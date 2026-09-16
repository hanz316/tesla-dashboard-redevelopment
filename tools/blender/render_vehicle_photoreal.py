#!/usr/bin/env python3
"""Photoreal lighting study: V3 cards vs HDRI-only vs HDRI-hybrid.

Same geometry, camera, canvas, engine and sample count for all three, so the
only variable is where the reflections come from (Part B).

    --lighting v3      V3 reference: artificial reflection cards + V3 rig
    --lighting hdri    HDRI world, no cards, one dim diffuse bounce
    --lighting hybrid  HDRI world + one key, one fill, one rim

The world always renders with film_transparent = True, so the HDRI shapes the
car but is never written into the exported PNG.

Usage:
    blender -b -P tools/blender/render_vehicle_photoreal.py -- \
        --lighting hybrid --hdri assets/source/hdri/studio_kontrast_01_2k.hdr \
        --out out.png
"""

import argparse
import os
import sys
import time

try:
    import bpy
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmi_studio_photoreal as photoreal  # noqa: E402
import hmi_studio_v3 as v3  # noqa: E402
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_HDRI = os.path.join(REPO_ROOT, "assets", "source", "hdri",
                            "studio_kontrast_01_2k.hdr")

# Part G: no clipped white, no crushed black. These are the two knobs that
# measurably work in this Blender build (the view-settings CurveMapping does
# not - see render_vehicle_visual_v3.py). Gamma stays at 1.0 on purpose: it is
# not used to make the car "brighter".
LOOKS = {
    "normal": {"exposure": 0.30, "gamma": 1.00},
    "soft": {"exposure": 0.16, "gamma": 1.35},
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--lighting", default="hybrid",
                    choices=["v3", "hdri", "hybrid"])
    ap.add_argument("--preset", default="silver_photoreal",
                    choices=sorted(photoreal.PAINT_PRESETS))
    ap.add_argument("--camera", default="v2a",
                    choices=sorted(vehicle_v2.CAMERA_PRESETS))
    ap.add_argument("--hdri", default=DEFAULT_HDRI)
    ap.add_argument("--hdri-strength", type=float, default=1.0)
    ap.add_argument("--hdri-rotation", type=float, default=0.0)
    ap.add_argument("--key-scale", type=float, default=1.0)
    ap.add_argument("--fill-scale", type=float, default=1.0,
                    help="scale the diffuse-only shadow-floor light")
    ap.add_argument("--look", default="normal", choices=sorted(LOOKS))
    ap.add_argument("--exposure", type=float, default=None)
    ap.add_argument("--clamp-indirect", type=float, default=4.0,
                    help="cap indirect radiance. The HDRI contains very bright "
                         "studio lamps; without a cap their specular images "
                         "clip to pure white no matter how low the exposure "
                         "is. Lowering the whole exposure instead would crush "
                         "the shadows (Part G)")
    ap.add_argument("--clamp-direct", type=float, default=6.0)
    ap.add_argument("--engine", default="cycles", choices=["eevee", "cycles"])
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--canvas", default="1100x760")
    ap.add_argument("--supersample", type=int, default=2)
    ap.add_argument("--nose", default="+Y")
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))

    meshes, size = vehicle_v2.import_and_normalise(args.input, args.nose)

    if args.lighting == "v3":
        v3.apply_v3_materials(meshes, "silver_v3")
        v3.build_reflection_studio_v3()
        v3.build_light_rig_v3()
    else:
        photoreal.apply_photoreal_materials(meshes, args.preset)
        if not os.path.isfile(args.hdri):
            sys.exit(f"HDRI not found: {args.hdri}")
        photoreal.build_hdri_world(args.hdri, args.hdri_strength,
                                   args.hdri_rotation)
        if args.lighting == "hdri":
            photoreal.build_hdri_only_lights(args.fill_scale)
        else:
            photoreal.build_hybrid_lights(args.key_scale, args.fill_scale)

    cfg = vehicle_v2.setup_camera(args.camera, canvas_w, canvas_h)
    scene = vehicle_v2.setup_render(args.engine, args.samples, canvas_w,
                                    canvas_h, args.supersample, args.out)
    look = LOOKS[args.look]
    scene.view_settings.exposure = (args.exposure if args.exposure is not None
                                    else look["exposure"])
    scene.view_settings.gamma = look["gamma"]
    if hasattr(scene, "cycles"):
        scene.cycles.sample_clamp_indirect = args.clamp_indirect
        scene.cycles.sample_clamp_direct = args.clamp_direct

    print(f"[photoreal] lighting={args.lighting} preset={args.preset} "
          f"camera={args.camera} look={args.look} "
          f"exposure={scene.view_settings.exposure:.2f} "
          f"gamma={scene.view_settings.gamma:.2f} "
          f"clamp_indirect={args.clamp_indirect} "
          f"clamp_direct={args.clamp_direct}")
    print(f"[photoreal] engine={args.engine} samples={args.samples} "
          f"res={canvas_w*args.supersample}x{canvas_h*args.supersample} "
          f"vehicle={size} film_transparent={scene.render.film_transparent}")

    start = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"[photoreal] RENDER_TIME {time.time() - start:.1f}s -> {args.out}")


if __name__ == "__main__":
    main()
