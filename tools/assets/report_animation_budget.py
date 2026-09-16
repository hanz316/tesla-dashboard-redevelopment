#!/usr/bin/env python3
"""Part 15: compare three decode strategies for one animation.

    A) full canvas      - decode the whole 769x531 (or larger) frame
    B) alpha crop       - decode only the union alpha bbox of the sequence
    C) difference crop  - decode only the per-frame dirty region

All three use the same device model as check_budget.py so the numbers are
directly comparable. Every device number here is an ESTIMATE: the real T113
figure stays UNKNOWN UNTIL DEVICE TEST.

Usage:
    python3 tools/assets/report_animation_budget.py \\
        --full assets/rendered/door_fl_v3/600_30/open \\
        --delta assets/rendered/door_fl_v3/600_30/open_delta \\
        --label 600/30
"""

import argparse
import json
import os
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow required: pip3 install pillow")

import numpy as np

A7_DECODE_FACTOR = 30.0
HOST_MS_PER_PX = 0.227 / (237.0 * 351.0)
FRAME_BUDGET_MS = 33.3


def frame_files(directory):
    return [os.path.join(directory, n) for n in sorted(os.listdir(directory))
            if n.lower().endswith(".png")]


def device_ms(width, height):
    return HOST_MS_PER_PX * width * height * A7_DECODE_FACTOR


def alpha_union(files):
    lo_x = lo_y = 10 ** 9
    hi_x = hi_y = -1
    for path in files:
        with Image.open(path) as img:
            bbox = img.convert("RGBA").getchannel("A").getbbox()
        if bbox is None:
            continue
        lo_x = min(lo_x, bbox[0])
        lo_y = min(lo_y, bbox[1])
        hi_x = max(hi_x, bbox[2])
        hi_y = max(hi_y, bbox[3])
    if hi_x < 0:
        return None
    return (lo_x, lo_y, hi_x - lo_x, hi_y - lo_y)


def summarise(name, widths, heights, bytes_per_frame, total_bytes, frames,
              budget_ms):
    avg_w = sum(widths) / float(len(widths)) if widths else 0.0
    avg_h = sum(heights) / float(len(heights)) if heights else 0.0
    peak_w = max(widths) if widths else 0
    peak_h = max(heights) if heights else 0
    avg_px = avg_w * avg_h
    peak_px = peak_w * peak_h
    avg_dec = device_ms(avg_w, avg_h)
    return {
        "name": name,
        "frames": frames,
        "avg_dims": (round(avg_w, 1), round(avg_h, 1)),
        "peak_dims": (peak_w, peak_h),
        "avg_px_per_frame": round(avg_px, 1),
        "peak_px_per_frame": round(peak_px, 1),
        "avg_decoded_mb": round(avg_px * 4 / 1024 / 1024, 3),
        "peak_decoded_mb": round(peak_px * 4 / 1024 / 1024, 3),
        "avg_png_bytes": round(sum(bytes_per_frame) / float(len(bytes_per_frame)))
        if bytes_per_frame else 0,
        "total_png_bytes": total_bytes,
        "avg_decode_ms": round(avg_dec, 2),
        "peak_decode_ms": round(device_ms(peak_w, peak_h), 2),
        "avg_decode_share": round(avg_dec / budget_ms, 4),
        "budget_ms": budget_ms,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", required=True)
    ap.add_argument("--delta", required=True)
    ap.add_argument("--label", default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--budget-ms", type=float, default=FRAME_BUDGET_MS,
                    help="per-frame budget the share column is measured "
                         "against (33.3 for 30 fps, 16.7 for 60 fps)")
    args = ap.parse_args()

    files = frame_files(args.full)
    if not files:
        sys.exit(f"no frames in {args.full}")
    with Image.open(files[0]) as img:
        canvas_w, canvas_h = img.size
    full_bytes = [os.path.getsize(p) for p in files]

    budget = args.budget_ms
    a = summarise("A_full_canvas", [canvas_w] * len(files),
                  [canvas_h] * len(files), full_bytes, sum(full_bytes),
                  len(files), budget)

    bbox = alpha_union(files)
    if bbox is None:
        sys.exit("sequence is fully transparent")
    bw, bh = bbox[2], bbox[3]
    # One crop covers the whole animation, so every frame pays the union cost.
    b = summarise("B_alpha_crop", [bw] * len(files), [bh] * len(files),
                  full_bytes, sum(full_bytes), len(files), budget)

    with open(os.path.join(args.delta, "animation.json")) as fh:
        manifest = json.load(fh)
    recs = [r for r in manifest["frames"] if not r.get("empty")]
    dw = [r["width"] for r in recs]
    dh = [r["height"] for r in recs]
    dbytes = [os.path.getsize(os.path.join(args.delta, "frames",
                                           f"{r['frame']:03d}.png"))
              for r in recs]
    c = summarise("C_difference_crop", dw, dh, dbytes, sum(dbytes), len(recs),
                  budget)

    label = args.label or os.path.basename(os.path.dirname(args.full.rstrip("/")))
    print(f"=== animation budget [{label}] canvas {canvas_w}x{canvas_h}, "
          f"{len(files)} frames, budget {budget:.1f} ms/frame ===")
    header = (f"{'strategy':20s} {'avg dims':>12s} {'peak dims':>12s} "
              f"{'avg px/frame':>13s} {'decoded MB':>11s} {'PNG KB/frame':>13s} "
              f"{'est ms/frame':>13s} {'% of budget':>12s}")
    print(header)
    print("-" * len(header))
    for row in (a, b, c):
        print(f"{row['name']:20s} "
              f"{row['avg_dims'][0]:5.0f}x{row['avg_dims'][1]:<6.0f} "
              f"{row['peak_dims'][0]:5d}x{row['peak_dims'][1]:<6d} "
              f"{row['avg_px_per_frame']:13.0f} "
              f"{row['avg_decoded_mb']:11.3f} "
              f"{row['avg_png_bytes']/1024:13.1f} "
              f"{row['avg_decode_ms']:13.1f} "
              f"{row['avg_decode_share']*100:10.0f}%")

    saved_px = 1.0 - (c["avg_px_per_frame"] / a["avg_px_per_frame"])
    saved_ms = 1.0 - (c["avg_decode_ms"] / a["avg_decode_ms"])
    saved_bytes = 1.0 - (c["avg_png_bytes"] / float(a["avg_png_bytes"]))
    print()
    print(f"[{label}] difference crop vs full canvas: "
          f"pixels -{saved_px*100:.1f}% | "
          f"est decode -{saved_ms*100:.1f}% | "
          f"PNG bytes -{saved_bytes*100:.1f}%")
    print(f"[{label}] ESTIMATED ONLY - real device numbers are "
          f"UNKNOWN UNTIL DEVICE TEST")

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump({"label": label, "A": a, "B": b, "C": c,
                       "saved_px_pct": round(saved_px * 100, 1),
                       "saved_decode_pct": round(saved_ms * 100, 1),
                       "saved_png_pct": round(saved_bytes * 100, 1)},
                      fh, indent=2)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
