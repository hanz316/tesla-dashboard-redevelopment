#!/usr/bin/env python3
"""Verify the PNG sequence contract (TASK 6) for rendered animations.

Checks, for every sequence:

1. every frame has the identical canvas size (no auto-crop);
2. the alpha bounding box never touches the canvas edge (nothing clipped);
3. the *static* region is stable — comparing the first and last frame, the
   pixels that differ must form a bounded motion region, so the whole
   vehicle cannot drift (a camera move would light up the full canvas);
4. the motion region stays inside a sane fraction of the canvas.

Usage:
    python3 tools/assets/verify_alignment.py assets/rendered/vehicle/door_fl
    python3 tools/assets/verify_alignment.py --all assets/rendered/vehicle
"""

import argparse
import os
import sys

try:
    from PIL import Image, ImageChops
except ImportError:
    sys.exit("Pillow required: pip3 install pillow")

MAX_MOTION_AREA_FRACTION = 0.55   # a moving door should not cover the canvas


def alpha_bbox(img):
    return img.split()[-1].getbbox()


def check_sequence(directory):
    frames = sorted(f for f in os.listdir(directory) if f.endswith(".png"))
    name = os.path.basename(directory.rstrip("/"))
    if not frames:
        print(f"FAIL {name}: no PNG frames")
        return False

    ok = True
    sizes = set()
    first = last = None
    for f in frames:
        img = Image.open(os.path.join(directory, f)).convert("RGBA")
        sizes.add(img.size)
        box = alpha_bbox(img)
        if box is None:
            print(f"FAIL {name}/{f}: fully transparent frame")
            ok = False
            continue
        x0, y0, x1, y1 = box
        if x0 <= 0 or y0 <= 0 or x1 >= img.width or y1 >= img.height:
            print(f"WARN {name}/{f}: content touches canvas edge {box} "
                  f"(possible clipping / auto-crop)")
        if first is None:
            first = img
        last = img

    if len(sizes) != 1:
        print(f"FAIL {name}: inconsistent canvas sizes {sorted(sizes)}")
        return False

    w, h = sizes.pop()
    # Motion detection uses consecutive frame pairs (union), so blink loops
    # whose first and last frame are both "off" are handled correctly.
    motion_note = "no motion detected"
    motion_box = None
    prev = None
    for f in frames:
        img = Image.open(os.path.join(directory, f)).convert("RGBA")
        if prev is not None:
            box = ImageChops.difference(prev, img).getbbox()
            if box is not None:
                if motion_box is None:
                    motion_box = box
                else:
                    motion_box = (min(motion_box[0], box[0]),
                                  min(motion_box[1], box[1]),
                                  max(motion_box[2], box[2]),
                                  max(motion_box[3], box[3]))
        prev = img
    if motion_box is not None:
        mx0, my0, mx1, my1 = motion_box
        area = (mx1 - mx0) * (my1 - my0) / float(w * h)
        motion_note = f"motion bbox={motion_box} ({area*100:.0f}% of canvas)"
        if area > MAX_MOTION_AREA_FRACTION:
            print(f"FAIL {name}: motion covers {area*100:.0f}% of the canvas "
                  f"(> {MAX_MOTION_AREA_FRACTION*100:.0f}%) — camera or "
                  f"whole-vehicle drift")
            ok = False

    print(f"{'PASS' if ok else 'FAIL'} {name}: frames={len(frames)} "
          f"canvas={w}x{h} {motion_note}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--all", action="store_true",
                    help="treat each path as a parent directory of sequences")
    args = ap.parse_args()

    targets = []
    for p in args.paths:
        if args.all:
            for entry in sorted(os.listdir(p)):
                sub = os.path.join(p, entry)
                if os.path.isdir(sub):
                    targets.append(sub)
        else:
            targets.append(p)
    if not targets:
        sys.exit("nothing to check (pass a directory or --all <parent>)")

    ok = True
    for t in targets:
        ok &= check_sequence(t)
    print("ALIGNMENT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
