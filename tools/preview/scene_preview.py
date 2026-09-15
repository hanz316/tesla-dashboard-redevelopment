#!/usr/bin/env python3
"""Mac scene previewer — renders *.scene + manifest without the dashboard.

Reads the exact same scene file, asset manifest and animation definitions
the device runtime consumes, so the Mac and the仪表 cannot drift into two
different UIs.

Mock vehicle data is allowed ONLY here (preview/developer mode). The
production runtime must never invent telemetry.

Usage:
    python3 tools/preview/scene_preview.py --scene scenes/horizon_v1.scene
    python3 tools/preview/scene_preview.py --scene scenes/horizon_v1.scene --all-states
    python3 tools/preview/scene_preview.py --list-states
"""

import argparse
import json
import os
import sys
from datetime import datetime

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow required: pip3 install pillow")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vehicle_asset_provider  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FALLBACK_FONT = "/System/Library/Fonts/Supplemental/Verdana.ttf"

# Preview-only mock states. Production never uses these.
MOCK_STATES = {
    "parked": {
        "speed": 0, "gear": 1, "soc": 97, "range": 253,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False,
        "brake": True, "headlight": False,
        "indicator_left": False, "indicator_right": False,
        "temperature_primary": 22, "closures": "ALL CLOSED",
        "uart_health": "UART OK",
    },
    "driving": {
        "speed": 88, "gear": 4, "soc": 63, "range": 253,
        "temperature_primary": 24, "closures": "ALL CLOSED",
        "indicator_left": True, "uart_health": "UART OK",
    },
    "door_open": {
        "speed": 0, "gear": 1, "soc": 97, "range": 253,
        "door_fl": True, "closures": "OPEN FL",
        "temperature_primary": 22, "uart_health": "UART OK",
    },
    "all_open": {
        "speed": 0, "gear": 3, "soc": 97, "range": 250,
        "door_fl": True, "door_fr": True, "door_rl": True, "door_rr": True,
        "frunk": True, "trunk": True, "closures": "OPEN FL FR RL RR FRUNK TRUNK",
        "temperature_primary": 21, "uart_health": "UART OK",
    },
    "stale": {
        "closures": "DOORS --", "uart_health": "UART STALE",
    },
    "lost": {
        "closures": "DOORS --", "uart_health": "UART LOST",
    },
}


# ---------------------------------------------------------------- data model

class Signal:
    def __init__(self, value=None, valid=True, extra=None):
        self.value = value
        self.valid = valid
        self.extra = extra or {}

    def get(self, key):
        return self.extra.get(key)


class State:
    """Minimal VehicleState projection used by the previewer."""

    def __init__(self, raw):
        self.raw = raw

    def signal(self, path):
        if path.endswith(".valid"):
            base = path[:-6]
            return Signal(self.has(base), self.has(base))
        if path.endswith(".trusted"):
            base = path[:-8]
            # MCU SOC is known-untrusted; only an explicit trusted flag is true.
            return Signal(bool(self.raw.get("soc_trusted", False)), True)
        if path == "any_door_open":
            v = any(bool(self.raw.get(k)) for k in
                    ("door_fl", "door_fr", "door_rl", "door_rr",
                     "frunk", "trunk"))
            return Signal(v, "closures" in self.raw)
        if path == "closures_valid":
            return Signal("closures" in self.raw, True)
        if path in self.raw:
            return Signal(self.raw[path], True)
        return Signal(None, False)

    def has(self, key):
        return key in self.raw and self.raw[key] is not None


# ------------------------------------------------------------------ bindings

def condition_holds(cond, state):
    if "any" in cond:
        return any(condition_holds(c, state) for c in cond["any"])
    if "all" in cond:
        return all(condition_holds(c, state) for c in cond["all"])
    sig = state.signal(cond.get("signal", ""))
    if "equals" in cond:
        return sig.value == cond["equals"]
    if "valid" in cond:
        return sig.valid == cond["valid"]
    if "is_true" in cond:
        return bool(sig.value) == cond["is_true"]
    return False


def pick_color(node, state, default_key="color"):
    for rule in node.get("color_when", []):
        if condition_holds(rule["when"], state):
            return rule["color"]
    return node.get(default_key, "#F2F4F6")


