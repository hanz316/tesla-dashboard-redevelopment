#!/usr/bin/env python3
"""Part H/I: check each lighting candidate at three display sizes.

Judging a vehicle material only on a full-size Blender render is how a
pipeline ends up with paint that reads as plastic at the size the driver
actually sees. Every candidate is therefore emitted at:

    full      the full render, downscaled for review
    600px     the whole frame scaled so the CAR is 600 px wide - this is the
              size the vehicle occupies in the dashboard, and it is produced by
              downscaling the render, which is exactly what the shipping asset
              pipeline does
    horizon   1:1 crop out of the real 1920x480 Horizon composite, so nothing
              is resampled and you see the true pixels

Usage:
    python3 tools/assets/build_photoreal_comparison.py
"""

import os
import subprocess
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow required")

import numpy as np

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VARIANTS = [
    ("v3", "V3 CURRENT (reflection cards)", "v3_silver.png"),
    ("hdri", "HDRI ONLY", "hdri_silver.png"),
    ("hybrid", "HDRI HYBRID", "hybrid_silver.png"),
]
SRC = os.path.join(REPO_ROOT, "assets", "rendered", "photoreal")
OUT = os.path.join(REPO_ROOT, "assets", "rendered", "photoreal", "checks")
SCENE = os.path.join(REPO_ROOT, "scenes", "horizon_v1.scene")
# Same framing the V2/V3 Horizon previews used, so this is directly
# comparable with the earlier review images.
VEHICLE_BOX = "864x597@582,-93"


def car_bbox(img):
    bbox = img.getchannel("A").getbbox()
    return bbox or (0, 0, img.width, img.height)


def resize_rgba(img, size):
    """Resize RGBA in PREMULTIPLIED space.

    Resampling a non-premultiplied RGBA image lets Lanczos ringing inject
    colour into almost-transparent edge pixels: downscaling the V3 render this
    way produced pure-white 255 pixels along the silhouette that do not exist
    in the source. Premultiplying first removes that - and since this is the
    same downscale the shipping asset pipeline performs, it is not a cosmetic
    detail.

    The resize itself runs on float32 channels: quantising the premultiplied
    values to 8 bit and then dividing by a small alpha re-amplifies the
    rounding error and is worse than doing nothing (measured: 77 -> 1119
    clipped pixels).
    """
    arr = np.asarray(img).astype(np.float32)
    alpha = arr[..., 3:4] / 255.0
    premul = np.clip(arr[..., :3] * alpha, 0.0, 255.0)

    def resize_plane(plane):
        return np.asarray(
            Image.fromarray(plane.astype(np.float32)).resize(
                size, Image.LANCZOS), dtype=np.float32)

    planes = [resize_plane(premul[..., i]) for i in range(3)]
    a_small = resize_plane(arr[..., 3])
    rgb = np.stack(planes, axis=2)
    ratio = np.clip(a_small, 0.0, 255.0) / 255.0
    rgb = np.where(ratio[..., None] > 1e-4,
                   rgb / np.maximum(ratio[..., None], 1e-4), 0.0)
    # Downscaling must never introduce a value brighter than the source.
    # Dividing by a tiny alpha on a silhouette edge can push a near-black
    # premultiplied value back up towards 255; clamping to the source peak
    # makes "the pipeline added no clipping" a guarantee instead of a hope.
    visible = arr[..., 3] > 0
    src_peak = float(arr[..., :3][visible].max()) if visible.any() else 255.0
    rgb = np.minimum(rgb, src_peak)
    out = np.concatenate([np.clip(rgb, 0.0, 255.0),
                          np.clip(a_small, 0.0, 255.0)[..., None]], axis=2)
    return Image.fromarray(out.astype(np.uint8))


def main():
    os.makedirs(OUT, exist_ok=True)
    results = {}
    for key, label, filename in VARIANTS:
        path = os.path.join(SRC, filename)
        if not os.path.isfile(path):
            sys.exit(f"missing render: {path}")
        img = Image.open(path).convert("RGBA")
        x0, y0, x1, y1 = car_bbox(img)
        car_w, car_h = x1 - x0, y1 - y0

        # 1. full frame, review size
        full = resize_rgba(img, (img.width // 2, img.height // 2))
        full.save(os.path.join(OUT, f"{key}_full.png"))

        # 2. the car at exactly 600 px wide
        scale = 600.0 / car_w
        small = resize_rgba(img, (max(1, int(img.width * scale)),
                                  max(1, int(img.height * scale))))
        small.save(os.path.join(OUT, f"{key}_600px.png"))

        # 3. real Horizon composite, then a 1:1 crop around the car
        horizon_name = f"horizon_photoreal_{key}"
        subprocess.run(
            ["python3", os.path.join(REPO_ROOT, "tools", "preview",
                                     "scene_preview.py"),
             "--scene", SCENE, "--state", "driving",
             "--vehicle-image", path, "--vehicle-box", VEHICLE_BOX,
             "--out-name", horizon_name, "--out", OUT],
            check=True, capture_output=True)
        horizon_path = os.path.join(OUT, horizon_name + ".png")
        horizon = Image.open(horizon_path).convert("RGB")
        crop_w, crop_h = 900, 480
        cx = 960
        box = (max(0, min(1920 - crop_w, cx - crop_w // 2)), 0,
               max(0, min(1920 - crop_w, cx - crop_w // 2)) + crop_w, crop_h)
        cropped = horizon.crop(box)
        cropped.save(os.path.join(OUT, f"{key}_horizon.png"))

        results[key] = {
            "label": label,
            "car_px": (car_w, car_h),
            "full": os.path.join(OUT, f"{key}_full.png"),
            "small": os.path.join(OUT, f"{key}_600px.png"),
            "horizon": os.path.join(OUT, f"{key}_horizon.png"),
            "horizon_full": horizon_path,
        }
        print(f"[checks] {key:7s} car={car_w}x{car_h} -> "
              f"{key}_full.png / {key}_600px.png / {key}_horizon.png")
    return results


def build_sheets(results):
    # Part I: three columns, full-vehicle crop + Horizon actual size.
    cmd = ["python3", os.path.join(REPO_ROOT, "tools", "assets",
                                   "make_comparison_sheet.py"),
           "--out", os.path.join(SRC, "vehicle_material_photoreal_comparison.png"),
           "--cols", "3", "--cell", "620x430"]
    for row in ("full", "horizon"):
        for key, label, _ in VARIANTS:
            suffix = "full vehicle" if row == "full" else "Horizon actual size"
            cmd += ["--image", f"{label} - {suffix}={results[key][row]}"]
    print(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())

    # Separate sheet for the Part H size check (the car at 600 px).
    cmd = ["python3", os.path.join(REPO_ROOT, "tools", "assets",
                                   "make_comparison_sheet.py"),
           "--out", os.path.join(SRC, "vehicle_material_sizecheck_600px.png"),
           "--cols", "3", "--cell", "620x430"]
    for key, label, _ in VARIANTS:
        cmd += ["--image", f"{label} - car at 600px wide={results[key]['small']}"]
    print(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())


if __name__ == "__main__":
    build_sheets(main())
