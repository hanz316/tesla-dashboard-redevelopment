#!/usr/bin/env python3
"""Bake the motion overlays: streaks, wake and road flow.

Everything here is offline and deterministic. The device only ever composites,
crops, offsets and changes opacity, which is what the T113 can afford.

Where the colours and places come from: the lamp pixels are measured, not
chosen. `car/brake/000.png - car/base/000.png` is the brake lamp; the indicator
variants give the amber lamps; the sampled colour and the measured bounding box
of those pixels are what the streaks are drawn from, so a red streak is the
taillight's own red and an amber streak is the indicator's own amber.

Usage:
    python3 tools/assets/bake_horizon_v5_motion_assets.py
"""

import argparse
import json
import math
import os
import random
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools", "assets"))
import horizon_v5_motion as motion  # noqa: E402

UI = os.path.join(REPO, "assets", "ui")
VEHICLE = os.path.join(REPO, "assets", "rendered", "vehicle", "horizon_v5")
CANVAS = (1920, 480)


def load_rgba(path):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)


def lamp_pixels(state, difference_threshold=30.0):
    """The pixels a lighting state lights, isolated by colour dominance.

    The changed region of a lit lamp includes the lens around it, so the mask is
    restricted to pixels that both changed and are dominated by the lamp's own
    channel (red for this car's rear bar). The colour and the bounding box then
    come from the lamp, not from a UI constant, which means a future change to
    the taillight system flows straight into the streak.
    """
    import numpy as np
    base = load_rgba(os.path.join(VEHICLE, "car", "base", "000.png"))
    lit = load_rgba(os.path.join(VEHICLE, "car", state, "000.png"))
    difference = np.abs(lit[:, :, :3] - base[:, :, :3]).max(axis=2)
    red, green, blue = (lit[:, :, 0], lit[:, :, 1], lit[:, :, 2])
    mask = ((difference > difference_threshold) & (lit[:, :, 3] > 128)
            & (red > green + 24) & (red > 45))
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    colour = np.median(lit[mask][:, :3], axis=0)
    return {"mask": mask, "bbox": [int(xs.min()), int(ys.min()),
                                   int(xs.max()) + 1, int(ys.max()) + 1],
            "pixels": int(xs.size),
            "colour": [int(round(value)) for value in colour]}


def streak_image(size, box, colour, length, width, alpha, seed, spread=1.0):
    """A wet-road reflection streak: the lamp's own colour, elongated away from
    the car and feathered so it reads as light on water, not as a laser."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    rng = random.Random(seed)
    x0, y0, x1, y1 = box
    centre = (x0 + x1) / 2.0
    top = y1 - 4
    for index in range(14):
        t = index / 13.0
        y = top + t * length
        half = (width * (0.6 + 1.5 * t)) * spread
        jitter = rng.uniform(-2.5, 2.5) * spread
        fade = alpha * (1.0 - t) ** 1.35
        draw.line([(centre - half + jitter, y), (centre + half + jitter, y)],
                  fill=(*colour, int(round(255 * fade))),
                  width=max(2, int(round(4 + 10 * t))))
    layer = layer.filter(ImageFilter.GaussianBlur(3.5))
    return layer


def wake_image(size, car_box, colour, seed):
    """A cyan airflow trail: two soft ribbons leaving the car's rear, low
    frequency, semi-transparent, and gone completely at 0 km/h (the layout
    drives its opacity from aero_wake_level, which is zero there)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    rng = random.Random(seed)
    x0, y0, x1, y1 = car_box
    for side, direction in (("left", -1), ("right", 1)):
        base_x = x0 + (x1 - x0) * (0.10 if direction < 0 else 0.90)
        base_y = y0 + (y1 - y0) * 0.72
        points = []
        for index in range(22):
            t = index / 21.0
            points.append((base_x + direction * (26 + 150 * t)
                           + rng.uniform(-2.0, 2.0),
                           base_y - t * (14 + 26 * rng.uniform(0.0, 1.0))))
        for index in range(len(points) - 1):
            t = index / float(len(points) - 1)
            draw.line([points[index], points[index + 1]],
                      fill=(*colour, int(round(30 * (1.0 - t) ** 1.2))),
                      width=max(1, int(round(1 + 3 * t))))
    return layer.filter(ImageFilter.GaussianBlur(5.0))