def resolve_value(node, state):
    """Returns (text, is_valid) for a text node."""
    # text_when rules take priority: declarative overrides such as
    # "known-untrusted SOC must not be shown as a trusted value".
    for rule in node.get("text_when", []):
        if condition_holds(rule["when"], state):
            return rule.get("text", ""), rule.get("valid", True)
    if "text" in node:
        return node["text"], True
    if node.get("source") == "clock":
        return datetime.now().strftime(node.get("format", "%H:%M")), True
    bind = node.get("bind")
    if not bind:
        return "", False
    sig = state.signal(bind)
    if not sig.valid or sig.value is None:
        fmt = node.get("format", "{}")
        return fmt.replace("{}", "--"), False
    value = sig.value
    vmap = node.get("value_map")
    if vmap is not None:
        value = vmap.get(str(value), "--")
    fmt = node.get("format", "{}")
    try:
        return fmt.format(value), True
    except (IndexError, KeyError):
        return f"{value}", True


# ----------------------------------------------------------------- rendering

def load_font(size, bold=False):
    for path in ((FONT_BOLD, FONT_REG) if bold else (FONT_REG, FALLBACK_FONT)):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def hex_to_rgb(value, alpha=255):
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


def draw_text(img, node, state):
    text, valid = resolve_value(node, state)
    color = pick_color(node, state)
    if not valid:
        color = node.get("invalid_color", "#5A646E")
    font = load_font(node.get("font", 32), node.get("bold", False))
    draw = ImageDraw.Draw(img)
    x = node.get("x", 0)
    y = node.get("y", 0)
    anchor_map = {"center": "mm", "left": "lm", "right": "rm"}
    anchor = anchor_map.get(node.get("align", "center"), "mm")
    shadow = node.get("shadow", True)
    if shadow:
        draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 160), anchor=anchor)
    draw.text((x, y), text, font=font, fill=hex_to_rgb(color), anchor=anchor)


def draw_vector(img, node, state):
    draw = ImageDraw.Draw(img, "RGBA")
    x, y = node.get("x", 0), node.get("y", 0)
    w, h = node.get("width", 0), node.get("height", 0)
    shape = node.get("shape", "rect")
    opacity = node.get("opacity", 1.0)

    if shape == "vgradient":
        top = hex_to_rgb(node["from"])
        bottom = hex_to_rgb(node["to"])
        for row in range(h):
            t = row / max(1, h - 1)
            col = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            draw.line([(x, y + row), (x + w, y + row)], fill=col + (255,))
        return

    if shape == "radial":
        steps = 48
        cx, cy = x + w / 2.0, y + h / 2.0
        inner = hex_to_rgb(node["from"], int(255 * opacity))
        outer = hex_to_rgb(node["to"], 0)
        for i in range(steps, 0, -1):
            t = i / steps
            rx, ry = (w / 2.0) * t, (h / 2.0) * t
            mix = tuple(int(inner[c] * (1 - t) + outer[c] * t) for c in range(3))
            a = int(inner[3] * (1 - t))
            draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=mix + (a,))
        return

    if shape == "roundrect":
        radius = node.get("radius", 10)
        draw.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                               fill=hex_to_rgb(node.get("fill", "#182028")))
        if "stroke" in node:
            draw.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                                   outline=hex_to_rgb(node["stroke"]), width=2)
        progress = node.get("progress")
        if progress:
            sig = state.signal(progress["signal"])
            if sig.valid and sig.value is not None:
                ratio = max(0.0, min(1.0, float(sig.value) / 100.0))
                fill_w = max(4.0, w * ratio)
                draw.rounded_rectangle([x, y, x + fill_w, y + h], radius=radius,
                                       fill=hex_to_rgb(progress.get("color",
                                                                   "#3D9BFF")))
        return

    draw.rectangle([x, y, x + w, y + h],
                   fill=hex_to_rgb(node.get("fill", "#000000")))


def resolve_asset_path(provider, asset_id):
    manifest = provider.manifest
    if asset_id in manifest.get("images", {}):
        return provider.path_for(manifest["images"][asset_id])
    if asset_id in manifest.get("overlays", {}):
        return provider.path_for(manifest["overlays"][asset_id])
    return None


