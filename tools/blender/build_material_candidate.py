#!/usr/bin/env python3
"""MODEL_A_MATERIAL_CANDIDATE: a material-only revision, with evidence.

The human review says the car reads as a plastic miniature. Geometry, camera,
scale and lighting stay exactly as they are: this changes only the response of
five material classes, then measures what changed.

    BODY      clearcoat up, coat roughness down, base silver slightly darker
              and a touch rougher - a broad, readable reflection instead of a
              flat bright wash
    GLASS     darker tint, higher specular: at 515 px the windows must read
              clearly darker than white paint without becoming black holes
    TIRE      rougher, less specular: matte rubber
    RIM       slightly rougher, less coat: metallic, but not competing with the
              body for attention
    TRIM      less metallic, rougher: black trim must not share the glass or
              wheel response

Nothing is promoted: the production master is left untouched and the candidate
is written beside it (gitignored, regenerable). Evidence produced:

    assets/checkpoints/model_a_material/  before/after renders, per-class
                                          luminance statistics, comparison sheet

Usage:
    blender -b -P tools/blender/build_material_candidate.py -- \
        --master assets/source/blender/model_a_production_master.blend
"""

import argparse
import json
import os
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(REPO_ROOT, "assets", "checkpoints", "model_a_material")
CANVAS = (356, 236)
CAMERA = {"name": "Camera_Horizon", "ortho_scale": 5.55,
          "location": (-5.30, -4.55, 3.85), "target": (0.0, 0.0, 0.62)}

# class -> how to recognise the material by name, and the candidate deltas.
CLASSES = {
    "paint": {
        "match": ("M_Paint",),
        "goal": "broad highlight transitions across roof, hood and shoulders",
        # Tuned against the measurements: a 0.90 multiply took the painted
        # surface from mean 166 to 98, which is dirty grey, and it left the
        # glass brighter than the paint. 0.96 keeps the paint the brightest
        # material while the clearcoat change adds tonal range.
        "delta": {"Base Color": ("mul", (0.96, 0.96, 0.965)),
                  "Roughness": ("set", 0.28),
                  "Coat Weight": ("set", 0.78),
                  "Coat Roughness": ("set", 0.060),
                  "Specular IOR Level": ("set", 0.58)},
    },
    "glass": {
        "match": ("M_Glass",),
        "goal": "clearly darker than white paint, with highlight structure",
        # Measured twice: the tint alone moved nothing (138.6 -> 138.5) because
        # what you see is the reflected environment, and roughening the
        # reflection made the windows flatter (spread 51 -> 41), which is the
        # "grey plastic" read, not the fix. The candidate therefore keeps the
        # reflection SHARP, cuts the transmission so less interior shows
        # through, and darkens the tint: bright reflection streaks over dark
        # glass is what gives the windows structure at 515 px.
        "delta": {"Base Color": ("mul", (0.45, 0.48, 0.54)),
                  "Specular IOR Level": ("set", 1.00),
                  "Roughness": ("mul", (0.8, 0.8, 0.8)),
                  "Transmission Weight": ("mul", (0.65, 0.65, 0.65)),
                  # Lower IOR reduces the Fresnel reflection the windows show
                  # at these grazing angles - the last material-level lever
                  # that can darken glass without flattening it.
                  "IOR": ("set", 1.25)},
    },
    "tire": {
        "match": ("M_Tire",),
        "goal": "matte rubber, no sheen",
        "delta": {"Roughness": ("set", 0.95),
                  "Specular IOR Level": ("set", 0.18)},
    },
    "rim": {
        "match": ("M_Wheel",),
        "goal": "metallic with a controlled highlight, quieter than the body",
        "delta": {"Roughness": ("set", 0.27),
                  "Coat Weight": ("set", 0.16),
                  "Specular IOR Level": ("set", 0.60)},
    },
    "trim": {
        "match": ("M_Trim",),
        "goal": "distinct from glass, tyre and body",
        "delta": {"Metallic": ("set", 0.20),
                  "Roughness": ("set", 0.62)},
    },
}

