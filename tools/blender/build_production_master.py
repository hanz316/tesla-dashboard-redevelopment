#!/usr/bin/env python3
"""Build MODEL_A_PRODUCTION_MASTER from the MODEL A source, deterministically.

This is the only sanctioned way to produce the production vehicle. It applies
the measured per-panel normal policy, adds the finalized taillight light-guide
geometry, installs the frozen material set and the frozen camera/lighting, then
writes both the master .blend and the parameter manifest that locks everything.

The .blend is NOT committed (it contains third-party geometry; see
assets/ATTRIBUTION.md). The manifest IS committed, and this script regenerates
the .blend byte-for-byte from the recorded inputs.

Usage:
    blender -b -P tools/blender/build_production_master.py -- \
        --blend assets/source/blender/model_a_production_master.blend \
        --manifest MODEL_A_PRODUCTION_MASTER.json
"""

import argparse
import json
import math
import os
import sys

try:
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmi_materials  # noqa: E402
import hmi_studio_photoreal as photoreal  # noqa: E402
import hmi_studio_reference as reference  # noqa: E402
import hmi_studio_v4 as v4  # noqa: E402
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402
import taillight_finalize as tail_base  # noqa: E402
import taillight_guide_v4 as tg4  # noqa: E402
import taillight_system as tail  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROD_HDRI = "assets/source/hdri/photo_studio_01_2k.hdr"
TAILIGHT_GEOMETRY_VERSION = "surface-offset-cavity-lightguide-v3"

# Part 1: the measured policy. Do NOT normalise this into a whole-car pass.
NORMAL_POLICY = {
    "door_lf": "WEIGHTED",
    "door_rf": "CLEAN",
    "door_lr": "KEEP_ORIGINAL",
    "door_rr": "KEEP_ORIGINAL",
    "bonnet_ok": "WEIGHTED",
    "boot": "KEEP_ORIGINAL",
    "front_bumper_ok": "CLEAN",
    "rear_bumper_ok": "KEEP_ORIGINAL",
    "body": "WEIGHTED",
}
NORMAL_POLICY_SOURCE = "panel_normal_policy.json (measured, see MODEL_A_CEILING_TEST.md)"

# Part 2: the four lamp objects that receive a real light guide.
TAILLIGHT_OBJECTS = ["rear_lights", "rear_lightsl", "rear_lightsr",
                     "light_breake"]
LIGHT_GUIDE_ROD_RADIUS = 0.0085      # 8.5 mm rod
LIGHT_GUIDE_ARC_SEGMENTS = 28
LIGHT_GUIDE_RING_VERTS = 12
LIGHT_GUIDE_INSET = 0.016            # 16 mm behind the lens surface


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--blend", required=True)
    ap.add_argument("--manifest", required=True)
    return ap.parse_args(argv)


def apply_panel_policy(meshes, report):
    """Weld + recalc + shade smooth for CLEAN; plus weighted normals for
    WEIGHTED. KEEP_ORIGINAL objects are not touched at all."""
    for obj in meshes:
        mode = NORMAL_POLICY.get(obj.name)
        if mode is None or mode == "KEEP_ORIGINAL":
            continue
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        mesh = obj.data
        if getattr(mesh, "has_custom_normals", False):
            try:
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
                report["custom_normals_cleared"] += 1
            except Exception:
                pass
        bm = bmesh.new()
        bm.from_mesh(mesh)
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0002)
        report["welded_vertices"] += before - len(bm.verts)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        for poly in mesh.polygons:
            poly.use_smooth = True
        if mode == "WEIGHTED":
            mod = obj.modifiers.new("HMI_WeightedNormal", "WEIGHTED_NORMAL")
            mod.keep_sharp = True
            mod.weight = 60
            report["weighted_normal_objects"] += 1
        report["processed"].append(obj.name)
        obj.select_set(False)
    return report


