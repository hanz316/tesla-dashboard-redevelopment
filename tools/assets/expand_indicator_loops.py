#!/usr/bin/env python3
"""Expand the indicator on/off renders into the 12-frame loops the contract asks
for.

`assets/manifest.json` declares indicator_left / indicator_right / hazard as
12-frame loops at 12 fps. A turn signal loop is a two-state pattern (lit for
half the cycle, dark for the other half), so it needs two renders and eleven
copies - not twelve renders. The files are written as a real 12-frame sequence
so the runtime and the previewer need no special case.

Usage:
    python3 tools/assets/expand_indicator_loops.py --assets assets/rendered/vehicle
"""

import argparse
import os
import shutil
import sys

LOOPS = ("indicator_left", "indicator_right", "hazard")
FRAMES = 12
LIT_FRAMES = 6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", required=True)
    args = ap.parse_args()
    base = os.path.join(args.assets, "base", "000.png")
    if not os.path.exists(base):
        sys.exit(f"missing base frame: {base}")
    written = {}
    for name in LOOPS:
        directory = os.path.join(args.assets, name)
        lit = os.path.join(directory, "000.png")
        if not os.path.exists(lit):
            sys.exit(f"missing lit frame for {name}: {lit}")
        for i in range(1, FRAMES):
            dst = os.path.join(directory, f"{i:03d}.png")
            src = lit if i < LIT_FRAMES else base
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copyfile(src, dst)
        written[name] = FRAMES
        print(f"[loops] {name}: {FRAMES} frames, "
              f"{LIT_FRAMES} lit / {FRAMES - LIT_FRAMES} dark")
    return 0


if __name__ == "__main__":
    sys.exit(main())
