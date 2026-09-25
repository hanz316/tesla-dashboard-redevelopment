#!/usr/bin/env python3
"""Bake the bounded blind-zone overlays used by the host and device paths.

The source is the frozen Model A silhouette. The overlay is intentionally an
amber-neutral, low-opacity acknowledgement of spatial presence; it carries no
collision probability and is only shown for a validated semantic state.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "assets/rendered/vehicle/horizon_v5/day/car/base/000.png"
OUT = ROOT / "assets/ui"


def ghost():
    image = Image.open(SOURCE).convert("RGBA")
    box = image.getchannel("A").getbbox()
    body = image.crop(box)
    body.thumbnail((132, 88), Image.Resampling.LANCZOS)
    padded = Image.new("RGBA", (132, 88), (0, 0, 0, 0))
    padded.alpha_composite(body, ((132 - body.width) // 2, (88 - body.height) // 2))
    body = padded
    alpha = body.getchannel("A")
    soft = np.asarray(alpha.filter(ImageFilter.GaussianBlur(1.2)), dtype=np.float32)
    inner = np.asarray(alpha.filter(ImageFilter.MinFilter(5)), dtype=np.float32)
    edge = np.clip(soft - inner, 0.0, 255.0)
    rgba = np.zeros((body.height, body.width, 4), dtype=np.uint8)
    rgba[:, :, :3] = (220, 174, 94)
    rgba[:, :, 3] = np.clip(soft * 0.10 + edge * 0.58, 0, 92).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def glow():
    canvas = Image.new("RGBA", (180, 220), (0, 0, 0, 0))
    pixels = np.zeros((220, 180, 4), dtype=np.uint8)
    yy, xx = np.mgrid[:220, :180]
    distance = np.sqrt(((xx - 89.5) / 72.0) ** 2 + ((yy - 109.5) / 100.0) ** 2)
    alpha = np.clip(1.0 - distance, 0.0, 1.0) ** 2 * 30.0
    pixels[:, :, :3] = (216, 166, 79)
    pixels[:, :, 3] = alpha.astype(np.uint8)
    return Image.fromarray(pixels, "RGBA").filter(ImageFilter.GaussianBlur(14))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    body = ghost()
    right = ImageOps.mirror(body)
    body.save(OUT / "horizon_v54_blind_ghost_left.png")
    right.save(OUT / "horizon_v54_blind_ghost_right.png")
    glow().save(OUT / "horizon_v54_blind_glow.png")


if __name__ == "__main__":
    main()
