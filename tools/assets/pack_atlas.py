#!/usr/bin/env python3
"""Pack a PNG frame sequence into a texture atlas + JSON metadata.

Offline half of the animation pipeline: Blender (or any renderer) emits
transparent PNG frames, this tool packs them into an atlas that the
EasyUI runtime can load as a single decoded bitmap.

Usage:
  python3 tools/assets/pack_atlas.py --input DIR --prefix NAME --out DIR
"""
import argparse, json, os, re, sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow required: pip3 install pillow")


def collect(input_dir, prefix, ext):
    files = []
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)\.{ext}$") if prefix else None
    for f in sorted(os.listdir(input_dir)):
        if pat and not pat.match(f):
            continue
        if prefix is None and not f.lower().endswith("." + ext):
            continue
        m = pat.match(f) if pat else re.match(r".*?(\d+)\.", f)
        idx = int(m.group(1)) if m else len(files)
        files.append((idx, os.path.join(input_dir, f)))
    files.sort(key=lambda t: t[0])
    return [p for _, p in files]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--prefix", default="")
    ap.add_argument("--ext", default="png")
    ap.add_argument("--out", required=True)
    ap.add_argument("--columns", type=int, default=0, help="0 = auto (near-square)")
    ap.add_argument("--name", default="atlas")
    args = ap.parse_args()

    frames = collect(args.input, args.prefix, args.ext)
    if not frames:
        sys.exit(f"no frames matched prefix={args.prefix!r} in {args.input}")

    first = Image.open(frames[0]).convert("RGBA")
    fw, fh = first.size
    n = len(frames)
    cols = args.columns or max(1, int(n ** 0.5 + 0.999))
    rows = (n + cols - 1) // cols
    atlas = Image.new("RGBA", (fw * cols, fh * rows), (0, 0, 0, 0))
    for i, path in enumerate(frames):
        img = Image.open(path).convert("RGBA")
        if img.size != (fw, fh):
            img = img.resize((fw, fh), Image.LANCZOS)
        atlas.paste(img, ((i % cols) * fw, (i // cols) * fh))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    atlas_path = out / f"{args.name}.png"
    atlas.save(atlas_path, optimize=True)
    meta = {
        "name": args.name,
        "frame_width": fw, "frame_height": fh,
        "columns": cols, "rows": rows, "frames": n,
        "atlas_width": atlas.width, "atlas_height": atlas.height,
        "source_frames": [os.path.basename(p) for p in frames],
        "decoded_bytes_rgba": atlas.width * atlas.height * 4,
    }
    (out / f"{args.name}.json").write_text(json.dumps(meta, indent=2))
    src_bytes = sum(os.path.getsize(p) for p in frames)
    print(f"frames={n} frame={fw}x{fh} atlas={atlas.width}x{atlas.height}")
    print(f"source PNG total = {src_bytes/1024:.1f} KB")
    print(f"atlas PNG        = {atlas_path.stat().st_size/1024:.1f} KB")
    print(f"decoded RGBA     = {meta['decoded_bytes_rgba']/1024:.1f} KB")
    print(f"wrote {atlas_path} and {out / (args.name + '.json')}")


if __name__ == "__main__":
    main()