def sequence_frame(provider, seq_id, bind, state, t_norm=1.0):
    """Picks the frame for a to_state / loop sequence."""
    manifest = provider.manifest
    seq = manifest.get("sequences", {}).get(seq_id)
    if seq is None:
        return None
    sig = state.signal(bind) if bind else Signal(True, True)
    frames = seq.get("frames", 1)
    if seq.get("mode") == "loop":
        if not (sig.valid and sig.value):
            return None
        idx = int(t_norm * frames) % frames
    else:  # to_state: open -> last frame, closed -> nothing drawn
        if not (sig.valid and sig.value):
            return None
        idx = frames - 1
    path = provider.path_for(os.path.join(seq["dir"], f"{idx:03d}.png"))
    return path if os.path.isfile(path) else None


def paste_scaled(base, path, x, y, w, h):
    img = Image.open(path).convert("RGBA")
    if (img.width, img.height) != (w, h):
        img = img.resize((w, h), Image.LANCZOS)
    base.alpha_composite(img, (int(x), int(y)))


def draw_vehicle_visual(img, node, state, provider, t_norm,
                        vehicle_image=None):
    x, y = node.get("x", 0), node.get("y", 0)
    w, h = node.get("width", 356), node.get("height", 236)
    if vehicle_image:
        # A/B checkpoint mode: composite a rendered vehicle instead of the
        # provider asset. Aspect ratio is preserved inside the node box.
        veh = Image.open(vehicle_image).convert("RGBA")
        scale = min(w / veh.width, h / veh.height)
        new_size = (max(1, int(veh.width * scale)),
                    max(1, int(veh.height * scale)))
        veh = veh.resize(new_size, Image.LANCZOS)
        ox = int(x + (w - new_size[0]) / 2)
        oy = int(y + (h - new_size[1]) / 2)
        img.alpha_composite(veh, (ox, oy))
        return
    asset = resolve_asset_path(provider, node.get("asset", ""))
    if asset and os.path.isfile(asset):
        paste_scaled(img, asset, x, y, w, h)
    else:
        d = ImageDraw.Draw(img, "RGBA")
        d.rounded_rectangle([x, y, x + w, y + h], radius=14,
                            outline=(90, 100, 110, 120), width=2)
    for part in node.get("parts", {}).values():
        path = sequence_frame(provider, part["sequence"], part.get("bind"),
                              state, t_norm)
        if path:
            paste_scaled(img, path, x, y, w, h)
    for ov in node.get("overlays", []):
        sig = state.signal(ov["bind"]) if ov.get("bind") else Signal(True, True)
        if not (sig.valid and sig.value):
            continue
        path = resolve_asset_path(provider, ov["asset"])
        if path and os.path.isfile(path):
            paste_scaled(img, path, x, y, w, h)
    for side, part in node.get("indicators", {}).items():
        path = sequence_frame(provider, part["sequence"], part.get("bind"),
                              state, t_norm)
        if path:
            paste_scaled(img, path, x, y, w, h)


def apply_safe_area(img, canvas):
    safe = canvas.get("safe_area", {})
    top = int(safe.get("top_corner_cut", 0))
    bottom = int(safe.get("bottom_corner_cut", 0))
    if top <= 0 and bottom <= 0:
        return img
    d = ImageDraw.Draw(img)
    w, h = img.size
    d.polygon([(0, 0), (top, 0), (bottom, h), (0, h)], fill=(0, 0, 0, 255))
    d.polygon([(w, 0), (w - top, 0), (w - bottom, h), (w, h)],
              fill=(0, 0, 0, 255))
    return img


def draw_dev_banner(img, text):
    """Marks a preview as developer/placeholder output so it can never be
    mistaken for a production asset."""
    d = ImageDraw.Draw(img, "RGBA")
    font = load_font(20, bold=True)
    pad = 8
    bbox = d.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + pad * 2
    h = bbox[3] - bbox[1] + pad * 2
    x, y = 130, 8
    d.rounded_rectangle([x, y, x + w, y + h], radius=6,
                        fill=(120, 60, 0, 190), outline=(255, 170, 60, 230))
    d.text((x + pad, y + pad - bbox[1]), text, font=font,
           fill=(255, 220, 170, 255))


