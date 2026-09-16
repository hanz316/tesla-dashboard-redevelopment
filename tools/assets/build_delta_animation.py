#!/usr/bin/env python3
"""Build a delta (dirty-region) animation from full-frame Blender renders.

Parts 12-14 of the V3 task.

The benchmark result that motivated this: a full transparent canvas decode is
purely wasteful. At 800 px the car occupies 30% of the canvas, and decoding the
whole canvas for every frame costs 179% of the 30 fps budget on the A7-class
device, while decoding only the pixels that actually changed costs far less.

What this tool produces for one animation:

    base.png          the closed vehicle, full canvas, rendered once
    frames/NNN.png    ONLY the rectangle that differs from base, cropped out
                      of the real full frame (so it is a complete, correct
                      local picture, not just "the door object")
    animation.json    per-frame x/y/width/height/anchor + verification + budget

Reconstruction is deliberately trivial and exact: the runtime draws base once
and then does a straight RECTANGLE REPLACEMENT (not src-over compositing) of
the per-frame crop. src-over would be wrong, because a pixel that became
transparent must be able to erase the base pixel underneath it. Because the
crop is taken from the original render, replacement reproduces the original
frame exactly - and this tool verifies that numerically.

Usage:
    python3 tools/assets/build_delta_animation.py \\
        --base assets/rendered/door_fl_v3/600_30/open/000.png \\
        --frames assets/rendered/door_fl_v3/600_30/open \\
        --out assets/rendered/door_fl_v3/600_30/open_delta \\
        --id door_fl_open --fps 30 --duration-ms 620
"""

import argparse
import json
import os
import re
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow required: pip3 install pillow")

import numpy as np

# Same device model as tools/assets/check_budget.py, so the numbers are
# comparable across tools. See docs/RENDERING_CAPABILITY_AUDIT.md section 11.
A7_DECODE_FACTOR = 30.0
HOST_MS_PER_PX = 0.227 / (237.0 * 351.0)
FRAME_BUDGET_MS = 33.3


def load_rgba(path):
    with Image.open(path) as img:
        return np.array(img.convert("RGBA"), dtype=np.int16)


def frame_files(directory):
    pat = re.compile(r"^(\d+)\.(png|jpg|jpeg)$", re.I)
    found = []
    for name in sorted(os.listdir(directory)):
        m = pat.match(name)
        if m:
            found.append((int(m.group(1)), os.path.join(directory, name)))
    return [p for _, p in sorted(found)]


def changed_bbox(base, frame, threshold):
    """Bounding box of every pixel that differs, alpha included."""
    delta = np.abs(frame - base).max(axis=2)
    rows = np.any(delta > threshold, axis=1)
    cols = np.any(delta > threshold, axis=0)
    if not rows.any():
        return None
    ys = np.where(rows)[0]
    xs = np.where(cols)[0]
    return int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1


def expand_and_clamp(bbox, padding, width, height):
    x0, y0, x1, y1 = bbox
    return (max(0, x0 - padding), max(0, y0 - padding),
            min(width, x1 + padding), min(height, y1 + padding))


