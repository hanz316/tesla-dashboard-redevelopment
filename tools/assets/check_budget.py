#!/usr/bin/env python3
"""Validate image asset budgets against the T113 device constraints.

Encodes the numbers from docs/RENDERING_CAPABILITY_AUDIT.md so an asset
that would blow the RAM or frame budget fails early (usable in CI).

Usage:
  python3 tools/assets/check_budget.py assets/vehicle/base.png
  python3 tools/assets/check_budget.py --sequence assets/vehicle/door_fl_open
"""

import argparse
import os
import re
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow required: pip3 install pillow")

# Device budget (see audit section 11).
DEVICE_RAM_AVAILABLE_MB = 183.0
MAX_SINGLE_ASSET_DECODED_MB = 12.0   # any one asset when fully decoded
MAX_SEQUENCE_DECODED_MB = 4.0        # one sprite sequence, fully decoded
MAX_UI_RESIDENT_RAM_MB = 40.0        # total decoded UI assets at runtime
A7_DECODE_FACTOR = 30.0              # A7 approx slower than Apple Silicon core
FRAME_BUDGET_MS = 33.3               # 30 fps
MAX_DECODE_SHARE = 0.30              # one animation should stay under 30%


def check_image(path, label=None):
    label = label or os.path.basename(path)
    img = Image.open(path)
    w, h = img.size
    decoded_mb = w * h * 4 / 1024 / 1024
    print(f"{label}: {w}x{h} mode={img.mode} "
          f"png={os.path.getsize(path)/1024:.1f}KB decoded={decoded_mb:.2f}MB")
    ok = True
    if decoded_mb > MAX_SINGLE_ASSET_DECODED_MB:
        print(f"  FAIL decoded {decoded_mb:.2f}MB > "
              f"{MAX_SINGLE_ASSET_DECODED_MB}MB single-asset budget")
        ok = False
    return ok, decoded_mb, (w, h)


def check_sequence(directory, prefix=""):
    files = []
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)\.(png|jpg|jpeg)$", re.I)
    for f in sorted(os.listdir(directory)):
        if pat.match(f):
            files.append(os.path.join(directory, f))
    if not files:
        print(f"FAIL no frames matched in {directory} (prefix={prefix!r})")
        return False

    first = Image.open(files[0])
    w, h = first.size
    n = len(files)
    per_frame_mb = w * h * 4 / 1024 / 1024
    total_mb = per_frame_mb * n
    first_bytes = os.path.getsize(files[0])
    # Host measurement baseline: ~0.227 ms for 237x351; scale by pixel count.
    baseline_px = 237 * 351
    host_ms = 0.227 * (w * h) / baseline_px
    device_ms = host_ms * A7_DECODE_FACTOR
    share = device_ms / FRAME_BUDGET_MS

    print(f"sequence {os.path.basename(directory)}: frames={n} frame={w}x{h}")
    print(f"  decoded per frame = {per_frame_mb:.3f} MB")
    print(f"  decoded all frames = {total_mb:.2f} MB")
    print(f"  device decode estimate = {device_ms:.1f} ms/frame "
          f"({share*100:.0f}% of 30fps budget)")
    print(f"  storage = {n*first_bytes/1024:.1f} KB")

    ok = True
    if total_mb > MAX_SEQUENCE_DECODED_MB:
        print(f"  NOTE full-decode {total_mb:.2f}MB > "
              f"{MAX_SEQUENCE_DECODED_MB}MB -> must stream frames, do not "
              f"cache the whole sequence")
    if share > MAX_DECODE_SHARE:
        print(f"  WARN decode uses {share*100:.0f}% of the 30fps budget "
              f"(limit {MAX_DECODE_SHARE*100:.0f}%): reduce frame size/count "
              f"or lower the animation fps")
        ok = False
    if per_frame_mb * 2 > MAX_UI_RESIDENT_RAM_MB:
        print(f"  FAIL resident budget unrealistic for {w}x{h}")
        ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--sequence", action="store_true",
                    help="treat each path as a directory of frames")
    ap.add_argument("--prefix", default="")
    args = ap.parse_args()

    all_ok = True
    for p in args.paths:
        if args.sequence or os.path.isdir(p):
            all_ok &= check_sequence(p, args.prefix)
        else:
            ok, _, _ = check_image(p)
            all_ok &= ok
    print("BUDGET:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
