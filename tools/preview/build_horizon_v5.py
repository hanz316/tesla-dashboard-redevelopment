#!/usr/bin/env python3
"""HORIZON V5 - structural prototype driven by the approved reference contract.

This agent does not design the V5 look. The human approved a reference image as
the visual source of truth; tools/assets/analyze_v5_reference.py measures it and
this builder consumes those numbers. When the image is absent, every parameter
that would come from it is marked TEMPORARY_PENDING_REFERENCE and the report
says BACKGROUND_ART_REQUIRED - no look is invented to fill the gap.

What is not a look choice, and is therefore implemented as specified:

* the three-zone composition and the frozen functional layout;
* the partial speed arc, mostly dark, active up to the current speed, with the
  range parameterised (0-240 km/h);
* the vehicle at 620-760 px visible width, reached by cropping every vehicle
  layer to the same union alpha box (framing only, no geometry change);
* ground contact, contact shadow, weak reflection and state ground responses;
* the energy rail as a baked rail plus crop;
* the navigation capsule, present only when navigation is valid.

Usage:
    python3 tools/preview/build_horizon_v5.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UI = os.path.join(REPO, "assets", "ui")
SCENES = os.path.join(REPO, "scenes")
GEN = os.path.join(REPO, "tools", "preview", "build_horizon_v2.py")
MEASUREMENTS = os.path.join(UI, "horizon_v5_reference_measurements.json")
V2_TOKENS = os.path.join(UI, "design_tokens.json")

# Composition test. The canvas is 480 tall; the frunk lid raises the union
# silhouette to 178 of the 179 cropped rows. Ground contact at y=440 with a 4 px
# top margin gives scale = (440-4)/178 = 2.45, i.e. 637 px of visible car -
# inside the requested 620-760 px - while every open-panel state still fits.
VEHICLE_CROP = [48, 21, 308, 200]
VEHICLE_SCALE = 2.45
GROUND_Y = 440
SPEED_ARC = {"start_deg": 232.0, "end_deg": 308.0, "max_kph": 240.0,
             "reference_marks": [0, 120, 240]}


def vehicle_box():
    width = int(round((VEHICLE_CROP[2] - VEHICLE_CROP[0]) * VEHICLE_SCALE))
    height = int(round((VEHICLE_CROP[3] - VEHICLE_CROP[1]) * VEHICLE_SCALE))
    y = GROUND_Y - int(round(178 * VEHICLE_SCALE))
    return {"x": 960 - width // 2, "y": y, "w": width, "h": height}


def build_tokens(measurements):
    from_reference = measurements is not None
    palette = (measurements or {}).get("palette") or ["#05090D", "#071017",
                                                      "#0A141C", "#0E1A22"]
    accent = (measurements or {}).get("accent") or "#58C8D8"
    horizon = ((measurements or {}).get("horizon") or {}).get("horizon_row", 300)
    return {
        "schema": "horizon-v5-tokens v1",
        "status": "AWAITING HUMAN VISUAL APPROVAL",
        "reference": {
            "role": "HORIZON_V5_VISUAL_REFERENCE",
            "image": "assets/ui/horizon_v5_reference.png",
            "measurements": os.path.relpath(MEASUREMENTS, REPO),
            "state": ("MEASURED_FROM_REFERENCE" if from_reference
                      else "TEMPORARY_PENDING_REFERENCE"),
            "note": "background bands, horizon row and accent hue come from the "
                    "reference when it is present; otherwise the values below "
                    "are structural placeholders and the report says "
                    "BACKGROUND_ART_REQUIRED",
        },
        "colors": {
            "bg_deep": palette[0], "bg_mid": palette[1 % len(palette)],
            "bg_horizon": palette[2 % len(palette)],
            "bg_ground": palette[3 % len(palette)],
            "ground_sheen": "#101A22", "contact_shadow": "#02060A",
            "reflection": "#0B141B", "glass_fill": "#071017",
            "glass_border": "#12202A", "glass_top_edge": "#9FB6C4",
            "glass_bottom_shade": "#02060A", "primary_text": "#E9EEF3",
            "secondary_text": "#C3CDD7", "muted_text": "#7C8894",
            "accent": accent, "accent_dim": "#1E3A44", "warning": "#D8A657",
            "critical": "#D8674F", "ready": "#7BD2C4", "throw": "#DCD8CC",
        },
        "horizon_row": horizon,
        "typography": {"tiers": {
            "DISPLAY": {"size": 124, "role": "bold", "tracking": -2.0},
            "TITLE": {"size": 62, "role": "bold", "tracking": 0.0},
            "BODY": {"size": 28, "role": "medium", "tracking": 1.2},
            "CAPTION": {"size": 22, "role": "medium", "tracking": 1.6},
            "LABEL": {"size": 16, "role": "medium", "tracking": 2.4}}},
        "spacing": {"zone_gap": 20, "stack_tight": 8, "stack_normal": 16,
                    "stack_loose": 34, "label_gap": 10},
        "radii": {"pill": 10, "bar": 6, "sign": 30, "capsule": 12},
        "opacity": {"muted": 0.55, "dim": 0.38, "inactive_gear": 0.28,
                    "active_gear": 1.0, "arc_inactive": 0.85, "arc_active": 0.95,
                    "shadow": 0.55, "reflection": 0.30, "sheen": 0.45,
                    "glass_fill": 0.70, "glass_top": 0.22, "glass_shade": 0.38},
        "animation": {"why": "declared for the device pass, not implemented here",
                      "state_fade_ms": 220, "navigation_fade_ms": 200,
                      "navigation_slide_px": 12,
                      "indicator_ground_pulse_ms": 420, "road_travel_ms": 900,
                      "arc_ease_ms": 160},
        "cost_model": {"canvas": [1920, 480],
                       "baked_background": "assets/ui/horizon_v5_background.png",
                       "vehicle_layers": "base + panel delta layers, cropped to "
                                         "the union alpha box",
                       "energy_rail": "baked rail + crop",
                       "glass": "9-slice bitmap"},
    }


def text(node_id, x, y, **kw):
    node = {"id": node_id, "kind": "text",
            "bounds": {"x": x, "y": y, "w": kw.pop("w", 120),
                       "h": kw.pop("h", 30)},
            "align": kw.pop("align", "left"), "z": kw.pop("z", 40),
            "layer": kw.pop("layer", "dynamic")}
    node.update(kw)
    return node


def vector(node_id, shape, bounds, colour, **kw):
    node = {"id": node_id, "kind": "vector", "shape": shape, "bounds": bounds,
            "color_token": colour, "z": kw.pop("z", 5),
            "layer": kw.pop("layer", "static"), "opacity": kw.pop("opacity", 1.0)}
    node.update(kw)
    return node


def glass(node_id, x, y, w, h, z=20, visible_when=None, exempt=False, reason=None):
    parts = [
        vector(f"{node_id}.fill", "roundrect", {"x": x, "y": y, "w": w, "h": h},
               "glass_fill", z=z, radius_token="capsule", opacity=0.70,
               stroke_token="glass_border", role="glass"),
        vector(f"{node_id}.edge", "line", {"x": x + 2, "y": y, "w": w - 4, "h": 1},
               "glass_top_edge", z=z + 1, opacity=0.22, role="glass",
               x2=x + w - 2, y2=y),
        vector(f"{node_id}.shade", "line",
               {"x": x + 2, "y": y + h - 1, "w": w - 4, "h": 1},
               "glass_bottom_shade", z=z + 1, opacity=0.38, role="glass",
               x2=x + w - 2, y2=y + h - 1)]
    for part in parts:
        if exempt:
            part["exempt_from_safe_area"] = True
            part["exempt_reason"] = reason
        if visible_when:
            part["layer"] = "dynamic"
            part["visibility"] = visible_when
            part["visible_opacity"] = part["opacity"]
    return parts


def build(measurements):
    tokens = build_tokens(measurements)
    horizon = tokens["horizon_row"]
    components = []

    components.append(vector("env.base", "vgradient",
                             {"x": 0, "y": 0, "w": 1920, "h": 480}, "bg_deep",
                             z=0, exempt_from_safe_area=True, role="environment",
                             color_to_token="bg_mid"))
    components.append(vector("env.horizon.glow", "vgradient",
                             {"x": 380, "y": max(0, horizon - 90), "w": 1160,
                              "h": 96},
                             "bg_horizon", z=1, opacity=0.55,
                             exempt_from_safe_area=True, role="environment",
                             color_to_token="bg_deep"))
    components.append(vector("env.horizon.line", "line",
                             {"x": 520, "y": horizon, "w": 880, "h": 1},
                             "bg_horizon", z=2, opacity=0.35, role="environment",
                             x2=1400, y2=horizon))
    components.append(vector("env.distant.ridge", "polygon",
                             {"x": 240, "y": horizon - 26, "w": 1440, "h": 26},
                             "bg_mid", z=2, opacity=0.55,
                             exempt_from_safe_area=True, role="environment",
                             points=[[240, horizon], [520, horizon - 22],
                                     [780, horizon - 8], [1040, horizon - 26],
                                     [1300, horizon - 10], [1560, horizon - 20],
                                     [1680, horizon]]))
    components.append(vector("stage.ground", "vgradient",
                             {"x": 0, "y": horizon, "w": 1920, "h": 480 - horizon},
                             "bg_ground", z=3, opacity=0.85,
                             exempt_from_safe_area=True, role="stage",
                             color_to_token="bg_deep"))
    components.append(vector("stage.ground.sheen", "polygon",
                             {"x": 500, "y": horizon, "w": 920,
                              "h": 480 - horizon}, "ground_sheen", z=4,
                             opacity=0.45, exempt_from_safe_area=True,
                             role="stage",
                             points=[[760, horizon], [1160, horizon],
                                     [1420, 456], [500, 456]]))
    box = vehicle_box()
    components.append(vector("stage.contact.shadow", "polygon",
                             {"x": box["x"] - 20, "y": GROUND_Y - 26,
                              "w": box["w"] + 40, "h": 34}, "contact_shadow",
                             z=5, opacity=0.55, exempt_from_safe_area=True,
                             role="stage",
                             points=[[box["x"] + 24, GROUND_Y - 22],
                                     [box["x"] + box["w"] - 24, GROUND_Y - 22],
                                     [box["x"] + box["w"] + 8, GROUND_Y + 8],
                                     [box["x"] - 8, GROUND_Y + 8]]))
    components.append(vector("stage.reflection", "vgradient",
                             {"x": box["x"] + 40, "y": GROUND_Y - 4,
                              "w": box["w"] - 80, "h": 32}, "reflection", z=6,
                             opacity=0.30, exempt_from_safe_area=True,
                             role="stage", color_to_token="bg_deep"))
    components.append({
        "id": "vehicle", "kind": "vehicle", "bounds": box,
        "anchor": {"x": 0.5, "y": 0.5}, "z": 30, "layer": "dynamic",
        "asset": "vehicle.base", "crop": VEHICLE_CROP,
        "parts": [{"id": "door_fl", "sequence": "vehicle.door.fl", "binding": "door_fl"},
                  {"id": "door_fr", "sequence": "vehicle.door.fr", "binding": "door_fr"},
                  {"id": "door_rl", "sequence": "vehicle.door.rl", "binding": "door_rl"},
                  {"id": "door_rr", "sequence": "vehicle.door.rr", "binding": "door_rr"},
                  {"id": "frunk", "sequence": "vehicle.frunk", "binding": "frunk"},
                  {"id": "trunk", "sequence": "vehicle.trunk", "binding": "trunk"}],
        "overlays": [{"asset": "vehicle.brake", "binding": "brake"},
                     {"asset": "vehicle.headlight", "binding": "headlight"},
                     {"asset": "vehicle.running", "binding": "position_light"}],
        "indicators": {"left": {"sequence": "vehicle.indicator.left",
                                "binding": "indicator_left"},
                       "right": {"sequence": "vehicle.indicator.right",
                                 "binding": "indicator_right"}},
        "visible_bounds_closed": {
            "x": box["x"] + int(round((51 - VEHICLE_CROP[0]) * VEHICLE_SCALE)),
            "y": box["y"] + int(round((57 - VEHICLE_CROP[1]) * VEHICLE_SCALE)),
            "w": int(round((307 - 51) * VEHICLE_SCALE)),
            "h": int(round((199 - 57) * VEHICLE_SCALE))},
        "visible_bounds_open_union": {
            "x": box["x"] + int(round((48 - VEHICLE_CROP[0]) * VEHICLE_SCALE)),
            "y": box["y"] + int(round((21 - VEHICLE_CROP[1]) * VEHICLE_SCALE)),
            "w": int(round((307 - 48) * VEHICLE_SCALE)),
            "h": int(round((199 - 21) * VEHICLE_SCALE))},
        "permitted_region": {"x": 520, "y": 0, "w": 900, "h": 480},
        "safe_area_exemption": {
            "top": True,
            "reason": "the frunk lid opens to 4 px above the stated top margin "
                      "(measured union top y=4 against a 22 px margin). It stays "
                      "inside the canvas and clear of the calibrated panel mask, "
                      "which cuts x<=115 and x>=1805 at that row; the car spans "
                      "646-1283 there."},
        "crop": VEHICLE_CROP,
        "visible_width_target": [620, 760],
        "ground_contact_band": [420, 460],
        "ground_contact_y": GROUND_Y,
        "exempt_from_safe_area": True,
        "exempt_reason": "the vehicle frame is transparent outside the car; the "
                         "checks use its visible bounds",
        "role": "vehicle"})

    components.append(vector("speed.arc", "arc",
                             {"x": 130, "y": 118, "w": 300, "h": 300},
                             "accent_dim", z=6, opacity=0.85, role="speed",
                             cx=280, cy=360, radius=268,
                             start_deg=SPEED_ARC["start_deg"],
                             end_deg=SPEED_ARC["end_deg"], width_px=8))
    components.append(vector("speed.arc.active", "arc",
                             {"x": 130, "y": 118, "w": 300, "h": 300},
                             "accent", z=7, opacity=0.95, role="speed",
                             cx=280, cy=360, radius=268,
                             start_deg=SPEED_ARC["start_deg"],
                             end_deg=SPEED_ARC["end_deg"], width_px=8,
                             progress={"binding": "speed",
                                       "max": SPEED_ARC["max_kph"],
                                       "from": "start"}))
    for mark in SPEED_ARC["reference_marks"]:
        components.append(vector(f"speed.mark.{mark}", "line",
                                 {"x": 126, "y": 118, "w": 10, "h": 1},
                                 "accent", z=8, opacity=0.55, role="speed",
                                 x2=136, y2=118, width_px=2))
    components.append(text("speed.value", 120, 105, w=300, h=140,
                           **{"binding": "speed", "format": "{}",
                              "invalid_text": "—", "font_token": "DISPLAY",
                              "color_token": "primary_text"}))
    components.append(text("speed.unit", 124, 250, w=120, h=26, text="km/h",
                           font_token="CAPTION", color_token="muted_text"))
    for index, letter in enumerate(("P", "R", "N", "D"), start=1):
        components.append({
            "id": f"gear.{letter.lower()}", "kind": "text",
            "bounds": {"x": 120 + (index - 1) * 44, "y": 283, "w": 30, "h": 34},
            "align": "left", "font_token": "BODY", "color_token": "primary_text",
            "z": 40, "layer": "dynamic", "text": letter,
            "highlight_when_gear": letter, "highlight_color_token": "accent",
            "highlight_opacity_token": "active_gear"})
    components.append(text("gear.unknown", 120, 283, w=30, h=34, text="—",
                           font_token="BODY", color_token="muted_text",
                           visibility={"binding": "gear", "show_when_invalid": True},
                           visible_opacity=1.0))
    components.append(text("driver.temperature", 300, 40, w=120, h=32,
                           **{"binding": "temperature_primary", "format": "{}°C",
                              "invalid_text": "— °C", "font_token": "CAPTION",
                              "color_token": "muted_text"}))
    components.append(text("driver.status", 120, 337, w=220, h=30,
                           **{"binding": "driver_status_text", "format": "{}",
                              "invalid_text": "", "font_token": "CAPTION",
                              "color_token": "muted_text"}))
    components.extend(glass("speedlimit.glass", 316, 240, 76, 76, z=24,
                            visible_when={"binding": "speed_limit",
                                          "show_when_valid": True}))
    components.append(vector("speedlimit.ring", "roundrect",
                             {"x": 324, "y": 248, "w": 60, "h": 60},
                             "critical", z=25, radius_token="sign", opacity=0.0,
                             layer="dynamic", role="sign",
                             visibility={"binding": "speed_limit",
                                         "show_when_valid": True},
                             visible_opacity=0.85))
    components.append(text("speedlimit.value", 316, 262, w=76, h=32,
                           align="center",
                           **{"binding": "speed_limit", "format": "{}",
                              "invalid_text": "", "font_token": "BODY",
                              "color_token": "primary_text",
                              "visibility": {"binding": "speed_limit",
                                             "show_when_valid": True},
                              "visible_opacity": 1.0}))

    components.append(text("energy.range", 1606, 138, w=200, h=74, align="right",
                           **{"binding": "range", "format": "{} km",
                              "invalid_text": "— km", "font_token": "TITLE",
                              "color_token": "primary_text"}))
    components.append(text("energy.range.label", 1606, 216, w=200, h=24,
                           align="right", text="RANGE", font_token="LABEL",
                           color_token="muted_text"))
    components.append(vector("energy.rail", "vticks",
                             {"x": 1758, "y": 264, "w": 10, "h": 132},
                             "accent_dim", z=6, opacity=0.85, role="energy",
                             count=22, major_every=4, width_px=6,
                             major_width_px=10, lit_token="accent",
                             progress={"binding": "actual_soc", "max": 100}))
    components.append(vector("energy.rail.warn", "vticks",
                             {"x": 1758, "y": 264, "w": 10, "h": 132},
                             "warning", z=7, opacity=0.0, role="energy",
                             count=22, major_every=4, width_px=6,
                             major_width_px=10, lit_token="warning",
                             progress={"binding": "actual_soc", "max": 100},
                             visibility={"binding": "actual_soc", "lte": 20},
                             visible_opacity=1.0))
    components.append(text("energy.soc", 1606, 268, w=140, h=36, align="right",
                           **{"binding": "actual_soc", "format": "{}%",
                              "invalid_text": "— %", "font_token": "BODY",
                              "color_token": "secondary_text"}))
    components.append(text("energy.soc.label", 1606, 310, w=140, h=24,
                           align="right", text="SOC", font_token="LABEL",
                           color_token="muted_text"))
    components.append(text("energy.power", 1606, 336, w=200, h=36, align="right",
                           **{"binding": "battery_power", "format": "{} kW",
                              "invalid_text": "— kW", "font_token": "BODY",
                              "color_token": "muted_text"}))
    components.append(text("energy.power.label", 1606, 376, w=200, h=24,
                           align="right", text="POWER", font_token="LABEL",
                           color_token="muted_text"))
    components.append(vector("energy.trend", "line",
                             {"x": 1560, "y": 414, "w": 186, "h": 1},
                             "accent", z=8, opacity=0.0, layer="dynamic",
                             role="energy", x2=1746, y2=414, width_px=2,
                             visibility={"binding": "power_history_valid",
                                         "show_when_true": True},
                             visible_opacity=0.6))
    components.append(text("top.clock", 1606, 40, w=200, h=32, align="right",
                           source="clock", format="%H:%M", font_token="CAPTION",
                           color_token="muted_text"))

    components.extend(glass("nav.capsule", 650, 16, 620, 64, z=20, exempt=True,
                            reason="the capsule floats above the stated safe "
                                   "margin; its content sits inside",
                            visible_when={"binding": "nav_manoeuvre",
                                          "show_when_valid": True}))
    for node_id, x, w, bind, fmt, colour in (
            ("nav.icon", 676, 44, None, "{}", "accent"),
            ("nav.distance", 724, 120, "nav_distance", "{} m", "primary_text"),
            ("nav.instruction", 850, 400, "nav_instruction", "{}", "muted_text")):
        kwargs = {"font_token": "BODY", "color_token": colour,
                  "visibility": {"binding": "nav_manoeuvre", "show_when_valid": True},
                  "visible_opacity": 1.0}
        if bind:
            kwargs.update({"binding": bind, "format": fmt, "invalid_text": ""})
        else:
            kwargs["text"] = "\u21b1"
        components.append(text(node_id, x, 30, w=w, h=36, **kwargs))

    for side in ("left", "right"):
        x = 560 if side == "left" else 1250
        for index in range(3):
            components.append(vector(f"state.{side}.ground{index}", "line",
                                     {"x": x + index * 12, "y": 424 + index * 10,
                                      "w": 120, "h": 1}, "warning", z=12,
                                     opacity=0.0, layer="dynamic", role="state",
                                     x2=x + index * 12 + 120,
                                     y2=424 + index * 10, width_px=2,
                                     visibility={"binding": f"indicator_{side}",
                                                 "show_when_true": True},
                                     visible_opacity=0.40))
    components.append(vector("state.brake.reflection", "polygon",
                             {"x": box["x"], "y": GROUND_Y - 16, "w": box["w"],
                              "h": 40}, "critical", z=11, opacity=0.0,
                             layer="dynamic", role="state",
                             exempt_from_safe_area=True,
                             points=[[box["x"] + 30, GROUND_Y - 12],
                                     [box["x"] + box["w"] - 30, GROUND_Y - 12],
                                     [box["x"] + box["w"] - 60, GROUND_Y + 22],
                                     [box["x"] + 60, GROUND_Y + 22]],
                             visibility={"binding": "brake", "show_when_true": True},
                             visible_opacity=0.24))
    for side, x, x2 in (("left", 420, 250), ("right", 1500, 1670)):
        components.append(vector(f"state.headlight.{side}", "polygon",
                                 {"x": min(x, x2), "y": 320, "w": abs(x2 - x),
                                  "h": 100}, "throw", z=10, opacity=0.0,
                                 layer="dynamic", role="state",
                                 exempt_from_safe_area=True,
                                 points=[[x, 320], [x2, 380], [x2, 420], [x, 350]],
                                 visibility={"binding": "headlight",
                                             "show_when_true": True},
                                 visible_opacity=0.08))
    components.extend(glass("warn.glass", 660, 406, 600, 36, z=29,
                            visible_when={"binding": "warning_active",
                                          "show_when_true": True}))
    components.append(text("warn.text", 660, 424, w=600, h=30, align="center",
                           **{"binding": "warning_text", "format": "{}",
                              "invalid_text": "", "font_token": "CAPTION",
                              "color_token": "warning"}))

    states = ["v5_neutral", "v5_left", "v5_right", "v5_hazard", "v5_brake",
              "v5_headlight", "v5_brake_left", "v5_brake_right",
              "v5_brake_hazard", "v5_door_fl", "v5_door_fr", "v5_door_rl",
              "v5_door_rr", "v5_all_doors", "v5_frunk", "v5_trunk",
              "v5_low_soc", "v5_unknown", "v5_stale", "v5_navigation"]
    names = [f"horizon_v5_{index:02d}_{state}.png"
             for index, state in enumerate(
                 ["neutral", "left_indicator", "right_indicator", "hazard",
                  "brake", "headlight", "brake_left", "brake_right",
                  "brake_hazard", "door_fl", "door_fr", "door_rl", "door_rr",
                  "all_doors", "frunk", "trunk", "low_soc", "unknown", "stale",
                  "navigation"], start=1)]
    # Roles are what the QA and the layer accounting key off, so the navigation
    # and the speed-limit surfaces are labelled explicitly.
    for component in components:
        if component["id"].startswith("nav."):
            component["role"] = "navigation"
        elif component["id"].startswith("speedlimit."):
            component["role"] = "sign"
    layout = {
        "schema": "horizon-v5-layout v1",
        "status": "AWAITING HUMAN VISUAL APPROVAL",
        "scene": "horizon_v5",
        "style_candidate": "HORIZON V5 - pending reference",
        "canvas": {"width": 1920, "height": 480},
        "panel": dict(json.load(open(os.path.join(UI, "horizon_v2_layout.json")))["panel"],
                      mask_color="bg_deep"),
        "safe_area": {"left": 48, "right": 48, "top": 22, "bottom": 24},
        "zones": {"driver": {"x": 60, "right": 430},
                  "vehicle": {"x": 430, "right": 1490},
                  "energy": {"x": 1490, "right": 1860}},
        "layers": {
            "LAYER_0_DEEP_ENVIRONMENT": ["env.base", "env.horizon.glow",
                                         "env.horizon.line", "env.distant.ridge"],
            "LAYER_1_VEHICLE_STAGE": ["stage.ground", "stage.ground.sheen",
                                      "stage.contact.shadow", "stage.reflection",
                                      "vehicle"],
            "LAYER_2_INFORMATION": ["speed.value", "speed.unit", "gear.p",
                                    "gear.r", "gear.n", "gear.d",
                                    "energy.range", "energy.rail",
                                    "energy.soc", "energy.power",
                                    "nav.capsule.fill", "speedlimit.glass.fill",
                                    "warn.glass.fill"],
            "LAYER_3_STATE_FEEDBACK": [c["id"] for c in components
                                       if c.get("role") == "state"],
        },
        "reference_state": tokens["reference"]["state"],
        "forbidden_in_production": json.load(
            open(os.path.join(UI, "horizon_v2_layout.json")))["forbidden_in_production"],
        "components": components,
        "screenshot_states": states,
        "screenshot_names": names,
    }
    return tokens, layout


def main():
    measurements = None
    if os.path.isfile(MEASUREMENTS):
        measurements = json.load(open(MEASUREMENTS))
    tokens, layout = build(measurements)
    tokens["vehicle"] = json.load(open(V2_TOKENS))["vehicle"]
    tokens_path = os.path.join(UI, "horizon_v5_tokens.json")
    layout_path = os.path.join(UI, "horizon_v5_layout.json")
    with open(tokens_path, "w") as fh:
        json.dump(tokens, fh, indent=1, ensure_ascii=False); fh.write("\n")
    with open(layout_path, "w") as fh:
        json.dump(layout, fh, indent=1, ensure_ascii=False); fh.write("\n")
    scene = os.path.join(SCENES, "horizon_v5.scene")
    subprocess.run([sys.executable, GEN, "--layout", layout_path, "--out", scene,
                    "--tokens", tokens_path], check=True)
    box = vehicle_box()
    print(f"[v5] {len(layout['components'])} components -> "
          f"{os.path.relpath(scene, REPO)}")
    print(f"[v5] vehicle {box['w']}x{box['h']} at ({box['x']},{box['y']}), "
          f"ground {GROUND_Y}, reference {tokens['reference']['state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
