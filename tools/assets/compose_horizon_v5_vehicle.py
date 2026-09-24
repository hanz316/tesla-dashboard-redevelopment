#!/usr/bin/env python3
"""Turn the V5 environment passes into the vehicle layer the screen pastes.

The Blender pass writes three things per state:

    road/no_car.png      the wet road with no car  (C0, state independent)
    road/<state>.png     the wet road with the car (C1)
    car/<state>/000.png  the car alone on transparent film

The car changes the road in two ways: it occludes it, and the wet surface
returns its shadow, its reflection and the ground response of whatever lamp the
state has lit. `C1 - C0` is exactly that change, with no painted polygon in it.
Compositing the clean car frame over those changed pixels gives one RGBA layer
that can be pasted onto the background bitmap.

The layer is cropped to its own alpha bounding box plus a margin, so the device
pastes a few hundred kilobytes instead of a full 1920x480 frame, and the crop
box is recorded in the manifest.

Usage:
    python3 tools/assets/compose_horizon_v5_vehicle.py
    python3 tools/assets/compose_horizon_v5_vehicle.py --states base,running
"""

import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load_rgb(path):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB")).astype(np.int16)


def smoothstep(edge0, edge1, values):
    import numpy as np
    span = max(1e-6, edge1 - edge0)
    scaled = np.clip((values - edge0) / span, 0.0, 1.0)
    return scaled * scaled * (3.0 - 2.0 * scaled)