def roadflow_tile(size, seed, streaks=26):
    """A small, faint wet-road streak texture. The device translates it and
    wraps it; it is a tile, so repeating it costs no extra memory."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    rng = random.Random(seed)
    width, height = size
    for _ in range(streaks):
        x = rng.uniform(0, width)
        length = rng.uniform(height * 0.35, height * 0.95)
        alpha = rng.uniform(9, 26)
        thickness = rng.uniform(1.0, 3.0)
        draw.line([(x, height - length), (x + rng.uniform(-3, 3), height)],
                  fill=(150, 178, 205, int(alpha)),
                  width=max(1, int(round(thickness))))
    return layer.filter(ImageFilter.GaussianBlur(1.6))


def wheel_overlays(car_path, boxes, spin_deg):
    """Rotational blur of the visible wheels, baked from the render itself.

    Measured first: rotating the master's `wheels` meshes in Blender changes
    1.8 k pixels and leaves the rim contrast untouched, i.e. those meshes are
    not the wheels this camera sees (the visible ones belong to the body mesh).
    Splitting them out would be a geometry change, and geometry is frozen, so
    the blur is produced from the pixels the camera actually shows: the wheel
    patch is rotated about its own centre across the exposure and the samples
    averaged, then written as an RGBA layer that *replaces* the wheel disc.

    That replacement is what makes the level a crossfade rather than a
    double exposure: at level 0 the layer is transparent (the sharp wheel the
    car render already has), at level 1 the disc is the fully swept wheel.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    car = Image.open(car_path).convert("RGBA")
    layer = Image.new("RGBA", (CANVAS[0], CANVAS[1]), (0, 0, 0, 0))
    for box in boxes:
        x0, y0, x1, y1 = [int(round(value)) for value in box]
        width, height = x1 - x0, y1 - y0
        patch = car.crop((x0, y0, x1, y1))
        cx, cy = width / 2.0, height / 2.0
        radius = 0.50 * min(width, height)
        samples = 11
        accumulator = None
        for index in range(samples):
            t = index / float(samples - 1) - 0.5
            rotated = patch.rotate(spin_deg * t, resample=Image.BILINEAR,
                                   center=(cx, cy))
            array = np.asarray(rotated).astype(np.float32)
            accumulator = array if accumulator is None else accumulator + array
        accumulator /= float(samples)
        mask_image = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask_image)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     fill=255)
        mask_image = mask_image.filter(ImageFilter.GaussianBlur(radius * 0.06))
        mask = np.asarray(mask_image).astype(np.float32) / 255.0
        # Only the car's own pixels: inside the wheel disc the road is
        # transparent in this pass, and a blurred patch must not paint black
        # over it. This is why the disc is masked twice - by its own shape and
        # by the car's alpha.
        car_alpha = np.asarray(patch)[:, :, 3].astype(np.float32) / 255.0
        accumulator[:, :, 3] = mask * car_alpha * 255.0
        layer.paste(Image.fromarray(np.clip(accumulator, 0, 255).astype("uint8"),
                                    "RGBA"),
                    (x0, y0), mask_image)
    return layer


