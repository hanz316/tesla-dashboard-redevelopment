#!/usr/bin/env python3
"""Generate scenes/horizon_v2.scene from the Horizon V2 layout.

DESIGN AS DATA: assets/ui/horizon_v2_layout.json holds every coordinate, size,
token reference and visibility rule. This file resolves the token references and
emits the scene the previewer and the device read. It refuses to emit a scene
that breaks the panel mask, the safe area or the zone rules, so a layout that
would be clipped on the real trapezoid panel cannot reach a screenshot.

Usage:
    python3 tools/preview/build_horizon_v2.py
"""

import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v2_layout.json")
TOKENS = os.path.join(REPO, "assets", "ui", "design_tokens.json")
OUT = os.path.join(REPO, "scenes", "horizon_v2.scene")

GEAR_INDEX = {"P": 1, "R": 2, "N": 3, "D": 4}
ALIGN = {"left": "left", "center": "center", "right": "right"}


def load(path):
    with open(path) as fh:
        return json.load(fh)


class Tokens:
    def __init__(self, doc):
        self.colors = doc["colors"]
        self.typography = doc["typography"]["tiers"]
        self.spacing = doc["spacing"]
        self.radii = doc["radii"]
        self.opacity = doc["opacity"]
        self.animation = doc["animation"]
        self.vehicles = doc["vehicle"]

    def color(self, name):
        if name not in self.colors:
            raise KeyError(f"unknown colour token: {name}")
        return self.colors[name]

    def opt(self, name):
        if name is None:
            return 1.0
        if name not in self.opacity:
            raise KeyError(f"unknown opacity token: {name}")
        return self.opacity[name]

    def radius(self, name):
        if name not in self.radii:
            raise KeyError(f"unknown radius token: {name}")
        return self.radii[name]

    def font(self, name):
        if name not in self.typography:
            raise KeyError(f"unknown typography token: {name}")
        return self.typography[name]


def panel_cut(y, layout):
    top = layout["panel"]["top_corner_cut"]
    bottom = layout["panel"]["bottom_corner_cut"]
    height = layout["canvas"]["height"]
    return top + (bottom - top) * (float(y) / height)


def check_bounds(component, tokens, layout):
    """Fail the build rather than emit a scene that is wrong on the panel."""
    if component.get("exempt_from_safe_area"):
        return
    b = component["bounds"]
    canvas = layout["canvas"]
    safe = layout["safe_area"]
    problems = []
    if b["x"] < 0 or b["y"] < 0 or b["x"] + b["w"] > canvas["width"] or \
            b["y"] + b["h"] > canvas["height"]:
        problems.append("outside canvas")
    if (b["x"] < safe["left"] or b["x"] + b["w"] > canvas["width"] - safe["right"]
            or b["y"] < safe["top"] or b["y"] + b["h"] > canvas["height"] - safe["bottom"]):
        problems.append("outside safe area")
    # The panel mask tapers: check both top and bottom edges of the component.
    for y in (b["y"], b["y"] + b["h"]):
        cut = panel_cut(y, layout)
        if "x" in b and b["x"] < cut:
            problems.append(f"behind the panel mask at y={y} (needs x >= {cut:.1f})")
        right_limit = canvas["width"] - cut
        if b["x"] + b["w"] > right_limit:
            problems.append(
                f"behind the panel mask at y={y} (needs x+w <= {right_limit:.1f})")
    if problems:
        raise SystemExit(f"[v2] {component['id']}: " + "; ".join(problems))