def bake_reflection(car_image, spec):
    """The wet road's answer to the car, as a pre-baked transparent layer.

    The render already carries the sharp part of the reflection (the wet road
    mirroring the car). This layer adds the part a real water film adds and a
    path tracer at this roughness does not: a soft, rippled, distance-faded
    copy of the car. Pre-baked, so the device still does no runtime blur.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    alpha_box = car_image.getchannel("A").getbbox()
    if not alpha_box:
        return None, None
    car = car_image.crop(alpha_box)
    mirrored = car.transpose(Image.FLIP_TOP_BOTTOM)
    height = max(1, int(round(car.height * spec["squash"])))
    mirrored = mirrored.resize((car.width, height), Image.LANCZOS)
    mirrored = mirrored.filter(ImageFilter.GaussianBlur(spec["blur"]))

    array = np.asarray(mirrored).astype(np.float32)
    t = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    fade = spec["alpha"] * (1.0 - t) ** spec["falloff"]
    ripple = 1.0 + spec["ripple"] * np.sin(
        np.linspace(0.0, spec["ripple_cycles"] * 2.0 * np.pi, car.width,
                    dtype=np.float32))[None, :]
    array[:, :, 3] *= np.clip(fade * ripple, 0.0, 1.0)
    # A wet road also desaturates what it returns and pulls it toward the water
    # colour, so the reflection reads as light on water, not as a second car.
    tint = np.array(spec["tint"], dtype=np.float32)
    array[:, :, 0:3] = (array[:, :, 0:3] * (1.0 - spec["tint_mix"])
                        + tint[None, None, :] * spec["tint_mix"])
    layer = Image.fromarray(array.astype("uint8"), "RGBA")
    box = (alpha_box[0], alpha_box[3], alpha_box[0] + layer.width,
           alpha_box[3] + layer.height)
    return layer, box


def compose(state_dir, state, margin, alpha_edges, reflection_spec,
            plate_path):
    import numpy as np
    from PIL import Image

    no_car = load_rgb(os.path.join(state_dir, "road", "no_car.png"))
    with_car = load_rgb(os.path.join(state_dir, "road", f"{state}.png"))
    # The two renders are orthographic and the plate they are pasted onto is
    # perspective, so the road tones differ before the car is involved. The
    # layer therefore carries "the plate's road plus the car's local change",
    # not "the ortho road": with the offset applied, a pixel the car did not
    # touch composites back to exactly the plate and no seam can appear.
    plate = load_rgb(plate_path)
    if plate.shape != no_car.shape:
        from PIL import Image
        plate = np.asarray(Image.open(plate_path).convert("RGB").resize(
            (no_car.shape[1], no_car.shape[0]), Image.LANCZOS)).astype(np.int16)
    offset = (plate - no_car).astype(np.float32)
    car = np.asarray(Image.open(os.path.join(state_dir, "car", state,
                                                "000.png")).convert("RGBA"))
    height, width = no_car.shape[:2]
    difference = np.abs(with_car - no_car).max(axis=2).astype(np.float32)
    response_alpha = smoothstep(alpha_edges[0], alpha_edges[1], difference)
    # A stray denoised pixel two levels off the reference is not a ground
    # response; dropping it keeps the layer cropped to the car instead of the
    # whole frame.
    response_alpha[response_alpha < 0.05] = 0.0
    car_alpha = (car[:, :, 3].astype(np.float32) / 255.0)
    # The car's own silhouette, measured on the car pass. It is recorded so the
    # QA never has to guess which pixels of the finished layer are the car and
    # which are the road it changed.
    car_only = Image.fromarray((car_alpha * 255).astype(np.uint8)).getbbox()
    # The ground response lives around and below the car. Outside that band the
    # only differences between two renders of the same road are denoiser noise,
    # so the response is measured there and nowhere else.
    car_box = Image.fromarray((car_alpha * 255).astype(np.uint8)).getbbox()
    if car_box:
        band = np.zeros_like(response_alpha)
        # Deep enough for the mirror image the wet road returns (the car's own
        # height below the contact) and wide enough for its shadow, but not the
        # whole frame: outside this band the two renders differ only by noise.
        band[max(0, car_box[1] - 16):min(height, car_box[3] + 300),
             max(0, car_box[0] - 90):min(width, car_box[2] + 90)] = 1.0
        response_alpha *= band
    # Drop isolated specks: a ground response is a connected patch, and one
    # lonely pixel would otherwise grow the layer's crop box and paste a stray
    # dot next to the car.
    solid = response_alpha > 0.05
    neighbours = np.zeros_like(solid, dtype=np.int16)
    for shift_y in (-1, 0, 1):
        for shift_x in (-1, 0, 1):
            neighbours += np.roll(np.roll(solid, shift_y, axis=0), shift_x,
                                  axis=1).astype(np.int16)
    response_alpha[solid & (neighbours < 4)] = 0.0
    # Where the car is solid the car frame owns the pixel; the road response
    # only carries the pixels the car changed around itself.
    response_alpha *= (1.0 - car_alpha)
    layer_alpha = np.clip(car_alpha + response_alpha, 0.0, 1.0)

    car_rgb = car[:, :, :3].astype(np.float32)
    response_rgb = with_car.astype(np.float32) + offset
    total = np.maximum(layer_alpha, 1e-6)
    rgb = (car_rgb * car_alpha[:, :, None]
           + response_rgb * response_alpha[:, :, None]) / total[:, :, None]

    alpha8 = (layer_alpha * 255.0 + 0.5).astype(np.uint8)
    rgb8 = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
    layer = Image.fromarray(np.dstack([rgb8, alpha8]), "RGBA")

    reflection, reflection_box = bake_reflection(
        Image.open(os.path.join(state_dir, "car", state, "000.png"))
        .convert("RGBA"), reflection_spec)
    if reflection is not None:
        layer.alpha_composite(reflection, reflection_box[:2])

    box = layer.getchannel("A").getbbox() or (0, 0, 1, 1)
    box = (max(0, box[0] - margin), max(0, box[1] - margin),
           min(width, box[2] + margin), min(height, box[3] + margin))
    crop = layer.crop(box)
    stats = {
        "state": state,
        "crop_box": list(box),
        "layer_size": [crop.width, crop.height],
        "solid_car_pixels": int((car_alpha > 0.5).sum()),
        "response_pixels": int((response_alpha > 0.5).sum()),
        "reflection_box": list(reflection_box) if reflection_box else None,
        "car_box": list(car_only) if car_only else None,
        "decoded_rgba_bytes": crop.width * crop.height * 4,
        "background_decoded_rgba_bytes": width * height * 4,
    }
    return crop, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=os.path.join(
        REPO, "assets", "rendered", "vehicle", "horizon_v5"))
    parser.add_argument("--states", default="base,running,brake,headlight,"
                                            "indicator_left,indicator_right,"
                                            "hazard")
    parser.add_argument("--margin", type=int, default=24)
    parser.add_argument("--alpha-edges", default="3.0,14.0",
                        help="difference values (0-255) that map to alpha 0 and 1")
    parser.add_argument("--manifest", default=os.path.join(
        REPO, "assets", "rendered", "vehicle", "horizon_v5",
        "horizon_v5_vehicle.json"))
    parser.add_argument("--report", default=os.path.join(
        REPO, "assets", "checkpoints", "horizon_v5",
        "horizon_v5_vehicle_layers.json"))
    parser.add_argument("--reflection-squash", type=float, default=0.62)
    parser.add_argument("--reflection-blur", type=float, default=7.0)
    parser.add_argument("--reflection-alpha", type=float, default=0.30)
    parser.add_argument("--reflection-falloff", type=float, default=1.9)
    parser.add_argument("--plate", default=os.path.join(
        REPO, "assets", "ui", "horizon_v5_background.png"))
    args = parser.parse_args()
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as error:
        sys.exit(f"Pillow and numpy are required: {error}")

    edges = [float(value) for value in args.alpha_edges.split(",")]
    reflection_spec = {
        "squash": args.reflection_squash,
        "blur": args.reflection_blur,
        "alpha": args.reflection_alpha,
        "falloff": args.reflection_falloff,
        "ripple": 0.18,
        "ripple_cycles": 7.0,
        "tint": [0.42, 0.55, 0.68],
        "tint_mix": 0.28,
        "why": "the wet road already returns the car's mirror image; this baked "
               "layer is the soft, rippled part of that reflection - the light "
               "that scatters on the water rather than the sharp mirror line",
    }
    states = args.states.split(",")
    layers = {}
    records = []
    for state in states:
        layer, stats = compose(args.dir, state, args.margin, edges,
                               reflection_spec, args.plate)
        out = os.path.join(args.dir, "layer", f"{state}.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        layer.save(out)
        layers[state] = {"source": os.path.relpath(out, REPO),
                         "offset": stats["crop_box"][:2],
                         "size": stats["layer_size"]}
        records.append(stats)
        print(f"[v5-vehicle] {state:16} {stats['layer_size'][0]}x"
              f"{stats['layer_size'][1]} at {stats['crop_box'][:2]} "
              f"({os.path.getsize(out) // 1024} KB)")

    manifest = {
        "schema": "horizon-v5-vehicle-layers v1",
        "why": "One baked RGBA layer per lighting state: the car, plus every "
               "pixel the car changes about the wet road. Rendered with the "
               "frozen ortho Horizon camera, so the frozen 356x236 asset "
               "contract is untouched.",
        "camera": {"ortho_scale": 18.91305160522461,
                   "shift_x": 0.0038402501959353685,
                   "shift_y": -0.011006813496351242,
                   "projected_box_px": [753.5, 123.8, 1154.5, 345.0]},
        "layers": layers,
    }
    with open(args.manifest, "w") as handle:
        json.dump(manifest, handle, indent=1)
        handle.write("\n")
    report = {"schema": "horizon-v5-vehicle-layers-report v1",
              "alpha_edges": edges, "reflection": reflection_spec,
              "records": records}
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"[v5-vehicle] manifest {os.path.relpath(args.manifest, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
