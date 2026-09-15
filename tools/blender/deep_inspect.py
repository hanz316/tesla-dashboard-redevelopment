#!/usr/bin/env python3
"""Deep, strictly read-only inspection of a vehicle model.

Reports what `tools/assets/inspect_model.py` cannot:

* every object in the file (any type) with world dimensions and origin
* origin vs bounding-box centre — the first hint about hinge placement
* for merged meshes: the number of disconnected components (loose parts),
  computed on an in-memory copy only, so the file is never modified
* material -> polygon count, i.e. which material drives which surface
* scene unit settings and overall vehicle bounding box

Nothing is written back to the model file.

Usage:
    blender -b -P tools/blender/deep_inspect.py -- --input model.fbx --json out.json
"""

import argparse
import json
import os
import sys

try:
    import bpy
    import bmesh
    from mathutils import Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender: blender -b -P tools/blender/deep_inspect.py")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--max-components", type=int, default=40,
                    help="stop counting loose parts beyond this many")
    ap.add_argument("--component-detail", action="store_true",
                    help="list per-loose-part bbox/materials (merged meshes)")
    return ap.parse_args(argv)


def load(path):
    ext = os.path.splitext(path)[1].lower()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        try:
            bpy.ops.wm.obj_import(filepath=path)
        except AttributeError:
            bpy.ops.import_scene.obj(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
    else:
        sys.exit(f"unsupported: {ext}")


def world_bounds(obj):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for corner in obj.bound_box:
        w = obj.matrix_world @ Vector(corner)
        lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
        hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    return lo, hi


def loose_part_count(obj, limit):
    """Counts disconnected mesh islands using an in-memory bmesh copy."""
    mesh_copy = obj.data.copy()
    bm = bmesh.new()
    bm.from_mesh(mesh_copy)
    bm.verts.ensure_lookup_table()
    visited = set()
    components = 0
    for vert in bm.verts:
        if vert.index in visited:
            continue
        components += 1
        if components > limit:
            break
        stack = [vert]
        visited.add(vert.index)
        while stack:
            current = stack.pop()
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other.index not in visited:
                    visited.add(other.index)
                    stack.append(other)
    bm.free()
    bpy.data.meshes.remove(mesh_copy)
    return components


def material_polygon_counts(obj):
    counts = {}
    mats = [m.name if m else "(none)" for m in obj.data.materials]
    for poly in obj.data.polygons:
        idx = poly.material_index
        name = mats[idx] if idx < len(mats) else f"(idx {idx})"
        counts[name] = counts.get(name, 0) + 1
    return counts


def component_report(obj, limit):
    """Per-loose-part bounding boxes: shows whether merged geometry still
    contains identifiable parts (doors, hood, wheels...)."""
    mesh_copy = obj.data.copy()
    bm = bmesh.new()
    bm.from_mesh(mesh_copy)
    bm.verts.ensure_lookup_table()
    visited = set()
    parts = []
    for vert in bm.verts:
        if vert.index in visited:
            continue
        if len(parts) >= limit:
            break
        stack = [vert]
        visited.add(vert.index)
        group = []
        while stack:
            current = stack.pop()
            group.append(current)
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other.index not in visited:
                    visited.add(other.index)
                    stack.append(other)
        lo = Vector((1e9, 1e9, 1e9))
        hi = Vector((-1e9, -1e9, -1e9))
        mats = set()
        for v in group:
            w = obj.matrix_world @ v.co
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
            for face in v.link_faces:
                idx = face.material_index
                if idx < len(obj.data.materials):
                    material = obj.data.materials[idx]
                    if material:
                        mats.add(material.name)
        size = hi - lo
        centre = (lo + hi) * 0.5
        parts.append({
            "vertices": len(group),
            "size": [round(size.x, 3), round(size.y, 3), round(size.z, 3)],
            "centre": [round(centre.x, 3), round(centre.y, 3), round(centre.z, 3)],
            "materials": sorted(mats)[:6],
        })
    bm.free()
    bpy.data.meshes.remove(mesh_copy)
    parts.sort(key=lambda p: -p["vertices"])
    return parts


def main():
    args = parse_args()
    load(args.input)
    scene = bpy.context.scene

    objects = []
    for obj in bpy.data.objects:
        entry = {
            "name": obj.name,
            "type": obj.type,
            "parent": obj.parent.name if obj.parent else None,
        }
        if obj.type == "MESH":
            lo, hi = world_bounds(obj)
            size = hi - lo
            origin = obj.matrix_world.translation
            centre = (lo + hi) * 0.5
            entry.update({
                "vertices": len(obj.data.vertices),
                "polygons": len(obj.data.polygons),
                "materials": [m.name for m in obj.data.materials if m],
                "world_size_m": [round(size.x, 4), round(size.y, 4), round(size.z, 4)],
                "origin_world": [round(origin.x, 4), round(origin.y, 4), round(origin.z, 4)],
                "bbox_centre": [round(centre.x, 4), round(centre.y, 4), round(centre.z, 4)],
                "origin_offset_from_centre": [
                    round(origin.x - centre.x, 4),
                    round(origin.y - centre.y, 4),
                    round(origin.z - centre.z, 4),
                ],
            })
        objects.append(entry)

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    overall = None
    if meshes:
        los, his = zip(*(world_bounds(o) for o in meshes))
        lo = Vector((min(v.x for v in los), min(v.y for v in los), min(v.z for v in los)))
        hi = Vector((max(v.x for v in his), max(v.y for v in his), max(v.z for v in his)))
        overall = {
            "min": [round(lo.x, 4), round(lo.y, 4), round(lo.z, 4)],
            "max": [round(hi.x, 4), round(hi.y, 4), round(hi.z, 4)],
            "size": [round((hi - lo).x, 4), round((hi - lo).y, 4), round((hi - lo).z, 4)],
        }

    # Loose parts only matter when geometry is merged into few objects.
    merged_detail = []
    if len(meshes) <= 3:
        for obj in meshes:
            entry = {
                "object": obj.name,
                "loose_parts": loose_part_count(obj, args.max_components),
                "materials_by_polygon": material_polygon_counts(obj),
            }
            if args.component_detail:
                entry["components"] = component_report(obj, args.max_components)
            merged_detail.append(entry)

    report = {
        "input": os.path.relpath(args.input, REPO_ROOT),
        "scene": {
            "unit_system": scene.unit_settings.system,
            "scale_length": round(scene.unit_settings.scale_length, 6),
            "object_count": len(objects),
            "mesh_count": len(meshes),
            "material_count": len(bpy.data.materials),
        },
        "overall_bounds": overall,
        "objects": objects,
        "merged_mesh_detail": merged_detail,
    }

    out = args.json or os.path.join("/tmp",
                                    os.path.basename(args.input) + ".deep.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2)

    print(f"[deep] {report['input']}")
    print(f"[deep] objects={len(objects)} meshes={len(meshes)} "
          f"materials={report['scene']['material_count']} "
          f"units={scene.unit_settings.system}/{scene.unit_settings.scale_length}")
    if overall:
        print(f"[deep] world size (X,Y,Z) = {overall['size']}")
    for detail in merged_detail:
        print(f"[deep] merged object {detail['object']!r}: "
              f"loose_parts={detail['loose_parts']}")
    print(f"[deep] wrote {out}")


if __name__ == "__main__":
    main()