def main():
    import numpy as np
    from PIL import Image
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=UI)
    parser.add_argument("--vehicle", default=VEHICLE)
    parser.add_argument("--report", default=os.path.join(
        REPO, "assets", "checkpoints", "horizon_v5",
        "horizon_v5_motion_assets.json"))
    args = parser.parse_args()
    width, height = CANVAS
    if not os.path.isdir(os.path.join(args.vehicle, "car", "base")):
        sys.exit("[v5-motion] the vehicle renders are missing: run "
                 "tools/blender/build_horizon_v5_environment.py first")

    report = {"schema": "horizon-v5-motion-assets v1", "assets": {}}
    brake = lamp_pixels("brake")
    left = lamp_pixels("indicator_left")
    right = lamp_pixels("indicator_right")
    for name, entry in (("brake", brake), ("indicator_left", left),
                        ("indicator_right", right)):
        if entry is None:
            sys.exit(f"[v5-motion] no lamp pixels found for {name}")
        report["assets"][f"lamp_{name}"] = {
            "bbox": entry["bbox"], "pixels": entry["pixels"],
            "colour": entry["colour"]}
        print(f"[v5-motion] {name:16s} bbox {entry['bbox']} "
              f"colour #{entry['colour'][0]:02X}{entry['colour'][1]:02X}"
              f"{entry['colour'][2]:02X}")

    base_layer_path = os.path.join(args.vehicle, "layer", "base.png")
    manifest_path = os.path.join(args.vehicle, "horizon_v5_vehicle.json")
    manifest = json.load(open(manifest_path))
    offset = manifest["layers"]["base"]["offset"]
    size = manifest["layers"]["base"]["size"]
    car_box = [offset[0], offset[1], offset[0] + size[0], offset[1] + size[1]]
    car_layer = Image.open(base_layer_path).convert("RGBA")
    alpha = np.asarray(car_layer)[:, :, 3]
    solid = Image.fromarray(alpha).point(lambda v: 255 if v > 200 else 0).getbbox()
    car_body = [offset[0] + solid[0], offset[1] + solid[1],
                offset[0] + solid[2], offset[1] + solid[3]]

    car_pass = os.path.join(args.vehicle, "car", "base", "000.png")
    car_pass_alpha = None
    if os.path.isfile(car_pass):
        car_pass_alpha = (np.asarray(Image.open(car_pass).convert("RGBA"))
                          .astype(np.float32)[:, :, 3] / 255.0)

    def outside_car(image):
        """Keep the light off the car's own body: these overlays are drawn over
        the vehicle layer (they are surface effects on the road), so they must
        not paint light onto the paintwork."""
        if car_pass_alpha is None:
            return image
        array = np.asarray(image).astype(np.float32)
        array[:, :, 3] *= (1.0 - car_pass_alpha)
        return Image.fromarray(np.clip(array, 0, 255).astype("uint8"), "RGBA")

    streak_specs = {"brake": (brake, 150, 26.0, 0.72, 11),
                    "indicator_left": (left, 96, 20.0, 0.62, 23),
                    "indicator_right": (right, 96, 20.0, 0.62, 37)}
    for name, (entry, length, width_px, alpha, seed) in streak_specs.items():
        image = outside_car(streak_image(CANVAS, entry["bbox"],
                                         entry["colour"], length, width_px,
                                         alpha, seed))
        box = image.getchannel("A").getbbox() or (0, 0, 1, 1)
        box = (max(0, box[0] - 2), max(0, box[1] - 2),
               min(width, box[2] + 2), min(height, box[3] + 2))
        image = image.crop(box)
        path = os.path.join(args.out, f"horizon_v5_streak_{name}.png")
        image.save(path)
        report["assets"][f"streak_{name}"] = {
            "file": os.path.relpath(path, REPO), "box": list(box),
            "colour": entry["colour"], "length_px": length}
        print(f"[v5-motion] streak_{name:16s} {image.size} at {box[:2]}")

    wake = outside_car(wake_image(CANVAS, car_body, (96, 196, 226), 5))
    wake_box = wake.getchannel("A").getbbox() or (0, 0, 1, 1)
    wake_box = (max(0, wake_box[0] - 4), max(0, wake_box[1] - 4),
                min(width, wake_box[2] + 4), min(height, wake_box[3] + 4))
    wake = wake.crop(wake_box)
    wake_path = os.path.join(args.out, "horizon_v5_wake.png")
    wake.save(wake_path)
    report["assets"]["wake"] = {"file": os.path.relpath(wake_path, REPO),
                                "box": list(wake_box),
                                "colour": [96, 196, 226]}
    print(f"[v5-motion] wake {wake.size} at {wake_box[:2]}")

    tile_h = 160
    flow = roadflow_tile((width, tile_h), 91)
    flow_path = os.path.join(args.out, "horizon_v5_roadflow.png")
    flow.save(flow_path)
    report["assets"]["roadflow"] = {
        "file": os.path.relpath(flow_path, REPO), "tile": [width, tile_h],
        "box": [0, CANVAS[1] - tile_h, width, CANVAS[1]],
        "why": "translated and wrapped by the runtime; the level curve sets how "
               "fast and how visible"}
    print(f"[v5-motion] roadflow tile {flow.size}")

    wheel_report = {}
    car_pass = os.path.join(args.vehicle, "car", "base", "000.png")
    framing_path = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                                "horizon_v5_environment.json")
    wheel_boxes = None
    if os.path.isfile(framing_path):
        try:
            entries = json.load(open(framing_path)).get("wheel_boxes_px", [])
            if entries:
                wheel_boxes = entries[0]["boxes"]
        except (OSError, ValueError):
            wheel_boxes = None
    if wheel_boxes is None:
        # Fall back to the geometry the car render itself shows: a wheel
        # occupies the lower quarter of the car box, front and rear.
        wheel_boxes = [[car_body[0] + (car_body[2] - car_body[0]) * 0.52,
                        car_body[1] + (car_body[3] - car_body[1]) * 0.06,
                        car_body[0] + (car_body[2] - car_body[0]) * 0.98,
                        car_body[3]],
                       [car_body[0] + (car_body[2] - car_body[0]) * 0.05,
                        car_body[1] + (car_body[3] - car_body[1]) * 0.46,
                        car_body[0] + (car_body[2] - car_body[0]) * 0.52,
                        car_body[3]]]
    for name, degrees in motion.WHEEL_LEVELS:
        overlay = wheel_overlays(car_pass, wheel_boxes, degrees)
        box = overlay.getchannel("A").getbbox() or (0, 0, 1, 1)
        box = (max(0, box[0] - 2), max(0, box[1] - 2),
               min(width, box[2] + 2), min(height, box[3] + 2))
        overlay = overlay.crop(box)
        path = os.path.join(args.out, f"horizon_v5_wheel_{name}.png")
        overlay.save(path)
        wheel_report[name] = {"file": os.path.relpath(path, REPO),
                              "box": list(box), "spin_deg": degrees}
        print(f"[v5-motion] wheel_{name:6s} spin {degrees:5.1f} deg  "
              f"{overlay.size} at {box[:2]}")
    report["assets"]["wheels"] = wheel_report
    report["wheel_boxes_px"] = [[round(v, 1) for v in box]
                                for box in wheel_boxes]

    report["motion"] = motion.definition()["levels_at_speeds"]
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"[v5-motion] report {os.path.relpath(args.report, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
