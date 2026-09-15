#!/usr/bin/env python3
"""Build a labelled contact sheet from a grid of rendered images.

Development aid only — the sheet is never a runtime asset.

Usage:
    python3 tools/assets/make_comparison_sheet.py \
        --out sheet.png --cell 620x430 --cols 3 \
        --image "Silver 01 / CAM A=path1.png" \
        --image "Silver 01 / CAM B=path2.png" ...
"""

import argparse
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow required: pip3 install pillow")

FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--image", action="append", required=True,
                    help="LABEL=PATH")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--cell", default="620x430")
    ap.add_argument("--bg", default="#0A0E12")
    ap.add_argument("--label-height", type=int, default=34)
    args = ap.parse_args()

    cw, ch = (int(v) for v in args.cell.lower().split("x"))
    entries = []
    for item in args.image:
        if "=" not in item:
            sys.exit(f"--image must be LABEL=PATH, got: {item}")
        label, path = item.split("=", 1)
        entries.append((label, path))

    rows = (len(entries) + args.cols - 1) // args.cols
    pad = 16
    sheet_w = pad + args.cols * (cw + pad)
    sheet_h = pad + rows * (ch + args.label_height + pad)
    sheet = Image.new("RGB", (sheet_w, sheet_h), args.bg)
    draw = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype(FONT, 20)
    except Exception:
        font = ImageFont.load_default()

    for index, (label, path) in enumerate(entries):
        row, col = divmod(index, args.cols)
        x = pad + col * (cw + pad)
        y = pad + row * (ch + args.label_height + pad)

        img = Image.open(path).convert("RGBA")
        scale = min(cw / img.width, ch / img.height)
        img = img.resize((max(1, int(img.width * scale)),
                          max(1, int(img.height * scale))), Image.LANCZOS)
        # Composite over the sheet background so transparency reads correctly.
        cell = Image.new("RGB", (cw, ch), args.bg)
        cell.paste(img, ((cw - img.width) // 2, (ch - img.height) // 2), img)
        sheet.paste(cell, (x, y))
        draw.rectangle([x, y, x + cw, y + ch], outline="#1E2A36", width=1)
        draw.text((x + 6, y + ch + 6), label, font=font, fill="#D8E2EC")

    sheet.save(args.out)
    print(f"[sheet] {len(entries)} cells -> {args.out} ({sheet.size[0]}x{sheet.size[1]})")


if __name__ == "__main__":
    main()