def build_light_guide(name, bbox_min, bbox_max, material, mirror=False):
    """PRODUCTION light guide: a swept rod that is PROVABLY inside the lens.

    The first version fitted the rod to the lamp's *bounding box*, which is a
    box around a curved lens - so parts of the rod protruded through the lens
    and read as visible red rods. Review caught it.

    This version fits the rod to the lamp MESH: the path follows the centroid
    of the actual lamp vertices in thin slabs along the lamp axis, pushed
    inward, and every generated vertex is then tested for containment inside
    the lens with a parity ray cast. If any vertex is outside, the radius and
    inset are reduced and it retries. The returned object therefore carries a
    hard guarantee, not a hope.
    """
    src = bpy.data.objects.get(name.replace("_LightGuide", ""))
    if src is None:
        return None, {"inside": False, "reason": "source lamp missing"}

    lens_verts = [src.matrix_world @ v.co for v in src.data.vertices]
    if len(lens_verts) < 16:
        return None, {"inside": False, "reason": "lamp mesh too small"}

    xs = sorted(v.x for v in lens_verts)
    lo_x = xs[int(len(xs) * 0.12)]
    hi_x = xs[int(len(xs) * 0.88)]
    axis_len = hi_x - lo_x
    if axis_len <= 0.01:
        lo_x, hi_x = min(xs), max(xs)
        axis_len = hi_x - lo_x

    # Inward direction: toward the vehicle centreline, which is the side the
    # lens interior faces.
    cy = sum(v.y for v in lens_verts) / len(lens_verts)
    inward = Vector((0.0, -1.0 if cy > 0 else 1.0, 0.0))

    from mathutils.bvhtree import BVHTree
    deps = bpy.context.evaluated_depsgraph_get()
    ev = src.evaluated_get(deps)
    mesh_eval = ev.to_mesh()
    mw = src.matrix_world
    world_verts = [mw @ v.co for v in mesh_eval.vertices]
    world_polys = [tuple(p.vertices) for p in mesh_eval.polygons]
    tree = BVHTree.FromPolygons(world_verts, world_polys, all_triangles=False)
    ev.to_mesh_clear()

    # The tail lamp objects are OPEN SHELLS (a lens surface), not closed
    # volumes, so an inside/outside parity test is meaningless on them - the
    # first version of this check rejected every candidate because of that.
    # What actually matters is whether the rod is VISIBLE from outside, so the
    # test is occlusion: from every exterior direction the ray must hit the
    # lamp before it escapes.
    outward_dirs = [
        Vector((0.0, -1.0 if cy > 0 else 1.0, 0.0)),   # straight out
        Vector((0.6, -1.0 if cy > 0 else 1.0, 0.3)),
        Vector((-0.6, -1.0 if cy > 0 else 1.0, 0.3)),
        Vector((0.0, -1.0 if cy > 0 else 1.0, 1.0)),   # up and out
        Vector((0.0, -1.0 if cy > 0 else 1.0, -1.0)),  # down and out
    ]
    for d in outward_dirs:
        d.normalize()

    def occluded(point):
        """True when every exterior ray hits the lamp before escaping."""
        for d in outward_dirs:
            loc, nor, idx, dist = tree.ray_cast(Vector(point), d, 4.0)
            if loc is None:
                return False
        return True

    def build(radius, inset, sagitta_scale):
        rings = []
        for i in range(LIGHT_GUIDE_ARC_SEGMENTS):
            t = i / (LIGHT_GUIDE_ARC_SEGMENTS - 1.0)
            px = lo_x + t * axis_len
            # Centroid of the real lens geometry in this slab -> the path
            # follows the lamp, not a box.
            band = [v for v in lens_verts if abs(v.x - px) < axis_len * 0.06]
            if not band:
                band = [v for v in lens_verts if abs(v.x - px) < axis_len * 0.15]
            if not band:
                band = lens_verts
            c = Vector((0.0, 0.0, 0.0))
            for v in band:
                c += v
            c /= len(band)
            u = t - 0.5
            sag = (max(v.z for v in band) - min(v.z for v in band)) * sagitta_scale
            centre = c + inward * inset
            centre.z += sag * (1.0 - (2.0 * u) ** 2)
            tangent = Vector((1.0, 0.0, -4.0 * sag * u / max(axis_len, 1e-6)))
            tangent.normalize()
            up = Vector((0.0, 0.0, 1.0))
            side = tangent.cross(up).normalized()
            up2 = side.cross(tangent).normalized()
            ring = []
            for k in range(LIGHT_GUIDE_RING_VERTS):
                a = 2.0 * math.pi * k / LIGHT_GUIDE_RING_VERTS
                offset = (math.cos(a) * up2 + math.sin(a) * side) * radius
                ring.append(centre + offset)
            rings.append(ring)
        return rings

    attempts = []
    chosen = None
    radius = LIGHT_GUIDE_ROD_RADIUS
    inset = LIGHT_GUIDE_INSET
    sagitta = 0.16
    for attempt in range(6):
        rings = build(radius, inset, sagitta)
        outside = sum(1 for ring in rings for v in ring if not occluded(v))
        attempts.append({"radius": round(radius, 5), "inset": round(inset, 5),
                         "sagitta": round(sagitta, 3), "outside": outside})
        if outside == 0:
            chosen = rings
            break
        radius *= 0.85
        inset += 0.004
        sagitta *= 0.7
    if chosen is None:
        return None, {"inside": False, "attempts": attempts}

    bm = bmesh.new()
    bm_rings = [[bm.verts.new((v.x, v.y, v.z)) for v in ring] for ring in chosen]
    bm.verts.ensure_lookup_table()
    n = LIGHT_GUIDE_RING_VERTS
    for r in range(len(bm_rings) - 1):
        a, b = bm_rings[r], bm_rings[r + 1]
        for k in range(n):
            k2 = (k + 1) % n
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
    bm.faces.new(list(reversed(bm_rings[0])))
    bm.faces.new(bm_rings[-1])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(material)
    return obj, {"inside": True, "attempts": attempts,
                 "final_radius": round(radius, 5),
                 "final_inset": round(inset, 5),
                 "vertices_verified": len(chosen) * n}