# Emission colours for the class masks, one per class.
MASK_COLOURS = {
    "paint": (1.0, 0.0, 0.0),
    "glass": (0.0, 1.0, 0.0),
    "tire": (0.0, 0.0, 1.0),
    "rim": (1.0, 1.0, 0.0),
    "trim": (1.0, 0.0, 1.0),
    "other": (0.0, 1.0, 1.0),
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--world-scale", type=float, default=1.0,
                    help="scale the HDRI strength; 1.0 keeps the frozen studio")
    ap.add_argument("--variant", default="A",
                    help="A = candidate as measured; B = same but the paint base "
                         "colour untouched, for a human A/B choice")
    return ap.parse_args(argv)


def setup_camera(scene):
    camera = bpy.data.objects.get(CAMERA["name"])
    if camera is None:
        data = bpy.data.cameras.new(CAMERA["name"])
        camera = bpy.data.objects.new(CAMERA["name"], data)
        scene.collection.objects.link(camera)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = CAMERA["ortho_scale"]
        camera.location = CAMERA["location"]
        target = bpy.data.objects.new("Camera_Horizon_Target", None)
        scene.collection.objects.link(target)
        target.location = CAMERA["target"]
        con = camera.constraints.new("TRACK_TO")
        con.target = target
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.up_axis = "UP_Y"
    scene.camera = camera
    bpy.context.view_layer.update()
    return camera