def render(scene, provider, raw_state, out_path, t_norm=1.0,
           banner=None, vehicle_image=None):
    canvas = scene["canvas"]
    img = Image.new("RGBA", (canvas["width"], canvas["height"]), (0, 0, 0, 255))
    state = State(raw_state)
    nodes = sorted(scene["nodes"], key=lambda n: n.get("z", 0))
    for node in nodes:
        ntype = node.get("type")
        if ntype == "vector":
            draw_vector(img, node, state)
        elif ntype == "text":
            draw_text(img, node, state)
        elif ntype == "vehicle_visual":
            draw_vehicle_visual(img, node, state, provider, t_norm,
                                vehicle_image)
        elif ntype == "image":
            path = resolve_asset_path(provider, node.get("asset", ""))
            if path and os.path.isfile(path):
                paste_scaled(img, path, node.get("x", 0), node.get("y", 0),
                             node.get("width", 0), node.get("height", 0))
        elif ntype == "image_anim":
            path = sequence_frame(provider, node["sequence"],
                                  node.get("bind"), state, t_norm)
            if path:
                paste_scaled(img, path, node.get("x", 0), node.get("y", 0),
                             node.get("width", 0), node.get("height", 0))
        elif ntype == "group":
            for child in sorted(node.get("children", []),
                                key=lambda n: n.get("z", 0)):
                child = dict(child)
                child["x"] = node.get("x", 0) + child.get("x", 0)
                child["y"] = node.get("y", 0) + child.get("y", 0)
                draw_text(img, child, state) if child.get("type") == "text" \
                    else draw_vector(img, child, state)
    apply_safe_area(img, canvas)
    if banner:
        draw_dev_banner(img, banner)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default=os.path.join(REPO_ROOT, "scenes",
                                                    "horizon_v1.scene"))
    ap.add_argument("--state", default="driving")
    ap.add_argument("--all-states", action="store_true")
    ap.add_argument("--list-states", action="store_true")
    ap.add_argument("--out", default=os.path.join(REPO_ROOT, "assets",
                                                  "preview"))
    ap.add_argument("--t", type=float, default=1.0,
                    help="animation phase 0..1 for looping sequences")
    ap.add_argument("--require-model3", action="store_true",
                    help="production-like check: refuse to preview with the "
                         "engineering placeholder vehicle")
    ap.add_argument("--allow-placeholder", action="store_true",
                    help="developer preview: permit the placeholder fallback")
    ap.add_argument("--vehicle-image", default=None,
                    help="A/B checkpoint: composite this rendered vehicle PNG "
                         "into the scene instead of the provider asset")
    ap.add_argument("--out-name", default=None,
                    help="override the output filename prefix")
    args = ap.parse_args()

    if args.list_states:
        for name in MOCK_STATES:
            print(" ", name)
        return

    with open(args.scene) as fh:
        scene = json.load(fh)
    manifest_path = os.path.join(REPO_ROOT,
                                 scene.get("manifest", "assets/manifest.json"))
    provider = vehicle_asset_provider.load_provider(REPO_ROOT, manifest_path)
    # Preview defaults to allowing the placeholder; --require-model3 turns
    # that off so CI can assert the real asset exists.
    allow_placeholder = args.allow_placeholder or not args.require_model3
    try:
        kind, root = provider.resolve(allow_placeholder=allow_placeholder)
    except RuntimeError as exc:
        sys.exit(f"[preview] vehicle asset error: {exc}")

    banner = None
    if kind == vehicle_asset_provider.PLACEHOLDER:
        banner = "DEV PREVIEW - ENGINEERING PLACEHOLDER VEHICLE (not production art)"
    print(f"[preview] vehicle source: {kind} -> {os.path.relpath(root, REPO_ROOT)}")
    if provider.warning:
        print(f"[preview] WARNING: {provider.warning}")

    states = list(MOCK_STATES) if args.all_states else [args.state]
    for name in states:
        if name not in MOCK_STATES:
            sys.exit(f"unknown state: {name} (see --list-states)")
        filename = (args.out_name or f"{scene['scene']}_{name}") + ".png"
        out = os.path.join(args.out, filename)
        render(scene, provider, MOCK_STATES[name], out, args.t, banner,
               args.vehicle_image)
        print(f"[preview] {name:10} -> {out}")


if __name__ == "__main__":
    main()