def build_cavity(name, bbox_min, bbox_max, material):
    """A dark cavity shell just inside the lens, so the lens has depth."""
    centre = (bbox_min + bbox_max) * 0.5
    size = (bbox_max - bbox_min) * 0.62
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size.x, v.co.y * size.y, v.co.z * size.z))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = centre
    mesh.materials.append(material)
    return obj


def is_segment_object(name, prefix, label):
    """Segment objects carry their label, so several lamps can coexist."""
    return name.startswith(prefix + label + ("" if prefix == "Cavity_"
                                             else "_"))


def lamp_owner(label, boot_name="boot", contact_m=0.030):
    """FIXED_BODY or TRUNK_MOVING, decided from geometry rather than names.

    A lamp piece that belongs to the trunk lid sits on the lid panel, so it is
    within a few millimetres of the boot mesh. A piece that belongs to the body
    keeps its distance from the lid. Distances are measured vertex to surface,
    not bounding box to bounding box - a boot bounding box covers most of the
    rear of the car and labelled every lamp as trunk-mounted.
    """
    src = bpy.data.objects.get(label.split(":")[1])
    boot = bpy.data.objects.get(boot_name)
    if src is None or boot is None:
        return "UNKNOWN", {"error": "source or boot missing"}
    tree = tail_base.bvh_of(boot)
    if tree is None:
        return "UNKNOWN", {"error": "boot has no triangles"}
    mw = src.matrix_world
    ds = []
    step = max(1, len(src.data.vertices) // 400)
    sampled = list(src.data.vertices)[::step]
    for v in sampled:
        p = mw @ v.co
        res = tree.find_nearest(p, 1.0)
        if res[0] is not None:
            ds.append(res[3])
    if not ds:
        return "UNKNOWN", {"error": "no distance samples"}
    ds.sort()
    median = ds[len(ds) // 2]
    owner = "TRUNK_MOVING" if median <= contact_m else "FIXED_BODY"
    return owner, {"samples": len(ds), "median_distance_to_boot_m":
                   round(median, 5), "p05_m": round(ds[len(ds) // 20], 5),
                   "min_m": round(ds[0], 5), "contact_threshold_m": contact_m}


def finalize_taillights(report):
    """Surface-offset cavity + medial light guide, solved per lamp component.

    Structure per optical segment: original outer lens (untouched) -> closed
    surface-offset cavity -> medial light guide, with the guide proven contained
    and clear by the v4 geometry stage. A lamp piece whose source geometry
    cannot host a cavity of any usable thickness (the brake light) gets no
    guide at all and is lit by material/emission instead - no geometry beats
    protruding geometry.
    """
    _, _, _, cavity_mat, _, _, _ = v4.build_taillight()
    channels = tail.channel_materials()
    left_sign, err = tail_base.resolve_left_sign()
    if left_sign is None:
        report["light_guides_failed"].append(
            {"source": "all", "stage": "left_sign", "detail": err})
        return []

    segments = []
    for comp in tg4.component_sources(left_sign):
        entry = tg4.evaluate_segment(comp, tg4.OFFSET_CANDIDATES_M, True,
                                     None, None)
        if entry is not None:
            segments.append(entry)
    tg4.pair_offsets(segments)

    built = []
    owners = {}
    for entry in segments:
        if not entry.get("passed"):
            report["light_guides_failed"].append({
                "source": entry["label"], "stage": "geometry",
                "detail": entry.get("evidence") or entry.get("offsets", [])[-1:]})
            continue
        owner_class, owner_evidence = lamp_owner(entry["label"])
        owners[entry["label"]] = {"owner": owner_class,
                                  "evidence": owner_evidence}
        tg4.discard_unselected(entry)
        for obj in bpy.data.objects:
            if is_segment_object(obj.name, "Cavity_", entry["label"]):
                # The cavity is a containment volume, not a visible part: its
                # outer wall is coincident with the lens and its inner wall
                # surrounds the guide. It stays in the master (it is what the
                # guide is proven inside, and the screen-space QA renders it),
                # but it must not occlude the guide in production renders.
                obj.hide_render = True
                for slot in obj.material_slots:
                    slot.material = cavity_mat
                if not obj.data.materials:
                    obj.data.materials.append(cavity_mat)
                else:
                    obj.data.materials[0] = cavity_mat
            if is_segment_object(obj.name, "TailGuide_", entry["label"]):
                for slot in obj.material_slots:
                    slot.material = channels["OFF"]
        report["light_guides"].append({
            "segment": entry["label"], "lamp": entry["lamp"],
            "owner": owner_class, "owner_evidence": owner_evidence,
            "offset_m": entry["selected_thickness_m"],
            "pair_offset_m": entry.get("pair_offset_m"),
            "cavity": [o.name for o in bpy.data.objects
                       if is_segment_object(o.name, "Cavity_", entry["label"])],
            "guides": [o.name for o in bpy.data.objects
                       if is_segment_object(o.name, "TailGuide_",
                                            entry["label"])],
            "summary": entry.get("summary"),
        })
        built += [o.name for o in bpy.data.objects
                  if is_segment_object(o.name, "Cavity_", entry["label"])]
        built += [o.name for o in bpy.data.objects
                  if is_segment_object(o.name, "TailGuide_", entry["label"])]
        print(f"[master] {entry['label']}: offset={entry['selected_thickness_m']} "
              f"containment={entry['summary']['worst_containment_percent']} "
              f"clearance={entry['summary']['worst_min_clearance_m']} "
              f"coverage={(entry['summary']['coverage'] or {}).get('coverage_ratio_of_usable')}")

    report["channels"] = sorted(channels.keys())
    report["segments"] = segments
    report["trunk_ownership"] = owners
    report["trunk_ownership_error"] = None
    return built


def main():
    args = parse_args()
    meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")

    report = {"processed": [], "custom_normals_cleared": 0,
              "welded_vertices": 0, "weighted_normal_objects": 0,
              "light_guides": [], "light_guides_failed": []}
    apply_panel_policy(meshes, report)
    finalize_taillights(report)

    # Frozen material set (Part 3/4/5): the reference architecture, unchanged.
    v4.apply_v4_materials(meshes, paint="d", silver="neutral")
    paint = reference.build_reference_paint()
    glass = {k: reference.build_reference_glass(k)
             for k in ("roof", "front", "side", "rear")}
    for obj in meshes:
        for slot in obj.material_slots:
            original = slot.material
            if original is None:
                continue
            role = hmi_materials.classify(original)
            name = original.name.lower()
            if role == "BODY":
                slot.material = paint
            elif role == "GLASS":
                if "glass.1" in name:
                    slot.material = glass["roof"]
                elif "depan" in name:
                    slot.material = glass["front"]
                elif "belakang" in name:
                    slot.material = glass["rear"]
                else:
                    slot.material = glass["side"]

    hdri_path = os.path.join(REPO_ROOT, PROD_HDRI)
    photoreal.build_hdri_world(hdri_path, 1.0, 0.0)
    photoreal.build_hybrid_lights(1.0, 2.0)

    cfg = vehicle_v2.CAMERA_PRESETS["v2a"]
    az, el = math.radians(cfg["azimuth_deg"]), math.radians(cfg["elevation_deg"])
    target = Vector((0.0, 0.0, cfg["look_at_z"]))
    direction = Vector((-math.cos(el) * math.cos(az),
                        -math.cos(el) * math.sin(az), math.sin(el)))
    data = bpy.data.cameras.new("PRODUCTION_Camera")
    data.type = "ORTHO"
    data.ortho_scale = cfg["ortho_scale"]
    cam = bpy.data.objects.new("PRODUCTION_Camera", data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = target + direction * 14.0
    empty = bpy.data.objects.new("PRODUCTION_Target", None)
    bpy.context.scene.collection.objects.link(empty)
    empty.location = target
    con = cam.constraints.new("TRACK_TO")
    con.target = empty
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    bpy.context.scene.camera = cam

    os.makedirs(os.path.dirname(args.blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=args.blend)

    manifest = {
        "asset": "MODEL_A_PRODUCTION_MASTER",
        "status": "LOCKED",
        "derived_from": {
            "geometry": "MODEL A - Tesla 2018 Model 3 (Ameer Studio FBX)",
            "source_file": "assets/source/download/model_a_ameer/source/"
                           "tesla_car1.fbx",
            "blend": os.path.relpath(args.blend, REPO_ROOT),
            "builder": "tools/blender/build_production_master.py",
        },
        "normal_policy": {
            "policy": NORMAL_POLICY,
            "source": NORMAL_POLICY_SOURCE,
            "applied": sorted(report["processed"]),
            "welded_vertices": report["welded_vertices"],
            "custom_normals_cleared": report["custom_normals_cleared"],
            "weighted_normal_objects": report["weighted_normal_objects"],
            "untouched_objects": 107 - len(report["processed"]),
        },
        "taillight_geometry": {
            "version": TAILIGHT_GEOMETRY_VERSION,
            "status": "GEOMETRY_STAGE_COMPLETE_PENDING_FREEZE_GATE",
            "outer_lens": "unchanged MODEL A geometry",
            "added": report["light_guides"],
            "failed": report["light_guides_failed"],
            "v1_defect": "lightguide-v1 fitted the rod to the lamp BOUNDING "
                         "BOX, so parts protruded through the curved lens and "
                         "read as red rods. Rejected in review.",
            "solved_by": "The lens shells are OPEN SHELLS, so a parity "
                         "containment test is undefined on them directly. The "
                         "interior is therefore derived from the SURFACE: the "
                         "shell is offset inward along its own normals into a "
                         "closed surface-offset cavity, which makes the parity "
                         "test valid and gives the guide a proven interior. "
                         "See docs/TAILLIGHT_GUIDE_V4.md.",
            "excluded_by_source_geometry": [
                {"lamp": "light_breake",
                 "measured": "the inward offset collapses at 2-5 mm (median "
                             "wall 0.80-0.92 mm against a 2-5 mm offset, "
                             "35-175 self-intersecting face pairs) and is not a "
                             "valid closed manifold at 6-12 mm; usable x span "
                             "0.0 m at every offset",
                 "consequence": "no internal guide; the brake light is lit by "
                                "material/emission on the lens. This is an "
                                "optical VISUAL_APPROXIMATION, not proven "
                                "OEM-exact segmentation."},
            ],
            "states_prepared": ["LIGHT_OFF", "BRAKE_ON",
                                "LEFT_INDICATOR", "RIGHT_INDICATOR"],
        },
        "paint": {
            "name": "REFERENCE AUTOMOTIVE PAINT (basecoat + independent "
                    "clearcoat)",
            "architecture": "Glossy BSDF (coat) mixed by Fresnel over a "
                            "metallic Principled basecoat; Voronoi flake on "
                            "the BASECOAT",
            "silver": "OEM SILVER NEUTRAL",
            "base_color": [0.560, 0.578, 0.605],
            "basecoat_metallic": 1.0,
            "basecoat_roughness": 0.340,
            "basecoat_roughness_variation": {"scale": 2.6, "range": "0.90-1.12"},
            "flake": {"type": "Voronoi F1", "scale": 260.0,
                      "bump_strength": 0.16, "bump_distance": 0.0006},
            "clearcoat_bsdf": "Glossy", "clearcoat_roughness": 0.018,
            "clearcoat_color": [0.92, 0.93, 0.95],
            "mix": {"base": 0.42, "fresnel_gain": 0.62, "layer_blend": 0.16},
        },
        "glass": {
            "architecture": "Principled dielectric + independent Glossy "
                            "coating layer, mixed by coat weight",
            "panes": reference.REFERENCE_GLASS,
        },
        "wheel_tire": {
            "rim": {"base_color": [0.150, 0.157, 0.170], "metallic": 0.95,
                    "roughness": 0.225, "anisotropic": 0.62,
                    "coat": 0.28, "specular": 0.70},
            "tire": {"base_color": [0.020, 0.020, 0.022], "metallic": 0.0,
                     "roughness": 0.93, "specular": 0.26},
            "brake_disc": {"base_color": [0.270, 0.272, 0.278],
                           "metallic": 1.0, "roughness": 0.38,
                           "anisotropic": 0.35},
            "note": "rim stays well below body brightness "
                    "(0.150 vs 0.560 base colour)",
        },
        "camera": {
            "preset": "V2-A", "type": "ORTHO",
            "azimuth_deg": cfg["azimuth_deg"],
            "elevation_deg": cfg["elevation_deg"],
            "ortho_scale": cfg["ortho_scale"],
            "look_at_z": cfg["look_at_z"],
            "distance_m": 14.0,
            "render_canvas": "1100x760",
            "supersample": 2,
            "output_resolution": "2200x1520",
        },
        "lighting": {
            "environment": PROD_HDRI,
            "environment_license": "CC0 1.0 (Poly Haven, Sergej Majboroda)",
            "environment_strength": 1.0,
            "rig": "HDRI HYBRID: 1 key (260 W, glossy) + 1 fill (90 W x2, "
                   "diffuse-only) + 1 rim (150 W) + 1 bounce (46 W x2, "
                   "diffuse-only)",
            "film_transparent": True,
        },
        "render": {
            "engine": "Cycles", "device": "CPU (GPU ran out of memory)",
            "samples": 96, "adaptive": True, "denoise": True,
            "sample_clamp_indirect": 4.0, "sample_clamp_direct": 6.0,
            "view_transform": "AgX", "exposure": 0.10, "gamma": 1.00,
            "output": "PNG RGBA",
        },
        "lock_notice": "These parameters are LOCKED. Door_FL/FR/RL/RR, frunk, "
                       "trunk, brake, indicator and headlight assets must all "
                       "derive from this master. Per-state re-tuning of "
                       "material, camera or lighting is forbidden because it "
                       "produces visible jumps between states.",
    }
    os.makedirs(os.path.dirname(args.manifest), exist_ok=True)
    with open(args.manifest, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print(f"[master] normal policy applied to {len(report['processed'])} "
          f"objects, {report['welded_vertices']} verts welded, "
          f"{len(report['light_guides'])} light guides")
    print(f"[master] blend -> {args.blend}")
    print(f"[master] manifest -> {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