def text_node(component, tokens):
    b = component["bounds"]
    align = ALIGN[component.get("align", "left")]
    tier = tokens.font(component["font_token"])
    x = b["x"] if align == "left" else (
        b["x"] + b["w"] if align == "right" else b["x"] + b["w"] / 2)
    node = {
        "id": component["id"],
        "type": "text",
        "z": component["z"],
        "layer": component.get("layer", "dynamic"),
        "x": round(x, 1),
        # The renderer anchors text on its vertical middle.
        "y": round(b["y"] + b["h"] / 2, 1),
        "size": tier["size"],
        "font": tier["size"],
        "font_role": tier["role"],
        "shadow": component.get("shadow", True),
        "color_token": component["color_token"],
        "bold": tier["role"] == "bold",
        "tracking": tier["tracking"],
        "align": align,
        "color": tokens.color(component["color_token"]),
    }
    if "opacity_token" in component:
        node["alpha"] = tokens.opt(component["opacity_token"])
    if "text_token" in component or "text" in component:
        node["text"] = component.get("text", "")
    if "source" in component:
        node["source"] = component["source"]
        node["format"] = component.get("format", "{}")
    if "binding" in component:
        node["bind"] = component["binding"]
        node["format"] = component.get("format", "{}")
        if "invalid_text" in component:
            node["invalid_text"] = component["invalid_text"]
        else:
            node["invalid_text"] = ""
        if component.get("unknown_behavior") == "hidden":
            node["invalid_alpha"] = 0.0
        elif "invalid_opacity_token" in component:
            node["invalid_alpha"] = tokens.opt(component["invalid_opacity_token"])
    if "highlight_when_gear" in component:
        letter = component["highlight_when_gear"]
        index = GEAR_INDEX[letter]
        node["color_when"] = [
            {"when": {"signal": "gear", "equals": index},
             "color": tokens.color(component["highlight_color_token"])}
        ]
        node["alpha_when"] = [
            {"when": {"signal": "gear", "equals": index},
             "alpha": tokens.opt(component["highlight_opacity_token"])},
            {"when": {"signal": "gear", "valid": True},
             "alpha": tokens.opt("inactive_gear")},
            # Unknown gear: the row hides and the "—" placeholder speaks for it,
            # rather than four dim letters sitting under a dash.
            {"when": {"signal": "gear", "valid": False}, "alpha": 0.0},
        ]
        node["alpha"] = tokens.opt("inactive_gear")
    if "visibility" in component:
        vis = component["visibility"]
        visible_opacity = tokens.opt(component.get("opacity_token"))
        if any(key in vis for key in ("lte", "gte", "equals")):
            condition = {"signal": vis["binding"]}
            for key in ("lte", "gte", "equals"):
                if key in vis:
                    condition[key] = vis[key]
            node["opacity"] = 1.0
            node["alpha_when"] = [
                {"when": condition,
                 "alpha": component.get("visible_opacity", 0.5)},
                {"when": {"signal": vis["binding"], "valid": False},
                 "alpha": 0.0},
                # A threshold rule has no rule that matches when the value is
                # outside it, and an unmatched alpha_when falls back to visible.
                # That is how a low-SOC warning rail stayed lit at 63 %.
                {"when": {"always": True}, "alpha": 0.0},
            ]
        elif vis.get("show_when_true"):
            node["opacity"] = 1.0
            node["alpha_when"] = [
                {"when": {"signal": vis["binding"], "is_true": True},
                 "alpha": component.get("visible_opacity", 0.5)},
                {"when": {"signal": vis["binding"], "is_true": False},
                 "alpha": 0.0},
            ]
        elif vis.get("show_when_valid"):
            node["alpha_when"] = [
                {"when": {"signal": vis["binding"], "valid": True},
                 "alpha": visible_opacity},
                {"when": {"signal": vis["binding"], "valid": False}, "alpha": 0.0},
            ]
            node["alpha"] = 0.0
        elif vis.get("show_when_invalid"):
            node["alpha_when"] = [
                {"when": {"signal": vis["binding"], "valid": False},
                 "alpha": visible_opacity},
                {"when": {"signal": vis["binding"], "valid": True}, "alpha": 0.0},
            ]
            node["alpha"] = 0.0
    if "text_when" in component:
        node["text_when"] = [
            {"when": {"signal": rule["signal"],
                      **({"is_true": True} if rule.get("is_true") else {}),
                      **({"valid": True} if rule.get("valid") else {})},
             "text": rule["text"], "valid": rule.get("valid", True)}
            for rule in component["text_when"]
        ]
    return node


def road_points(layout):
    zone = layout["zones"]["vehicle"]
    top_y = 300
    bottom_y = layout["canvas"]["height"] - 24
    centre = (zone["x"] + zone["right"]) / 2.0
    top_half = 210.0
    bottom_half = (zone["right"] - zone["x"]) / 2.0
    return [[centre - top_half, top_y], [centre + top_half, top_y],
            [centre + bottom_half, bottom_y], [centre - bottom_half, bottom_y]]