def configure(scene, samples):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.render.resolution_x = CANVAS[0]
    scene.render.resolution_y = CANVAS[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.seed = 0
    scene.cycles.use_animated_seed = False


def render(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def classify(material):
    for name, spec in CLASSES.items():
        if any(material.name.startswith(prefix) for prefix in spec["match"]):
            return name
    return "other"


def read_input(bsdf, names):
    for name in names:
        if name in bsdf.inputs:
            return name, bsdf.inputs[name]
    return None, None


def apply_delta(material, delta):
    """Apply the candidate values, recording what each input was before."""
    bsdf = next((node for node in material.node_tree.nodes
                 if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return {}
    recorded = {}
    aliases = {
        "Base Color": ("Base Color",),
        "Roughness": ("Roughness",),
        "Metallic": ("Metallic",),
        "Coat Weight": ("Coat Weight", "Clearcoat"),
        "Coat Roughness": ("Coat Roughness", "Clearcoat Roughness"),
        "Specular IOR Level": ("Specular IOR Level", "Specular"),
        "Transmission Weight": ("Transmission Weight", "Transmission"),
        "IOR": ("IOR",),
    }
    for key, (mode, value) in delta.items():
        name, socket = read_input(bsdf, aliases[key])
        if socket is None:
            continue
        before = socket.default_value
        if hasattr(before, "__len__"):
            before = tuple(round(float(v), 4) for v in before)
        else:
            before = round(float(before), 4)
        if mode == "set":
            socket.default_value = value
        else:  # multiply, component-wise for colours
            if hasattr(socket.default_value, "__len__"):
                # A colour socket carries RGBA while the delta may state RGB:
                # the last component (alpha) keeps its value.
                socket.default_value = tuple(
                    float(socket.default_value[i]) * value[min(i, len(value) - 1)]
                    for i in range(len(socket.default_value)))
            else:
                socket.default_value = float(socket.default_value) * value[0]
        after = socket.default_value
        if hasattr(after, "__len__"):
            after = tuple(round(float(v), 4) for v in after)
        else:
            after = round(float(after), 4)
        recorded[name] = {"before": before, "after": after}
    return recorded


def class_masks(scene, meshes, path):
    """Render one emission pass that says which class each pixel belongs to."""
    originals = {}
    mask_materials = {}
    for name, colour in MASK_COLOURS.items():
        material = bpy.data.materials.new(f"M_Mask_{name}")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        for node in list(nodes):
            nodes.remove(node)
        output = nodes.new("ShaderNodeOutputMaterial")
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Color"].default_value = colour + (1.0,)
        emission.inputs["Strength"].default_value = 1.0
        material.node_tree.links.new(emission.outputs["Emission"],
                                     output.inputs["Surface"])
        mask_materials[name] = material
    for obj in meshes:
        for slot in obj.material_slots:
            if slot.material is None:
                continue
            originals[(obj.name, slot.slot_index)] = slot.material
            slot.material = mask_materials[classify(slot.material)]
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    render(scene, path)
    for (obj_name, slot_index), material in originals.items():
        obj = bpy.data.objects.get(obj_name)
        if obj is not None:
            obj.material_slots[slot_index].material = material
    return path


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=args.master)
    scene = bpy.context.scene
    camera = setup_camera(scene)
    configure(scene, args.samples)
    os.makedirs(OUT_DIR, exist_ok=True)

    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]

    report = {
        "schema": "model-a-material-candidate v1",
        "status": "MODEL_A_MATERIAL_REVISION = AWAITING HUMAN VISUAL APPROVAL",
        "variant": args.variant,
        "master": os.path.relpath(args.master, REPO_ROOT),
        "camera": CAMERA["name"],
        "canvas": list(CANVAS),
        "samples": args.samples,
        # The glass reflects the studio; the four area lights are what give the
        # paint its highlights. The smallest evidence-backed change is to leave
        # the lights alone and reduce the uniform HDRI field the windows mirror.
        "lighting_or_hdri_changed": None,
        "world_strength": None,
        "geometry_changed": False,
        "camera_changed": False,
        "classes": {},
        "masks": {},
    }

    before_path = os.path.join(OUT_DIR, "material_before.png")
    suffix = "" if args.variant == "A" else f"_variant{args.variant}"
    after_path = os.path.join(OUT_DIR, f"material_after{suffix}.png")
    mask_path = os.path.join(OUT_DIR, "material_classes.png")

    render(scene, before_path)
    report["masks"]["classes"] = class_masks(scene, meshes, mask_path)

    changes = {}
    for obj in meshes:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                continue
            kind = classify(material)
            if kind == "other":
                continue
            delta = dict(CLASSES[kind]["delta"])
            if args.variant == "B" and kind == "paint":
                # Variant B: keep the production paint brightness and take only
                # the clearcoat change, so the human can see what the darkening
                # costs and buys.
                delta.pop("Base Color", None)
            recorded = apply_delta(material, delta)
            if recorded:
                changes.setdefault(f"{kind}:{material.name}", recorded)
    report["material_changes"] = changes
    report["classes"] = {kind: {"goal": spec["goal"],
                                "delta": {key: str(value)
                                          for key, value in spec["delta"].items()}}
                         for kind, spec in CLASSES.items()}

    # --- lighting: tested, measured, NOT changed -----------------------
    #
    # The windows mirror the studio HDRI, so the candidate was also measured
    # with the HDRI at 60 %. One run was enough to reject it: the whole car
    # darkened with it (paint mean 166 -> 114) and the gap between glass and
    # paint collapsed (glass 112 vs paint 114), which is the opposite of what
    # the review asked for. The frozen studio therefore stays exactly as it is
    # and the glass question goes to the human as an open item, rather than
    # being solved by re-tuning the studio.
    world = scene.world
    background = None
    if world is not None and world.use_nodes:
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                background = node
                break
    if background is not None:
        before_strength = round(float(background.inputs["Strength"].default_value), 4)
        scale = args.world_scale
        background.inputs["Strength"].default_value = before_strength * scale
        report["world_strength"] = {"node": background.name,
                                    "before": before_strength,
                                    "after": round(before_strength * scale, 4),
                                    "scale": scale}
        report["lighting_or_hdri_changed"] = (scale != 1.0)
    else:
        report["lighting_or_hdri_changed"] = False

    configure(scene, args.samples)
    render(scene, after_path)

    candidate_blend = os.path.join(REPO_ROOT, "assets", "source", "blender",
                                   "model_a_material_candidate.blend")
    bpy.ops.wm.save_as_mainfile(filepath=candidate_blend)
    report["candidate_master"] = os.path.relpath(candidate_blend, REPO_ROOT)

    with open(os.path.join(OUT_DIR, f"material_candidate{suffix}.json"), "w") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")
    print(f"[material] before {os.path.relpath(before_path, REPO_ROOT)}")
    print(f"[material] after  {os.path.relpath(after_path, REPO_ROOT)}")
    print(f"[material] masks  {os.path.relpath(mask_path, REPO_ROOT)}")
    print(f"[material] candidate blend {report['candidate_master']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