def decode_ms(width, height):
    host = HOST_MS_PER_PX * width * height
    return host * A7_DECODE_FACTOR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True,
                    help="full-canvas frame the animation starts from")
    ap.add_argument("--frames", required=True,
                    help="directory of full-canvas frames")
    ap.add_argument("--out", required=True)
    ap.add_argument("--id", default=None)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duration-ms", type=int, default=None)
    ap.add_argument("--padding", type=int, default=6,
                    help="safe padding in px around the changed region")
    ap.add_argument("--threshold", type=int, default=4,
                    help="per-channel difference (0-255) that counts as "
                         "changed. 0 gives a byte-exact reconstruction but "
                         "inflates the rectangle with 1-3 level renderer "
                         "noise; 4 is imperceptible and typically shrinks "
                         "the dirty region by ~2/3. The verification block "
                         "always records the resulting worst-case error.")
    args = ap.parse_args()

    base = load_rgba(args.base)
    height, width = base.shape[:2]
    files = frame_files(args.frames)
    if not files:
        sys.exit(f"no frames found in {args.frames}")

    out_frames = os.path.join(args.out, "frames")
    os.makedirs(out_frames, exist_ok=True)
    Image.fromarray(base.astype("uint8")).save(os.path.join(args.out, "base.png"))

    duration_ms = args.duration_ms
    if duration_ms is None:
        duration_ms = int(round(1000.0 * len(files) / max(args.fps, 1)))

    records = []
    reconstructed_ok = True
    worst_diff = 0
    worst_mismatch = 0
    delta_bytes = 0
    full_bytes = 0
    areas = []
    decode_total = 0.0
    peak_decode = 0.0

    for index, path in enumerate(files):
        frame = load_rgba(path)
        if frame.shape != base.shape:
            sys.exit(f"frame size mismatch: {path} {frame.shape} vs "
                     f"{base.shape}")
        full_bytes += os.path.getsize(path)

        bbox = changed_bbox(base, frame, args.threshold)
        record = {"frame": index, "x": 0, "y": 0, "width": 0, "height": 0,
                  "anchor_x": 0, "anchor_y": 0, "duration_ms": duration_ms,
                  "empty": bbox is None}

        if bbox is not None:
            x0, y0, x1, y1 = expand_and_clamp(bbox, args.padding,
                                              width, height)
            crop = frame[y0:y1, x0:x1]
            crop_path = os.path.join(out_frames, f"{index:03d}.png")
            Image.fromarray(crop.astype("uint8")).save(crop_path)
            delta_bytes += os.path.getsize(crop_path)
            areas.append(crop.shape[0] * crop.shape[1])
            this_decode = decode_ms(crop.shape[1], crop.shape[0])
            decode_total += this_decode
            peak_decode = max(peak_decode, this_decode)

            record.update({
                "x": x0, "y": y0,
                "width": crop.shape[1], "height": crop.shape[0],
                # Anchor is where the crop is blitted on the base canvas.
                # Same numbers as x/y here on purpose: the metadata contract
                # keeps them separate so a future packed atlas can place the
                # cell somewhere else in the sheet.
                "anchor_x": x0, "anchor_y": y0,
                "raw_bbox": [bbox[0], bbox[1], bbox[2], bbox[3]],
            })

            # Verify by actually rebuilding the frame the runtime way.
            rebuilt = base.copy()
            rebuilt[y0:y1, x0:x1] = crop
            diff = np.abs(rebuilt - frame).max(axis=2)
            mismatched = int((diff > 0).sum())
            if mismatched:
                reconstructed_ok = False
            worst_diff = max(worst_diff, int(diff.max()))
            worst_mismatch = max(worst_mismatch, mismatched)

        records.append(record)

    covered = sum(areas)
    peak = max(areas) if areas else 0
    avg_area = covered / float(len(areas)) if areas else 0.0
    frames_with_change = len(areas)

    manifest = {
        "id": args.id or os.path.basename(os.path.normpath(args.out)),
        "kind": "delta_animation",
        "base": "base.png",
        "canvas": {"width": width, "height": height},
        "fps": args.fps,
        "duration_ms": duration_ms,
        "padding": args.padding,
        "threshold": args.threshold,
        "compositing": "rectangle_replacement",
        "frames": records,
        "stats": {
            "frame_count": len(records),
            "frames_with_change": frames_with_change,
            "avg_region_px": round(avg_area, 1),
            "peak_region_px": peak,
            "canvas_px": width * height,
            "avg_region_share_of_canvas": round(
                avg_area / float(width * height), 4) if covered else 0.0,
            "avg_png_bytes": round(delta_bytes / float(frames_with_change), 1)
            if frames_with_change else 0.0,
            "total_png_bytes": delta_bytes,
            "full_frame_avg_png_bytes": round(full_bytes / float(len(files)), 1),
            "avg_decode_ms": round(
                decode_total / frames_with_change, 2) if frames_with_change
            else 0.0,
            "peak_decode_ms": round(peak_decode, 2),
            "avg_decode_share_of_30fps": round(
                (decode_total / frames_with_change) / FRAME_BUDGET_MS, 4)
            if frames_with_change else 0.0,
        },
        "verification": {
            "method": "rebuild = base; rebuild[y0:y1, x0:x1] = crop",
            "pixel_equal": reconstructed_ok,
            "worst_mismatched_px": worst_mismatch,
            "worst_channel_diff": worst_diff,
        },
    }

    with open(os.path.join(args.out, "animation.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    stats = manifest["stats"]
    print(f"[delta] {manifest['id']}: {len(records)} frames, "
          f"{frames_with_change} with change")
    print(f"[delta] canvas {width}x{height} | avg region "
          f"{stats['avg_region_px']:.0f} px "
          f"({stats['avg_region_share_of_canvas']*100:.1f}% of canvas) | "
          f"peak {peak} px")
    print(f"[delta] PNG/frame full={stats['full_frame_avg_png_bytes']/1024:.1f}KB "
          f"delta={stats['avg_png_bytes']/1024:.1f}KB")
    print(f"[delta] verification: pixel_equal={reconstructed_ok} "
          f"worst_mismatch={worst_mismatch}px worst_diff={worst_diff}")
    print(f"[delta] -> {os.path.join(args.out, 'animation.json')}")
    return 0 if reconstructed_ok else 1


if __name__ == "__main__":
    sys.exit(main())