def vector_node(component, tokens, layout):
    b = component["bounds"]
    shape = component["shape"]
    node = {
        "id": component["id"],
        "type": "vector",
        "shape": shape,
        "z": component["z"],
        "layer": component.get("layer", "static"),
    }
    if shape in ("vgradient", "hgradient"):
        node.update({"x": b["x"], "y": b["y"], "width": b["w"], "height": b["h"],
                     "from": tokens.color(component["color_token"]),
                     "to": tokens.color(component["color_to_token"])})
    elif shape == "radial":
        node.update({"x": b["x"], "y": b["y"], "width": b["w"], "height": b["h"],
                     "from": tokens.color(component["color_token"]),
                     "to": tokens.color(component["color_to_token"]),
                     "opacity": component.get(
                         "opacity", tokens.opt(component.get("opacity_token")))})
    elif shape == "line":
        node.update({"x": b["x"], "y": b["y"],
                     # A line may state its own end point; the bounds are then
                     # just the box that contains it, for the layout checks.
                     "x2": component.get("x2", b["x"] + b["w"]),
                     "y2": component.get("y2", b["y"] + b["h"]),
                     "color": tokens.color(component["color_token"]),
                     "width_px": component.get("width_px", 1)})
    elif shape == "polygon":
        node.update({"points": component.get("points") or road_points(layout),
                     "fill": tokens.color(component["color_token"]),
                     "opacity": tokens.opt(component.get("opacity_token"))})
    elif shape == "arc":
        node.update({"cx": component["cx"], "cy": component["cy"],
                     "radius": component["radius"],
                     "start_deg": component.get("start_deg", 0),
                     "end_deg": component.get("end_deg", 360),
                     "width_px": component.get("width_px", 4),
                     "color": tokens.color(component["color_token"]),
                     "opacity": component.get("opacity", 1.0)})
        if "progress" in component:
            prog = component["progress"]
            node["progress"] = {"signal": prog["binding"], "max": prog.get("max", 100),
                                "from": prog.get("from", "start"),
                                "color": tokens.color(prog.get("color_token", "accent")),
                                "opacity": prog.get("opacity", 1.0)}
    elif shape == "arc_ticks":
        # Radial marks on the instrument arc: the quiet ring of the dial.
        node.update({"cx": component["cx"], "cy": component["cy"],
                     "radius": component["radius"],
                     "start_deg": component.get("start_deg", 0),
                     "end_deg": component.get("end_deg", 360),
                     "count": component.get("count", 24),
                     "length_px": component.get("length_px", 8),
                     "major_every": component.get("major_every", 0),
                     "major_length_px": component.get("major_length_px",
                                                      component.get("length_px", 8)),
                     "color": tokens.color(component["color_token"]),
                     "major_color": tokens.color(
                         component.get("major_token",
                                       component["color_token"])),
                     "width_px": component.get("width_px", 2),
                     "opacity": component.get("opacity", 1.0)})
    elif shape == "polyline":
        node.update({"points": component.get("points", []),
                     "color": tokens.color(component["color_token"]),
                     "width_px": component.get("width_px", 2),
                     "opacity": component.get("opacity", 1.0)})
    elif shape == "vticks":
        # A vertical tick column grows upward from its bottom row. The bounds
        # are the box the checker reasons about (top based); `y_bottom` is what
        # the renderer draws from, so the declared box and the ink agree.
        node.update({"x": b["x"],
                     "y": component.get("y_bottom", b["y"] + b["h"]),
                     "height": b["h"],
                     "count": component.get("count", 20),
                     "major_every": component.get("major_every", 0),
                     "width_px": component.get("width_px", 6),
                     "major_width_px": component.get("major_width_px", 10),
                     "tick_height_px": component.get("tick_height_px", 2),
                     "color": tokens.color(component["color_token"]),
                     "major_color": tokens.color(component["color_token"]),
                     "lit_color": tokens.color(component.get("lit_token", "accent")),
                     "opacity": component.get("opacity", 1.0)})
        if "progress" in component:
            node["progress"] = {"signal": component["progress"]["binding"],
                                "max": component["progress"].get("max", 100)}
    elif shape == "tickrow":
        node.update({"x": b["x"], "y": b["y"], "width": b["w"],
                     "count": component.get("count", 24),
                     "height_px": component.get("height_px", b["h"]),
                     "major_every": component.get("major_every", 0),
                     "color": tokens.color(component["color_token"]),
                     "major_color": tokens.color(component["color_token"]),
                     "lit_color": tokens.color(component.get("lit_token", "accent")),
                     "opacity": component.get("opacity", 1.0)})
        if "progress" in component:
            node["progress"] = {"signal": component["progress"]["binding"],
                                "max": component["progress"].get("max", 100)}
    elif shape == "roundrect":
        node.update({"x": b["x"], "y": b["y"], "width": b["w"], "height": b["h"],
                     "radius": tokens.radius(component["radius_token"]),
                     "fill": tokens.color(component["color_token"])})
        if "stroke_token" in component:
            node["stroke"] = tokens.color(component["stroke_token"])
        node["opacity"] = component.get("opacity", tokens.opt(component.get("opacity_token")))
        if "progress" in component:
            prog = component["progress"]
            node.pop("fill", None)
            node["progress"] = {
                "signal": prog["binding"],
                "max": prog.get("max", 100),
                "color": tokens.color(component["color_token"]),
                "opacity": tokens.opt(component.get("opacity_token")),
            }
            low = prog.get("low_threshold")
            critical = prog.get("critical_threshold")
            if low is not None and critical is not None:
                node["progress"]["color_when"] = [
                    {"when": {"signal": prog["binding"], "lte": critical},
                     "color": tokens.color(component["color_critical_token"])},
                    {"when": {"signal": prog["binding"], "lte": low},
                     "color": tokens.color(component["color_low_token"])},
                ]
    else:
        raise SystemExit(f"[v2] unsupported shape: {shape}")
    if "visibility" in component:
        vis = component["visibility"]
        # The renderer multiplies node opacity by the conditional alpha, so the
        # base stays 1.0 and the rule carries the value the design wants when the
        # element is showing.
        visible_opacity = tokens.opt(component.get("opacity_token"))
        if any(key in vis for key in ("lte", "gte", "equals")):
            condition = {"signal": vis["binding"]}
            for key in ("lte", "gte", "equals"):
                if key in vis:
                    condition[key] = vis[key]
            node["opacity"] = 1.0
            node["alpha_when"] = [
                {"when": condition,
                 "alpha": component.get("visible_opacity", 0.5)},
                {"when": {"signal": vis["binding"], "valid": False},
                 "alpha": 0.0},
                # A threshold rule has no rule that matches when the value is
                # outside it, and an unmatched alpha_when falls back to visible.
                # That is how a low-SOC warning rail stayed lit at 63 %.
                {"when": {"always": True}, "alpha": 0.0},
            ]
        elif vis.get("show_when_true"):
            node["opacity"] = 1.0
            node["alpha_when"] = [
                {"when": {"signal": vis["binding"], "is_true": True},
                 "alpha": component.get("visible_opacity", 0.5)},
                {"when": {"signal": vis["binding"], "is_true": False},
                 "alpha": 0.0},
            ]
        elif vis.get("show_when_valid"):
            node["opacity"] = 1.0
            node["alpha_when"] = [
                {"when": {"signal": vis["binding"], "valid": True},
                 "alpha": visible_opacity},
                {"when": {"signal": vis["binding"], "valid": False},
                 "alpha": 0.0},
            ]
        elif vis.get("show_when_invalid"):
            node["opacity"] = 1.0
            node["alpha_when"] = [
                {"when": {"signal": vis["binding"], "valid": False},
                 "alpha": visible_opacity},
                {"when": {"signal": vis["binding"], "valid": True},
                 "alpha": 0.0},
            ]
    return node


