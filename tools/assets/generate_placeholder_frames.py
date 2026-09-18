#!/usr/bin/env python3
"""Blender-free placeholder renderer for the vehicle asset pipeline.

Produces EXACTLY the same output contract as the Blender renders
(transparent RGBA, fixed canvas, fixed anchor, pixel aligned — only the
moving part changes between frames), so the whole downstream pipeline
(budget check -> atlas -> scene preview -> runtime) can be validated
without Blender installed.

It is a deliberate engineering placeholder, never a production asset.
When Blender is available, `tools/blender/render_vehicle_assets.py`
regenerates the same directories with real geometry.

Usage:
    python3 tools/assets/generate_placeholder_frames.py --all
    python3 tools/assets/generate_placeholder_frames.py --action Door_FL_Open
    python3 tools/assets/generate_placeholder_frames.py --list
"""

import argparse
import math
import os
import sys

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Pillow required: pip3 install pillow")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# Placeholder art is kept in its own tree so the runtime can tell it apart
# from real Blender renders (assets/rendered/vehicle). Production must never
# ship the placeholder tree.
DEFAULT_OUT = os.path.join(REPO_ROOT, "assets", "rendered", "placeholder")

CANVAS_W, CANVAS_H = 356, 236
SS = 3                      # supersample, matching the Blender pipeline

# Fixed anchor: every frame uses the same absolute canvas coordinates, so the
# vehicle never moves inside the canvas (no per-frame crop, no drift).
ANCHOR_X, ANCHOR_Y = 0.0, 0.0
SCALE = 1.0

COL_BODY = (156, 162, 168, 255)
COL_BODY_EDGE = (214, 220, 224, 255)
COL_GLASS = (26, 34, 40, 235)
COL_TIRE = (18, 18, 20, 255)
COL_RIM = (176, 180, 184, 255)
COL_HEAD = (255, 246, 226, 255)
COL_BRAKE = (232, 44, 36, 255)
COL_IND = (255, 150, 24, 255)

ACTIONS = {
    "Vehicle_Base": ("base", 1),
    # name: (kind, frames)
    "Door_FL_Open": ("door_fl", 16),
    "Door_FR_Open": ("door_fr", 16),
    "Door_RL_Open": ("door_rl", 16),
    "Door_RR_Open": ("door_rr", 16),
    "Frunk_Open": ("frunk", 14),
    "Trunk_Open": ("trunk", 14),
    "Brake_On": ("brake", 1),
    # The rear running light shares the brake lamp in the frozen production
    # system, so its placeholder is the brake placeholder. It exists because
    # assets/manifest.json declares vehicle.running: a committed placeholder
    # tree has to satisfy the same contract the runtime reads.
    "Running_On": ("running", 1),
    "Headlight_On": ("headlight", 1),
    "Indicator_Left": ("indicator_left", 12),
    "Indicator_Right": ("indicator_right", 12),
    "Hazard": ("hazard", 12),
}

DIRS = {
    "Vehicle_Base": "base",
    "Door_FL_Open": "door_fl", "Door_FR_Open": "door_fr",
    "Door_RL_Open": "door_rl", "Door_RR_Open": "door_rr",
    "Frunk_Open": "frunk", "Trunk_Open": "trunk",
    "Brake_On": "brake_on", "Headlight_On": "headlight_on",
    "Running_On": "running_on",
    "Indicator_Left": "indicator_left",
    "Indicator_Right": "indicator_right", "Hazard": "hazard",
}


def s(v):
    """Scale a design-space value to the supersampled canvas."""
    return v * SCALE * SS


def pt(x, y):
    """Design-space (canvas absolute px) -> supersampled pixel coordinates."""
    return (ANCHOR_X * SS + x * SS, ANCHOR_Y * SS + y * SS)


def new_canvas():
    return Image.new("RGBA", (CANVAS_W * SS, CANVAS_H * SS), (0, 0, 0, 0))


def draw_car_base(d):
    """Body, glass, wheels — identical in every frame (the fixed anchor)."""
    body = [pt(96, 34), pt(58, 46), pt(46, 78), pt(46, 118),
            pt(58, 150), pt(96, 162), pt(258, 162), pt(296, 150),
            pt(308, 118), pt(308, 78), pt(296, 46), pt(258, 34)]
    d.polygon(body, fill=COL_BODY, outline=COL_BODY_EDGE, width=max(1, int(s(1.5))))

    glass = [pt(104, 56), pt(84, 66), pt(84, 104), pt(104, 126),
             pt(132, 126), pt(146, 104), pt(146, 66), pt(132, 56)]
    d.polygon(glass, fill=COL_GLASS)

    for cx, cy in ((84, 96), (268, 96), (84, 176), (268, 176)):
        x, y = pt(cx, cy)
        r_out, r_in = s(16), s(9)
        d.ellipse([x - r_out, y - r_out, x + r_out, y + r_out], fill=COL_TIRE)
        d.ellipse([x - r_in, y - r_in, x + r_in, y + r_in], fill=COL_RIM)


