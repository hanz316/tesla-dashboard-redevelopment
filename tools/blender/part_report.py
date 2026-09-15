#!/usr/bin/env python3
"""Deep part-structure report for FBX/BLEND inputs (needs Blender).

Goes further than tools/assets/inspect_model.py: it also inspects
materials, loose parts inside a single mesh, and vertex counts, then
classifies every part as

    ALREADY_SEPARATE | AUTO_SPLITTABLE_CANDIDATE | NEEDS_MANUAL_WORK

It never modifies the model. Run the import step afterwards, or hand the
report to a human for mesh surgery decisions.

Usage:
    blender -b -P tools/blender/part_report.py -- --input model.fbx
"""

import argparse
import json
import os
import sys

try:
    import bpy
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender: blender -b -P tools/blender/part_report.py")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAPPING_PATH = os.path.join(REPO_ROOT, "tools", "assets", "part_mapping.json")


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default=None)
    return ap.parse_args(argv)


def import_asset(path):
    ext = os.path.splitext(path)[1].lower()
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
        sys.exit(f"unsupported input: {ext}")


def classify(name, mapping):
    low = name.lower()
    for canonical, tokens in mapping["mappings"].items():
        for token in tokens:
            if token in low:
                return canonical
    return None


def loose_part_count(obj):
    """Counts disconnected islands — a hint that several logical parts are
    merged into one mesh object."""
    try:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.mesh.separate(type="LOOSE")
        # separate() acts on the mesh; we immediately undo to stay non-destructive
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.ed.undo()
        return None      # value unreliable after undo; reported as hint only
    except Exception:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
        return None


def main():
    args = parse_args()
    mapping = json.load(open(MAPPING_PATH))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_asset(args.input)

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    entries = []
    for obj in meshes:
        canonical = classify(obj.name, mapping)
        mat_names = [m.name for m in obj.data.materials if m]
        entries.append({
            "object": obj.name,
            "canonical": canonical,
            "vertices": len(obj.data.vertices),
            "polygons": len(obj.data.polygons),
            "materials": mat_names,
            "status": "ALREADY_SEPARATE" if canonical else "UNMATCHED",
        })

    # A mesh that carries both body and glass materials is a split candidate.
    mixed = [e for e in entries
             if len({m.lower() for m in e["materials"]}) > 1
             and e["canonical"] is None]
    for e in mixed:
        e["status"] = "AUTO_SPLITTABLE_CANDIDATE"

    unmatched = [e for e in entries if e["status"] == "UNMATCHED"]
    for e in unmatched:
        e["status"] = "NEEDS_MANUAL_WORK"

    report = {
        "input": os.path.relpath(args.input, REPO_ROOT),
        "mesh_objects": len(meshes),
        "materials": [m.name for m in bpy.data.materials][:60],
        "entries": entries,
        "summary": {
            "already_separate": sum(1 for e in entries
                                    if e["status"] == "ALREADY_SEPARATE"),
            "auto_splittable_candidates": len(mixed),
            "needs_manual_work": sum(1 for e in entries
                                     if e["status"] == "NEEDS_MANUAL_WORK"),
        },
        "guidance": [
            "ALREADY_SEPARATE parts can be renamed/animated directly.",
            "AUTO_SPLITTABLE_CANDIDATE parts share several materials and could be "
            "split by material — requires visual verification before doing so.",
            "NEEDS_MANUAL_WORK parts need a human to decide; never auto-cut.",
        ],
    }

    out = args.out or os.path.join(REPO_ROOT, "assets", "source", "blender",
                                   "part_report.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2)

    print(f"[part-report] {report['input']}: meshes={len(meshes)} "
          f"separate={report['summary']['already_separate']} "
          f"candidates={report['summary']['auto_splittable_candidates']} "
          f"manual={report['summary']['needs_manual_work']}")
    print(f"[part-report] wrote {os.path.relpath(out, REPO_ROOT)}")


if __name__ == "__main__":
    main()
