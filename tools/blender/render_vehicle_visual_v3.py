#!/usr/bin/env python3
"""Vehicle Visual V3 render: controlled shading + filmic look selection.

Same camera family and same MODEL A geometry as V2; only the shading, the
reflection studio, the light rig and the colour management change. That keeps
the V2 vs V3 comparison honest: if a frame looks different, it is the shading.

Usage:
    blender -b -P tools/blender/render_vehicle_visual_v3.py -- \\
        --preset silver_v3 --camera v2a --look normal --engine cycles \\
        --samples 96 --out out.png
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
import hmi_studio_v3  # noqa: E402
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402

# Part 5: Blender 5.2.2 ships no named AgX "look" variants (the look enum only
# exposes 'None'), and the view-settings CurveMapping turned out to be
# unusable here: changing its top control point produced a bit-identical
# render, so only its bottom region has any effect. Soft contrast is therefore
# built from the two display controls that measurably work - exposure (which
# protects the highlights) and gamma (which lifts the shadow floor).
LOOKS = {
    "normal": {
        "label": "V3_Normal (AgX, gamma 1.00)",
        "exposure": 0.30,
        "gamma": 1.00,
    },
    "soft": {
        "label": "V3_SoftContrast (lower exposure + lifted gamma)",
        "exposure": 0.16,
        "gamma": 1.35,
    },
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--preset", default="silver_v3",
                    choices=sorted(hmi_studio_v3.BODY_PRESETS_V3))
    ap.add_argument("--camera", default="v2a",
                    choices=sorted(vehicle_v2.CAMERA_PRESETS))
    ap.add_argument("--look", default="normal", choices=sorted(LOOKS))
    ap.add_argument("--engine", default="cycles", choices=["eevee", "cycles"])
    ap.add_argument("--samples", type=int, default=0)
    ap.add_argument("--exposure", type=float, default=None,
                    help="override the look's exposure")
    ap.add_argument("--key-scale", type=float, default=1.0,
                    help="scale the key/rim lights")
    ap.add_argument("--ambient-scale", type=float, default=1.0,
                    help="scale the diffuse-only dark-side recovery lights")
    ap.add_argument("--world-floor", type=float, default=None,
                    help="override the global ambient floor")
    ap.add_argument("--gamma", type=float, default=None,
                    help="override the look's display gamma")
    ap.add_argument("--out", required=True)
    ap.add_argument("--canvas", default="1100x760")
    ap.add_argument("--supersample", type=int, default=2)
    ap.add_argument("--nose", default="+Y")
    return ap.parse_args(argv)


def apply_look(scene, name, exposure_override=None, gamma_override=None):
    cfg = LOOKS[name]
    scene.view_settings.exposure = (exposure_override
                                    if exposure_override is not None
                                    else cfg["exposure"])
    scene.view_settings.gamma = (gamma_override
                                 if gamma_override is not None
                                 else cfg["gamma"])
    print(f"[v3] look={name} ({cfg['label']}) "
          f"exposure={scene.view_settings.exposure:.2f} "
          f"gamma={scene.view_settings.gamma:.2f}")


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))

    meshes, size = vehicle_v2.import_and_normalise(args.input, args.nose)
    hmi_studio_v3.apply_v3_materials(meshes, args.preset)
    hmi_studio_v3.build_light_rig_v3(args.key_scale, args.ambient_scale,
                                     args.world_floor)
    cards = hmi_studio_v3.build_reflection_studio_v3()
    print(f"[v3] reflection studio: {len(cards)} narrow strips/cards "
          f"(camera-invisible, off-white)")
    cfg = vehicle_v2.setup_camera(args.camera, canvas_w, canvas_h)
    scene = vehicle_v2.setup_render(args.engine, args.samples, canvas_w,
                                    canvas_h, args.supersample, args.out)
    apply_look(scene, args.look, args.exposure, args.gamma)

    print(f"[v3] preset={args.preset} camera={args.camera} ({cfg['label']}) "
          f"az={cfg['azimuth_deg']} el={cfg['elevation_deg']}")
    print(f"[v3] engine={args.engine} samples={args.samples or 'default'} "
          f"res={canvas_w*args.supersample}x{canvas_h*args.supersample} "
          f"vehicle={size}")

    start = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"[v3] RENDER_TIME {time.time() - start:.1f}s -> {args.out}")


if __name__ == "__main__":
    main()