def draw_door(d, side, hinge_x, length, angle_deg):
    """Door panel hinged at its front edge, swinging outward off the flank.

    Left doors sit on the lower flank and swing down; right doors sit on the
    upper flank and swing up. Geometry is schematic (rear 3/4 read).
    """
    left = side.endswith("L")
    flank_y = 158 if left else 52          # keep the swing inside the canvas
    outward = 1.0 if left else -1.0
    ang = math.radians(angle_deg)
    hx, hy = pt(hinge_x, flank_y)
    ex = hx + s(length) * math.cos(ang)
    ey = hy + s(length) * math.sin(ang) * outward
    d.line([hx, hy, ex, ey], fill=COL_BODY, width=max(2, int(s(6))))
    edge = s(4)
    d.ellipse([ex - edge, ey - edge, ex + edge, ey + edge], fill=COL_BODY_EDGE)


def draw_light(d, kind, strength):
    if strength <= 0.01:
        return
    alpha = int(255 * min(1.0, strength))
    if kind in ("brake", "running"):
        for cx in (66, 268):
            x, y = pt(cx, 52)
            # The running light is the same lamp at a lower intensity.
            alpha_run = int(alpha * 0.45) if kind == "running" else alpha
            d.ellipse([x - s(13), y - s(8), x + s(13), y + s(8)],
                      fill=COL_BRAKE[:3] + (alpha_run,))
    elif kind == "headlight":
        for cx in (304, 304):
            x, y = pt(cx - 10, 52)
            d.ellipse([x - s(9), y - s(12), x + s(9), y + s(12)],
                      fill=COL_HEAD[:3] + (alpha,))
    elif kind in ("indicator_left", "indicator_right"):
        cx = 60 if kind.endswith("left") else 272
        x, y = pt(cx, 42)
        d.ellipse([x - s(10), y - s(7), x + s(10), y + s(7)],
                  fill=COL_IND[:3] + (alpha,))
    elif kind == "hazard":
        for cx in (60, 272):
            x, y = pt(cx, 42)
            d.ellipse([x - s(10), y - s(7), x + s(10), y + s(7)],
                      fill=COL_IND[:3] + (alpha,))


def render_action(action, out_dir):
    kind, frames = ACTIONS[action]
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))

    for i in range(frames):
        t = 0.0 if frames == 1 else i / float(frames - 1)
        img = new_canvas()
        d = ImageDraw.Draw(img)
        draw_car_base(d)

        if kind.startswith("door_"):
            side = kind.split("_")[1].upper()
            front = side in ("FL", "FR")
            hinge_x = 140 if front else 232
            length = 62 if front else 58
            draw_door(d, side, hinge_x, length, 44.0 * t)
        elif kind == "frunk":
            y = 30 - 26 * t
            x0, y0 = pt(108, y)
            x1, y1 = pt(246, y + 16)
            d.rectangle([x0, y0, x1, y1], outline=COL_BODY_EDGE,
                        fill=(150, 156, 162, 200), width=max(1, int(s(1.5))))
        elif kind == "trunk":
            y = 176 + 20 * t
            x0, y0 = pt(112, y)
            x1, y1 = pt(244, y + 14)
            d.rectangle([x0, y0, x1, y1], outline=COL_BODY_EDGE,
                        fill=(150, 156, 162, 200), width=max(1, int(s(1.5))))
        elif kind in ("brake", "running"):
            draw_light(d, "running" if kind == "running" else "brake", 1.0)
        elif kind == "headlight":
            draw_light(d, "headlight", 1.0)
        elif kind in ("indicator_left", "indicator_right", "hazard"):
            # one full blink cycle: on, off, on, off
            phase = (i / float(frames)) * 2.0
            strength = 1.0 if (phase % 1.0) < 0.5 else 0.0
            draw_light(d, kind, strength)
        elif kind == "base":
            pass        # body/glass/wheels already drawn; static reference frame

        img = img.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
        img.save(os.path.join(out_dir, f"{i:03d}.png"))
    return frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--budget", action="store_true",
                    help="run check_budget.py on each generated sequence")
    args = ap.parse_args()

    if args.list:
        for name, (kind, frames) in sorted(ACTIONS.items()):
            print(f"  {name:16} frames={frames:2d} kind={kind}")
        return

    selected = list(ACTIONS) if args.all else args.action
    if not selected:
        sys.exit("nothing selected: pass --all or --action NAME (see --list)")

    for name in selected:
        if name not in ACTIONS:
            sys.exit(f"unknown action: {name}")
        out_dir = os.path.join(args.out, DIRS[name])
        n = render_action(name, out_dir)
        print(f"[placeholder] {name}: {n} frames -> {out_dir}")

    if args.budget:
        import subprocess
        for name in selected:
            out_dir = os.path.join(args.out, DIRS[name])
            subprocess.run([sys.executable,
                            os.path.join(REPO_ROOT, "tools", "assets",
                                         "check_budget.py"),
                            "--sequence", out_dir], check=False)


if __name__ == "__main__":
    main()
