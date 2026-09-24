#!/usr/bin/env python3
"""HORIZON V4 - SPATIAL GLASS COCKPIT.

V3 was rejected because its three candidates were the same composition with
different decorative lines, and because a thick cyan diagonal carried no
meaning. V4 replaces the visual language instead of decorating it, and builds
the screen as four perceptual depth layers rather than a flat canvas:

    LAYER 0  deep environment     dark blue-black gradient, broad horizon glow
    LAYER 1  vehicle stage        wide dark road, sheen, lane edges, contact
                                  shadow, floor reflection, rim light
    LAYER 2  information glass    pre-rendered-style glass surfaces used only
                                  where functional: navigation, warning,
                                  speed-limit sign
    LAYER 3  state feedback       road-surface chevrons, brake reflection,
                                  headlight wedges, door contours, panel
                                  under-lights, energy flow direction

Technology comes from depth, light, material and state reaction - not from
drawing more cyan lines. Cyan is sparse on purpose: lane edges, the active part
of the speed sweep, the energy surface and the navigation cue. Nothing is a
filled cyan polygon and there is no beam across the screen.

This script is the deterministic source: it writes the design tokens, the
layout, the generated scene and the spec document from one set of numbers, so
the document cannot drift from the scene.

Usage:
    python3 tools/preview/build_horizon_v4.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UI = os.path.join(REPO, "assets", "ui")
SCENES = os.path.join(REPO, "scenes")
GEN = os.path.join(REPO, "tools", "preview", "build_horizon_v2.py")
BASE = os.path.join(UI, "horizon_v2_layout.json")

TOKENS = {
    "schema": "horizon-v4-tokens v1",
    "scope": "horizon-v4-spatial-glass",
    "colors": {
        "bg_top": "#05090D",
        "bg_mid": "#071017",
        "bg_bottom": "#0A141C",
        "glass_fill": "#071017",
        "glass_border": "#101C26",
        "glass_top_edge": "#9FB6C4",
        "glass_bottom_shade": "#02060A",
        "primary_text": "#E9EEF3",
        "secondary_text": "#C3CDD7",
        "muted_text": "#7C8894",
        "accent": "#58C8D8",
        "accent_dim": "#1E3A44",
        "road": "#071017",
        "road_sheen": "#0A141C",
        "lane_edge": "#1E3A44",
        "shadow": "#02060A",
        "warning": "#D8A657",
        "critical": "#D8674F",
        "ready": "#7BD2C4",
        "wedge": "#E4E0D6",
    },
    "typography": {
        "why": "hierarchy through weight, tracking and size; no new typeface",
        "tiers": {
            "DISPLAY": {"size": 124, "role": "bold", "tracking": -2.0},
            "TITLE": {"size": 62, "role": "bold", "tracking": 0.0},
            "BODY": {"size": 28, "role": "medium", "tracking": 1.2},
            "CAPTION": {"size": 22, "role": "medium", "tracking": 1.6},
            "LABEL": {"size": 16, "role": "medium", "tracking": 2.4},
        },
    },
    "spacing": {"zone_gap": 20, "stack_tight": 8, "stack_normal": 16,
                "stack_loose": 34, "label_gap": 10},
    "radii": {"pill": 10, "bar": 6, "sign": 30, "capsule": 12},
    "opacity": {
        "muted": 0.55, "dim": 0.38, "inactive_gear": 0.28,
        "active_gear": 1.0, "road": 0.90, "sheen": 0.55,
        "lane": 0.25, "rim_light": 0.18, "shadow": 0.50,
        "reflection": 0.35, "horizon_glow": 0.35, "atmosphere": 0.30,
        "arc_inactive": 0.90, "arc_active": 0.90,
        "glass_fill": 0.72, "glass_border": 0.80, "glass_top": 0.25,
        "glass_shade": 0.40, "chevron": 0.50, "brake_reflection": 0.22,
        "headlight_wedge": 0.10, "door_contour": 0.55,
        "panel_underlight": 0.45, "flow": 0.85,
    },
    "animation": {
        "why": "declared now, implemented after visual approval",
        "chevron_stage_ms": 180,
        "chevron_travel_px": 26,
        "navigation_fade_ms": 200,
        "navigation_slide_px": 12,
        "state_fade_ms": 220,
        "flow_travel_ms": 900,
        "arc_ease_ms": 160,
    },
    "cost_model": {
        "why": "static effects are pre-rendered; runtime does text, opacity, "
               "crop, translation and small state overlays only",
        "canvas": [1920, 480],
        "baked_background_asset": "assets/ui/horizon_v4_background.png",
        "glass_asset": "9-slice bitmap, one per surface size class",
    },
}


def txt(node_id, x, y, size=22, align="left", colour="muted_text",
        role="medium", tracking=1.6, **kw):
    node = {"id": node_id, "kind": "text", "bounds": {"x": x, "y": y, "w": 40,
                                                      "h": size + 4},
            "align": align, "font_token": "CAPTION", "color_token": colour,
            "z": 40, "layer": "dynamic"}
    node.update(kw)
    return node


def build_text(node_id, x, y, text=None, bind=None, fmt="{}", invalid="",
               align="left", size=22, colour="muted_text", z=40,
               layer="dynamic", visible_when=None, visible_opacity=None,
               width=120, height=None, font_token=None, source=None,
               format=None):
    node = {"id": node_id, "kind": "text",
            "bounds": {"x": x, "y": y, "w": width, "h": height or size + 8},
            "align": align, "color_token": colour, "z": z, "layer": layer}
    if font_token:
        node["font_token"] = font_token
    else:
        node["font_token"] = "CAPTION"
    if text is not None:
        node["text"] = text
    if source:
        node["source"] = source
        node["format"] = format or "{}"
    elif bind:
        node["binding"] = bind
        node["format"] = format or fmt
        node["invalid_text"] = invalid
    if visible_when:
        node["visibility"] = visible_when
        node["visible_opacity"] = visible_opacity if visible_opacity is not None else 1.0
    return node


def vector(node_id, shape, bounds, colour, opacity=1.0, z=5, layer="static",
           role=None, exempt=False, **kw):
    node = {"id": node_id, "kind": "vector", "shape": shape, "bounds": bounds,
            "color_token": colour, "opacity": opacity, "z": z, "layer": layer,
            "role": role}
    if exempt:
        node["exempt_from_safe_area"] = True
    node.update(kw)
    return node


def glass(node_id, x, y, w, h, radius=12, z=20, exempt=False, reason=None,
          visible_when=None):
    """Pre-rendered-style glass: fill, 1 px border, top edge, bottom shade.

    No runtime blur: the production asset is a 9-slice bitmap with exactly this
    structure, so the static render and the device agree.
    """
    parts = [
        vector(f"{node_id}.fill", "roundrect", {"x": x, "y": y, "w": w, "h": h},
               "glass_fill", opacity=0.72, z=z, radius_token="capsule",
               layer="static", stroke_token="glass_border", role="glass"),
        vector(f"{node_id}.edge", "line", {"x": x + 2, "y": y, "w": w - 4, "h": 1},
               "glass_top_edge", opacity=0.25, z=z + 1, role="glass",
               x2=x + w - 2, y2=y),
        vector(f"{node_id}.shade", "line",
               {"x": x + 2, "y": y + h - 1, "w": w - 4, "h": 1},
               "glass_bottom_shade", opacity=0.40, z=z + 1, role="glass",
               x2=x + w - 2, y2=y + h - 1),
    ]
    if exempt:
        for part in parts:
            part["exempt_from_safe_area"] = True
            part["exempt_reason"] = reason
    if visible_when:
        # A glass surface exists only because the thing it carries exists. The
        # first version left the navigation capsule ungated, which put 40 253
        # pixels of "empty capsule" on a screen with no route - the exact thing
        # the zero-navigation rule is for.
        for part in parts:
            part["layer"] = "dynamic"
            part["visibility"] = visible_when
            part["visible_opacity"] = part["opacity"]
    return parts


def build_layout():
    """Every element with its exact numbers; nothing is left to judgement."""
    components = []

    # ---- LAYER 0: deep environment ------------------------------------
    components.append(vector("env.depth", "vgradient",
                             {"x": 0, "y": 0, "w": 1920, "h": 480},
                             "bg_top", z=0, exempt=True, role="environment",
                             color_to_token="bg_bottom"))
    components.append(vector("env.horizon.glow", "radial",
                             {"x": 340, "y": 150, "w": 1240, "h": 290},
                             "bg_bottom", opacity=0.35, z=1, exempt=True,
                             role="environment", color_to_token="bg_top"))
    components.append(vector("env.atmosphere", "vgradient",
                             {"x": 300, "y": 248, "w": 1320, "h": 56},
                             "bg_mid", opacity=0.30, z=1, exempt=True,
                             role="environment", color_to_token="bg_bottom"))

    # ---- LAYER 1: vehicle stage ---------------------------------------
    components.append(vector("stage.road", "polygon",
                             {"x": 300, "y": 296, "w": 1320, "h": 160},
                             "road", opacity=0.90, z=2, exempt=True,
                             role="stage",
                             points=[[700, 296], [1220, 296], [1620, 456],
                                     [300, 456]]))
    components.append(vector("stage.sheen", "polygon",
                             {"x": 620, "y": 296, "w": 680, "h": 160},
                             "road_sheen", opacity=0.55, z=3, exempt=True,
                             role="stage",
                             points=[[830, 296], [1090, 296], [1300, 456],
                                     [620, 456]]))
    components.append(vector("stage.lane.left", "line",
                             {"x": 620, "y": 296, "w": 280, "h": 160},
                             "lane_edge", opacity=0.25, z=4, role="stage",
                             x2=900, y2=296, width_px=1))
    components.append(vector("stage.lane.right", "line",
                             {"x": 1020, "y": 296, "w": 280, "h": 160},
                             "lane_edge", opacity=0.25, z=4, role="stage",
                             x2=1300, y2=456, width_px=1))
    components.append(vector("stage.contact.shadow", "polygon",
                             {"x": 720, "y": 398, "w": 480, "h": 34},
                             "shadow", opacity=0.50, z=4, exempt=True,
                             role="stage",
                             points=[[762, 400], [1158, 400], [1200, 432],
                                     [720, 432]]))
    components.append(vector("stage.reflection", "vgradient",
                             {"x": 740, "y": 402, "w": 440, "h": 54},
                             "bg_mid", opacity=0.35, z=5, exempt=True,
                             role="stage", color_to_token="bg_top"))
    components.append(vector("stage.rim.light", "line",
                             {"x": 762, "y": 402, "w": 396, "h": 1},
                             "accent", opacity=0.18, z=6, role="stage",
                             x2=1158, y2=402, width_px=1))

    # ---- the vehicle, unchanged in size and position -------------------
    # The vehicle is the only element V4 inherits: every information, glass and
    # state element below is rebuilt with V4 numbers. That is what makes this a
    # new architecture rather than V3's decoration pass on the same screen.
    base = json.load(open(BASE))
    for component in base["components"]:
        if component["id"] == "vehicle":
            vehicle = json.loads(json.dumps(component))
            vehicle["z"] = 30
            components.append(vehicle)

    # ---- LAYER 2 / speed module ----------------------------------------
    components.append(vector("speed.sweep", "arc",
                             {"x": 130, "y": 118, "w": 300, "h": 300},
                             "accent_dim", opacity=0.90, z=6, role="speed",
                             cx=280, cy=360, radius=268,
                             start_deg=232, end_deg=308, width_px=8))
    components.append(vector("speed.sweep.active", "arc",
                             {"x": 130, "y": 118, "w": 300, "h": 300},
                             "accent", opacity=0.90, z=7, role="speed",
                             cx=280, cy=360, radius=268,
                             start_deg=232, end_deg=308, width_px=8,
                             progress={"binding": "speed", "max": 200,
                                       "from": "start"}))
    components.append(vector("speed.sweep.marker.start", "line",
                             {"x": 126, "y": 118, "w": 8, "h": 1},
                             "accent", opacity=0.60, z=8, role="speed",
                             x2=134, y2=118, width_px=2))
    components.append(vector("speed.sweep.marker.end", "line",
                             {"x": 426, "y": 118, "w": 8, "h": 1},
                             "accent", opacity=0.60, z=8, role="speed",
                             x2=434, y2=118, width_px=2))
    components.append(build_text("speed.value", 120, 105, bind="speed",
                                 invalid="—", size=124, colour="primary_text",
                                 font_token="DISPLAY", width=300, height=140))
    components.append(build_text("speed.unit", 124, 250, text="km/h",
                                 size=22, colour="muted_text"))
    for index, (letter, gear_index) in enumerate((("P", 1), ("R", 2),
                                                  ("N", 3), ("D", 4))):
        components.append({
            "id": f"gear.{letter.lower()}", "kind": "text",
            "bounds": {"x": 120 + index * 44, "y": 283, "w": 30, "h": 34},
            "align": "left", "font_token": "BODY", "color_token": "primary_text",
            "z": 40, "layer": "dynamic", "text": letter,
            "highlight_when_gear": letter, "highlight_color_token": "accent",
            "highlight_opacity_token": "active_gear"})
    components.append(build_text("gear.unknown", 120, 283, text="—", size=28,
                                 colour="muted_text", width=30, height=34,
                                 font_token="BODY",
                                 visible_when={"binding": "gear",
                                               "show_when_invalid": True}))
    components.append(build_text("driver.status", 120, 337,
                                 bind="driver_status_text", invalid="",
                                 width=220, height=30))

    # speed limit: a compact road-sign element on the approved band
    components.extend(glass("speedlimit.glass", 300, 236, 76, 76, radius=30,
                            z=24,
                            visible_when={"binding": "speed_limit",
                                          "show_when_valid": True}))
    components.append(vector("speedlimit.ring", "roundrect",
                             {"x": 308, "y": 244, "w": 60, "h": 60},
                             "critical", opacity=0.0, z=25, radius_token="sign",
                             layer="dynamic", role="sign",
                             visibility={"binding": "speed_limit",
                                         "show_when_valid": True},
                             visible_opacity=0.85))
    components.append(build_text("speedlimit.value", 300, 262,
                                 bind="speed_limit", fmt="{}", invalid="",
                                 align="center", size=28,
                                 colour="primary_text", width=76, height=32,
                                 font_token="BODY",
                                 visible_when={"binding": "speed_limit",
                                               "show_when_valid": True}))

    # ---- energy module --------------------------------------------------
    components.append(build_text("energy.range", 1606, 138, bind="range",
                                 fmt="{} km", invalid="— km", align="right",
                                 size=62, colour="primary_text",
                                 font_token="TITLE", width=200, height=74))
    components.append(build_text("energy.range.label", 1606, 216,
                                 text="RANGE", align="right", size=16,
                                 colour="muted_text", width=200, height=24,
                                 font_token="LABEL"))
    components.append(vector("energy.surface", "vticks",
                             {"x": 1748, "y": 264, "w": 8, "h": 116},
                             "accent_dim", opacity=0.85, z=6, role="energy",
                             count=20, major_every=4, width_px=6,
                             major_width_px=10, lit_token="accent",
                             progress={"binding": "actual_soc", "max": 100}))
    components.append(vector("energy.surface.warn", "vticks",
                             {"x": 1748, "y": 264, "w": 8, "h": 116},
                             "warning", opacity=0.0, z=7, role="energy",
                             count=20, major_every=4, width_px=6,
                             major_width_px=10, lit_token="warning",
                             progress={"binding": "actual_soc", "max": 100},
                             visibility={"binding": "actual_soc", "lte": 20},
                             visible_opacity=1.0))
    components.append(build_text("energy.soc", 1606, 276, bind="actual_soc",
                                 fmt="{}%", invalid="— %", align="right",
                                 size=28, colour="secondary_text", width=120,
                                 height=36, font_token="BODY"))
    components.append(build_text("energy.soc.label", 1606, 316, text="SOC",
                                 align="right", size=16, colour="muted_text",
                                 width=120, height=24, font_token="LABEL"))
    components.append(build_text("energy.power", 1606, 336,
                                 bind="battery_power", fmt="{} kW",
                                 invalid="— kW", align="right", size=28,
                                 colour="muted_text", width=200, height=36,
                                 font_token="BODY"))
    # flow direction: consumption in (accent), regen out (warning)
    components.append(vector("energy.flow.consume", "line",
                             {"x": 1690, "y": 362, "w": 34, "h": 1},
                             "accent", opacity=0.0, z=8, role="state",
                             layer="dynamic", x2=1724, y2=362, width_px=3,
                             visibility={"binding": "battery_power",
                                         "gte": 0.5},
                             visible_opacity=0.85))
    components.append(vector("energy.flow.regen", "line",
                             {"x": 1690, "y": 376, "w": 34, "h": 1},
                             "warning", opacity=0.0, z=8, role="state",
                             layer="dynamic", x2=1724, y2=376, width_px=3,
                             visibility={"binding": "battery_power",
                                         "lte": -0.5},
                             visible_opacity=0.85))

    # ---- top information ------------------------------------------------
    components.append(build_text("top.temperature", 500, 57,
                                 bind="temperature_primary", fmt="{}°C",
                                 invalid="—°C", size=22, colour="muted_text",
                                 width=120, height=34))
    components.append(build_text("top.clock", 1606, 57, align="right",
                                 size=22, colour="muted_text", width=200,
                                 height=34, source="clock", format="%H:%M"))

    # ---- navigation: a glass capsule that emerges from the scene --------
    components.extend(glass("nav.capsule", 650, 16, 620, 64, radius=12, z=20,
                            visible_when={"binding": "nav_manoeuvre",
                                          "show_when_valid": True},
                            exempt=True,
                            reason="the capsule floats 6 px above the stated "
                                   "safe margin; its text sits at y=48, inside "
                                   "it"))
    components.append(vector("nav.leading", "line",
                             {"x": 650, "y": 26, "w": 3, "h": 44},
                             "accent", opacity=0.0, z=22, role="navigation",
                             layer="dynamic", x2=653, y2=70, width_px=3,
                             visibility={"binding": "nav_manoeuvre",
                                         "show_when_valid": True},
                             visible_opacity=0.85))
    # The icon is a static glyph: the manoeuvre *text* would duplicate the
    # instruction, and the projection uses nav_manoeuvre as the gate for the
    # whole capsule.
    components.append(build_text("nav.icon", 676, 30, text="↱",
                                 size=28, colour="accent", width=44,
                                 height=36, font_token="BODY",
                                 visible_when={"binding": "nav_manoeuvre",
                                               "show_when_valid": True}))
    components.append(build_text("nav.distance", 724, 30,
                                 bind="nav_distance", fmt="{} m", invalid="",
                                 size=28, colour="primary_text", width=120,
                                 height=36, font_token="BODY",
                                 visible_when={"binding": "nav_manoeuvre",
                                               "show_when_valid": True}))
    components.append(build_text("nav.instruction", 850, 30,
                                 bind="nav_instruction", fmt="{}", invalid="",
                                 size=28, colour="muted_text", width=400,
                                 height=36, font_token="BODY",
                                 visible_when={"binding": "nav_manoeuvre",
                                               "show_when_valid": True}))

    # ---- LAYER 3: state feedback ---------------------------------------
    for index, y in enumerate((352, 380, 408)):
        components.append(vector(f"state.indicator.left{index}", "line",
                                 {"x": 618 + index * 10, "y": y, "w": 96,
                                  "h": 1}, "warning", opacity=0.0, z=12,
                                 role="state", layer="dynamic",
                                 x2=618 + index * 10 + 96, y2=y, width_px=2,
                                 visibility={"binding": "indicator_left",
                                             "show_when_true": True},
                                 visible_opacity=0.50))
        components.append(vector(f"state.indicator.right{index}", "line",
                                 {"x": 1206 - index * 10, "y": y, "w": 96,
                                  "h": 1}, "warning", opacity=0.0, z=12,
                                 role="state", layer="dynamic",
                                 x2=1206 - index * 10 + 96, y2=y, width_px=2,
                                 visibility={"binding": "indicator_right",
                                             "show_when_true": True},
                                 visible_opacity=0.50))
    components.append(vector("state.brake.reflection", "polygon",
                             {"x": 800, "y": 402, "w": 320, "h": 40},
                             "critical", opacity=0.0, z=11, role="state",
                             layer="dynamic", exempt=True,
                             points=[[840, 402], [1080, 402], [1120, 440],
                                     [800, 440]],
                             visibility={"binding": "brake",
                                         "show_when_true": True},
                             visible_opacity=0.22))
    for side, sign in (("l", -1), ("r", 1)):
        components.append(vector(f"state.headlight.{side}", "polygon",
                                 {"x": 1120 if sign > 0 else 620, "y": 300,
                                  "w": 440, "h": 140},
                                 "wedge", opacity=0.0, z=10, role="state",
                                 layer="dynamic", exempt=True,
                                 points=([[1160, 300], [1560, 396],
                                          [1500, 424], [1160, 330]]
                                         if sign > 0 else
                                         [[760, 300], [360, 396], [420, 424],
                                          [760, 330]]),
                                 visibility={"binding": "headlight",
                                             "show_when_true": True},
                                 visible_opacity=0.10))
    for door, (x, y) in (("fl", (700, 168)), ("fr", (1160, 168)),
                         ("rl", (700, 300)), ("rr", (1160, 300))):
        components.append(vector(f"state.door.{door}", "line",
                                 {"x": x, "y": y, "w": 64, "h": 1},
                                 "warning", opacity=0.0, z=11, role="state",
                                 layer="dynamic", x2=x + 64, y2=y, width_px=2,
                                 visibility={"binding": f"door_{door}",
                                             "show_when_true": True},
                                 visible_opacity=0.55))
    components.append(vector("state.frunk.underlight", "line",
                             {"x": 900, "y": 196, "w": 120, "h": 1},
                             "warning", opacity=0.0, z=11, role="state",
                             layer="dynamic", x2=1020, y2=196, width_px=2,
                             visibility={"binding": "frunk",
                                         "show_when_true": True},
                             visible_opacity=0.45))
    components.append(vector("state.trunk.underlight", "line",
                             {"x": 900, "y": 404, "w": 120, "h": 1},
                             "warning", opacity=0.0, z=11, role="state",
                             layer="dynamic", x2=1020, y2=404, width_px=2,
                             visibility={"binding": "trunk",
                                         "show_when_true": True},
                             visible_opacity=0.45))
    components.extend(glass("warn.glass", 660, 406, 600, 36, radius=10, z=29,
                            visible_when={"binding": "warning_active",
                                          "show_when_true": True}))
    components.append(build_text("warn.text", 660, 424, bind="warning_text",
                                 fmt="{}", invalid="", align="center",
                                 size=22, colour="warning", width=600,
                                 height=30))

    layout = {
        "schema": "horizon-v4-layout v1",
        "status": "AWAITING HUMAN VISUAL APPROVAL",
        "scene": "horizon_v4",
        "style_candidate": "HORIZON V4 - SPATIAL GLASS COCKPIT",
        "canvas": {"width": 1920, "height": 480},
        "panel": dict(base["panel"], mask_color="bg_top"),
        "safe_area": base["safe_area"],
        "zones": base["zones"],
        "tokens": {"colors": "assets/ui/horizon_v4_tokens.json#colors",
                   "typography": "assets/ui/horizon_v4_tokens.json#typography"},
        "layers": {
            "LAYER_0_DEEP_ENVIRONMENT": ["env.depth", "env.horizon.glow",
                                         "env.atmosphere"],
            "LAYER_1_VEHICLE_STAGE": ["stage.road", "stage.sheen",
                                      "stage.lane.left", "stage.lane.right",
                                      "stage.contact.shadow",
                                      "stage.reflection", "stage.rim.light",
                                      "vehicle"],
            "LAYER_2_INFORMATION_GLASS": ["nav.capsule", "speedlimit.glass",
                                          "warn.glass"],
            "LAYER_3_STATE_FEEDBACK": [c["id"] for c in components
                                       if c.get("role") == "state"],
        },
        "components": components,
        "forbidden_in_production": base["forbidden_in_production"],
        "screenshot_states": [
            "h4_neutral", "h4_left", "h4_right", "h4_hazard", "h4_brake",
            "h4_headlight", "h4_brake_left", "h4_door_fl", "h4_all_doors",
            "h4_frunk", "h4_trunk", "h4_low_soc", "h4_navigation",
            "h4_unknown"],
        "screenshot_names": [
            "horizon_v4_01_neutral.png", "horizon_v4_02_left_indicator.png",
            "horizon_v4_03_right_indicator.png", "horizon_v4_04_hazard.png",
            "horizon_v4_05_brake.png", "horizon_v4_06_headlight.png",
            "horizon_v4_07_brake_left.png", "horizon_v4_08_door_fl.png",
            "horizon_v4_09_all_doors.png", "horizon_v4_10_frunk.png",
            "horizon_v4_11_trunk.png", "horizon_v4_12_low_soc.png",
            "horizon_v4_13_navigation.png", "horizon_v4_14_unknown.png"],
    }
    return layout


def main():
    layout = build_layout()
    tokens_path = os.path.join(UI, "horizon_v4_tokens.json")
    # The vehicle measurements are shared with the approved token set: they are
    # properties of the Model A renders, not of a style.
    TOKENS["vehicle"] = json.load(
        open(os.path.join(UI, "design_tokens.json")))["vehicle"]
    layout_path = os.path.join(UI, "horizon_v4_layout.json")
    with open(tokens_path, "w") as fh:
        json.dump(TOKENS, fh, indent=1, ensure_ascii=False); fh.write("\n")
    with open(layout_path, "w") as fh:
        json.dump(layout, fh, indent=1, ensure_ascii=False); fh.write("\n")
    scene = os.path.join(SCENES, "horizon_v4.scene")
    subprocess.run([sys.executable, GEN, "--layout", layout_path, "--out", scene,
                    "--tokens", tokens_path], check=True)
    print(f"[v4] {len(layout['components'])} components -> "
          f"{os.path.relpath(scene, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