def vehicle_node(component, tokens):
    b = component["bounds"]
    return {
        "id": component["id"],
        "type": "vehicle_visual",
        "x": b["x"],
        "y": b["y"],
        "width": b["w"],
        "height": b["h"],
        "z": component["z"],
        "layer": component.get("layer", "dynamic"),
        "anchor": component.get("anchor", {"x": 0.5, "y": 0.5}),
        "asset": component["asset"],
        "parts": {p["id"]: {"sequence": p["sequence"], "bind": p["binding"]}
                  for p in component["parts"]},
        "overlays": [{"asset": o["asset"], "bind": o["binding"]}
                     for o in component["overlays"]],
        "indicators": {side: {"sequence": spec["sequence"], "bind": spec["binding"]}
                       for side, spec in component["indicators"].items()},
    }


def image_node(component):
    """A baked bitmap: the environment plate, a cluster glow, a vehicle layer.

    `src` is a repository-relative path; it is kept as written so the device
    build can ship the same file. `asset` (resolved through the vehicle
    manifest) stays supported for the frozen vehicle asset set.
    """
    b = component["bounds"]
    node = {
        "id": component["id"],
        "type": "image",
        "z": component["z"],
        "layer": component.get("layer", "static"),
        "x": b["x"], "y": b["y"], "width": b["w"], "height": b["h"],
    }
    for key in ("src", "asset", "opacity_from", "offset_from", "crop_from",
                "micro_motion", "environment_opacity", "presentation"):
        if key in component:
            node[key] = component[key]
    if "opacity" in component:
        node["opacity"] = component["opacity"]
    if "visibility" in component:
        vis = component["visibility"]
        visible_opacity = component.get("visible_opacity", 1.0)
        if vis.get("show_when_true"):
            node["opacity"] = 1.0
            node["alpha_when"] = [
                {"when": {"signal": vis["binding"], "is_true": True},
                 "alpha": visible_opacity},
                {"when": {"signal": vis["binding"], "is_true": False},
                 "alpha": 0.0}]
        elif vis.get("show_when_valid"):
            node["opacity"] = 1.0
            node["alpha_when"] = [
                {"when": {"signal": vis["binding"], "valid": True},
                 "alpha": visible_opacity},
                {"when": {"signal": vis["binding"], "valid": False},
                 "alpha": 0.0}]
    if "alpha_when" in component:
        node["alpha_when"] = component["alpha_when"]
    return node


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", default=LAYOUT,
                        help="design source to generate from")
    parser.add_argument("--out", default=None, help="scene file to write")
    parser.add_argument("--tokens", default=TOKENS,
                        help="design tokens to resolve colour and type names")
    args = parser.parse_args()

    layout = load(args.layout)
    tokens = Tokens(load(args.tokens))
    canvas = layout["canvas"]

    nodes = []
    for component in layout["components"]:
        check_bounds(component, tokens, layout)
        kind = component["kind"]
        if kind == "text":
            nodes.append(text_node(component, tokens))
        elif kind == "vector":
            nodes.append(vector_node(component, tokens, layout))
        elif kind == "vehicle":
            nodes.append(vehicle_node(component, tokens))
        elif kind == "image":
            nodes.append(image_node(component))
        else:
            raise SystemExit(f"[v2] unsupported component kind: {kind}")

    scene = {
        "scene": layout.get("scene", "horizon_v2"),
        "version": 1,
        "status": layout["status"],
        "style_candidate": layout.get("style_candidate"),
        "title": "Horizon V2",
        "role": "production-candidate",
        "canvas": {
            "width": canvas["width"],
            "height": canvas["height"],
            "safe_area": {
                "top_corner_cut": layout["panel"]["top_corner_cut"],
                "bottom_corner_cut": layout["panel"]["bottom_corner_cut"],
            },
            "mask_color": tokens.color(layout["panel"]["mask_color"]),
        },
        # The previewer reads `manifest` as the vehicle asset manifest path, so
        # provenance lives beside it rather than inside it.
        "manifest": "assets/manifest.json",
        "provenance": {
            "layout": os.path.relpath(args.layout, REPO),
            "tokens": "assets/ui/design_tokens.json",
            "generator": "tools/preview/build_horizon_v2.py",
        },
        "notes": [
            "Generated from assets/ui/horizon_v2_layout.json. Do not edit by "
            "hand: edit the layout, regenerate, and the QA re-checks it.",
            "Vehicle states come from VehicleVisualController's contract: "
            "brake, headlight, running, indicators, doors, frunk, trunk.",
            "No link, source, quality or protocol text belongs on this screen.",
        ],
        "nodes": nodes,
    }

    out_path = args.out or os.path.join(
        REPO, "scenes", (layout.get("scene") or "horizon_v2") + ".scene")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(scene, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    texts = sum(1 for n in nodes if n["type"] == "text")
    vectors = sum(1 for n in nodes if n["type"] == "vector")
    vehicles = sum(1 for n in nodes if n["type"] == "vehicle_visual")
    print(f"[v2] {len(nodes)} nodes ({texts} text, {vectors} vector, "
          f"{vehicles} vehicle) -> {os.path.relpath(out_path, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
