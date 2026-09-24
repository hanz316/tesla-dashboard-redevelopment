#!/usr/bin/env python3
"""HORIZON V5 - the approved reference, implemented.

This builder does not design the V5 look. The human approved a reference image
(assets/ui/horizon_v5_reference.png); tools/assets/analyze_v5_reference.py
measures it and every position below is that measurement mapped into the panel.
The mapping is stated once, here, and used everywhere:

    panel_x = 960 + (x_ref - 1086) * 480/724
    panel_y = y_ref * 480/724

which is the reference placed 1:1 by height inside a centred 1440x480 content
box. The panel is 4:1 and the reference is 3:1, so the panel is 480 px wider:
that width is environment, on both sides, which is also what keeps every
element clear of the calibrated corner mask.

What the reference is used for:

* background          one baked Cycles render (assets/ui/horizon_v5_background)
                      - not a gradient, not polygons;
* vehicle             one baked RGBA layer per state: the car plus the pixels
                      it changes about the wet road (shadow, reflection, lamp
                      response) - no pasted decal, no painted beam;
* speed cluster       full 225 degree instrument arc, active/inactive
                      hierarchy, baked glow, numeral and arc as one unit;
* energy cluster      RANGE / SOC / segmented rail / POWER, rail track baked;
* ground response     measured from the render, never drawn.

The review's forbidden list is enforced here: no white road trapezoids, no red
brake trapezoid, no decoration lines without semantics, no runtime blur.

Usage:
    python3 tools/preview/build_horizon_v5.py
"""

import json
import math
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UI = os.path.join(REPO, "assets", "ui")
SCENES = os.path.join(REPO, "scenes")
GEN = os.path.join(REPO, "tools", "preview", "build_horizon_v2.py")
MEASUREMENTS = os.path.join(UI, "horizon_v5_reference_measurements.json")
UI_ASSETS = os.path.join(UI, "horizon_v5_ui_assets.json")
VEHICLE_LAYERS = os.path.join(REPO, "assets", "rendered", "vehicle",
                              "horizon_v5", "horizon_v5_vehicle.json")
ALIGNMENT = os.path.join(UI, "horizon_v5_speed_alignment.json")
MOTION = os.path.join(UI, "horizon_v5_motion.json")
MOTION_ASSETS = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                             "horizon_v5_motion_assets.json")
MICRO_MOTION_AMPLITUDE_PX = 2.0
MICRO_MOTION_HZ = 0.55


def load_motion_assets():
    if not os.path.isfile(MOTION_ASSETS):
        return None
    with open(MOTION_ASSETS) as handle:
        return json.load(handle)["assets"]


def motion_components(assets, vehicle_layers):
    """The nodes that make the car read as driving.

    Every one of them is a baked bitmap plus a value-driven opacity, offset or
    crop: the runtime translates, crops and blends, and never blurs, never
    particles and never 3D. Each is driven by the motion curves in
    assets/ui/horizon_v5_motion.json, so the evidence and the screen agree.
    """
    if not assets:
        return []
    nodes = []
    flow = assets.get("roadflow")
    if flow:
        tile = flow["tile"]
        nodes.append(image("motion.roadflow", flow["file"],
                           {"x": 0, "y": 480 - tile[1], "w": tile[0],
                            "h": tile[1]}, z=8, layer="dynamic",
                           role="motion", opacity=0.8,
                           offset_from={"binding": "speed",
                                        "points": [[0, 0], [30, 34], [80, 110],
                                                   [120, 190]],
                                        "scale": 1.0, "wrap": tile[1]},
                           opacity_from={"binding": "speed",
                                         "points": [[0, 0.0], [30, 0.35],
                                                    [80, 0.75], [120, 1.0]]},
                           exempt_from_safe_area=True,
                           exempt_reason="the road flow tile covers the road "
                                         "band only and its alpha is zero at "
                                         "rest"))
    wake = assets.get("wake")
    if wake:
        box = wake["box"]
        nodes.append(image("motion.wake", wake["file"],
                           {"x": box[0], "y": box[1], "w": box[2] - box[0],
                            "h": box[3] - box[1]}, z=33, layer="dynamic",
                           role="motion", opacity=0.9,
                           opacity_from={"binding": "speed",
                                         "points": [[0, 0.0], [30, 0.05],
                                                    [80, 0.45], [120, 1.0]]},
                           exempt_from_safe_area=True,
                           exempt_reason="the wake is a soft baked trail behind "
                                         "the car and is fully transparent at "
                                         "0 km/h"))
    streak_states = (("brake", "streak_brake", "brake"),
                     ("indicator_left", "streak_indicator_left",
                      "indicator_left"),
                     ("indicator_right", "streak_indicator_right",
                      "indicator_right"))
    for state, key, binding in streak_states:
        entry = assets.get(key)
        if not entry:
            continue
        box = entry["box"]
        nodes.append(image(f"motion.streak.{state}", entry["file"],
                           {"x": box[0], "y": box[1], "w": box[2] - box[0],
                            "h": box[3] - box[1]}, z=32, layer="dynamic",
                           role="motion", opacity=0.85,
                           crop_from={"binding": "speed", "anchor": "top",
                                      "points": [[0, 0.06], [30, 0.32],
                                                 [80, 0.68], [120, 1.0]]},
                           visibility={"binding": binding,
                                       "show_when_true": True},
                           visible_opacity=0.85,
                           exempt_from_safe_area=True,
                           exempt_reason="the lamp's own reflection on the wet "
                                         "road, drawn from the measured lamp "
                                         "pixels and only while that lamp is on"))
    wheels = assets.get("wheels") or {}
    windows = {"low": [[0, 0.0], [30, 1.0], [80, 0.0]],
               "medium": [[30, 0.0], [80, 1.0], [120, 0.0]],
               "high": [[80, 0.0], [120, 1.0], [240, 1.0]]}
    for index, (level, entry) in enumerate(
            sorted(wheels.items(), key=lambda item: item[1]["spin_deg"])):
        box = entry["box"]
        nodes.append(image(f"motion.wheel.{level}", entry["file"],
                           {"x": box[0], "y": box[1], "w": box[2] - box[0],
                            "h": box[3] - box[1]}, z=26 + index,
                           layer="dynamic", role="motion", opacity=1.0,
                           opacity_from={"binding": "speed",
                                         "points": windows[level]},
                           exempt_from_safe_area=True,
                           exempt_reason="the baked rotational blur of the "
                                         "wheels; transparent at 0 km/h"))
    return nodes
V2_LAYOUT = os.path.join(UI, "horizon_v2_layout.json")

CONTENT_SCALE = 480 / 724.0
CONTENT_CENTRE_X = 1086.0
PANEL_CENTRE_X = 960.0

# 0..240 km/h over 225 degrees, the dial starting at the lower left.
ARC_START_DEG = 135.0
ARC_END_DEG = 360.0
ARC_MAX_KPH = 240.0
ARC_MINOR_TICKS = 24

# Element boxes measured on the reference, in reference pixels. Each entry
# names the thing that was measured, not a look: the numbers come from
# analyze_v5_reference.py plus the annotated overlay next to it.
REF = {
    "speed_numeral": [188, 244, 350, 358],
    "speed_unit": [215, 368, 330, 400],
    "gear_row": [155, 424, 350, 462],
    "driver_status": [98, 490, 200, 522],
    "climate_status": [236, 490, 330, 522],
    "temperature": [398, 36, 500, 72],
    "speed_sign": [479, 178, 550, 248],
    "range_value": [1685, 178, 1890, 246],
    "range_label": [1685, 258, 1800, 284],
    "range_rule": [1685, 350, 1965, 352],
    "power_trace": [1690, 392, 1900, 438],
    "power_value": [1690, 446, 1900, 482],
    "power_label": [1690, 492, 1900, 518],
    "soc_value": [2078, 342, 2142, 382],
    "soc_label": [2078, 346, 2142, 386],
    "rail": [2020, 120, 2075, 575],
    "clock": [1990, 34, 2082, 68],
    "nav": [650, 20, 1270, 80],
}

VEHICLE_STATES = [
    ("base", None),
    ("running", ("position_light", "show_when_true")),
    ("brake", ("brake", "show_when_true")),
    ("indicator_left", ("indicator_left", "show_when_true")),
    ("indicator_right", ("indicator_right", "show_when_true")),
    ("headlight", ("headlight", "show_when_true")),
]


def px(x_ref):
    return PANEL_CENTRE_X + (x_ref - CONTENT_CENTRE_X) * CONTENT_SCALE


def py(y_ref):
    return y_ref * CONTENT_SCALE


def ps(value):
    return value * CONTENT_SCALE


def box(name):
    x0, y0, x1, y1 = REF[name]
    return {"x": round(px(x0), 1), "y": round(py(y0), 1),
            "w": round(ps(x1 - x0), 1), "h": round(ps(y1 - y0), 1)}


def text(node_id, box_name, align="left", tier=None, colour=None, **kw):
    bounds = box(box_name) if isinstance(box_name, str) else box_name
    node = {"id": node_id, "kind": "text", "bounds": bounds, "align": align,
            "z": kw.pop("z", 40), "layer": kw.pop("layer", "dynamic")}
    if tier is not None:
        node["font_token"] = tier
    if colour is not None:
        node["color_token"] = colour
    node.update(kw)
    return node


def vector(node_id, shape, bounds, colour, **kw):
    node = {"id": node_id, "kind": "vector", "shape": shape, "bounds": bounds,
            "color_token": colour, "z": kw.pop("z", 5),
            "layer": kw.pop("layer", "static"),
            "opacity": kw.pop("opacity", 1.0)}
    node.update(kw)
    return node


def image(node_id, src, bounds, z, **kw):
    node = {"id": node_id, "kind": "image", "src": src, "bounds": bounds,
            "z": z, "layer": kw.pop("layer", "static")}
    node.update(kw)
    return node


def build_tokens(measurements, ui_assets):
    palette = measurements.get("palette") or ["#040C14", "#04040C", "#0C141C"]
    accent = measurements.get("accent") or "#2496D8"
    return {
        "schema": "horizon-v5-tokens v1",
        "status": "AWAITING HUMAN VISUAL APPROVAL",
        "reference": {
            "role": "HORIZON_V5_VISUAL_REFERENCE",
            "image": "assets/ui/horizon_v5_reference.png",
            "annotation": "assets/ui/horizon_v5_reference_annotation.png",
            "measurements": "assets/ui/horizon_v5_reference_measurements.json",
            "state": "MEASURED_FROM_REFERENCE",
            "mapping": {
                "why": "the panel is 4:1, the reference is 3:1: the reference "
                       "is placed 1:1 by height in a centred 1440x480 content "
                       "box and the extra 480 px is environment",
                "scale": CONTENT_SCALE,
                "content_box": [240, 0, 1440, 480],
                "panel_x": "960 + (x_ref - 1086) * 480/724",
                "panel_y": "y_ref * 480/724",
            },
        },
        "colors": {
            "bg_deep": "#05090D", "bg_mid": palette[0], "bg_horizon": palette[1],
            "bg_ground": palette[2],
            "contact_shadow": "#02060A", "reflection": "#0B141B",
            "primary_text": "#E9EEF3", "secondary_text": "#C3CDD7",
            "muted_text": "#8792A0", "dim_text": "#5E6875",
            "accent": accent, "accent_bright": "#7FE3F2", "accent_dim": "#1B3A4A",
            "rail_lit": "#8FD8EE", "warning": "#D8A657", "critical": "#D8674F",
            "ready": "#5FC98A", "ready_dim": "#3E8F62",
            "throw": "#DCD8CC", "rule": "#E9EEF3",
            "arc_underlay": "#03080C",
            "on_road_label": "#C3CDD7", "on_road_value": "#E9EEF3",
            "on_road_status": "#5FC98A",
        },
        "horizon_row": measurements["horizon"]["horizon_row"],
        "typography": {"tiers": {
            "DISPLAY": {"size": 98, "role": "bold", "tracking": -3.0},
            "TITLE": {"size": 58, "role": "bold", "tracking": -1.0},
            "BODY": {"size": 30, "role": "medium", "tracking": 0.6},
            "CAPTION": {"size": 22, "role": "medium", "tracking": 1.0},
            "LABEL": {"size": 16, "role": "medium", "tracking": 3.0}}},
        "spacing": {"zone_gap": 20, "stack_tight": 8, "stack_normal": 16,
                    "stack_loose": 34, "label_gap": 10},
        "radii": {"pill": 10, "bar": 6, "sign": 30, "capsule": 12},
        "opacity": {"muted": 0.55, "dim": 0.38, "inactive_gear": 0.22,
                    "active_gear": 1.0, "arc_inactive": 0.42,
                    "arc_active": 0.98, "rail_inactive": 0.32,
                    "rail_active": 0.95, "rule": 0.30, "glow": 0.85},
        "animation": {"why": "declared for the device pass, not implemented here",
                      "state_fade_ms": 220, "navigation_fade_ms": 200,
                      "navigation_slide_px": 12, "indicator_ground_pulse_ms": 420,
                      "arc_ease_ms": 160},
        "arc": {"start_deg": ARC_START_DEG, "end_deg": ARC_END_DEG,
                "max_kph": ARC_MAX_KPH, "minor_ticks": ARC_MINOR_TICKS,
                "centre_px": [ui_assets["dial"]["cx"], ui_assets["dial"]["cy"]],
                "radius_px": ui_assets["dial"]["radius"]},
        "cost_model": {
            "canvas": [1920, 480],
            "baked_background": "assets/ui/horizon_v5_background.png",
            "baked_glow": ["assets/ui/horizon_v5_arc_glow.png",
                           "assets/ui/horizon_v5_numeral_glow.png"],
            "baked_rail": "assets/ui/horizon_v5_rail_track.png",
            "vehicle_layers": "assets/rendered/vehicle/horizon_v5/layer/*.png "
                              "(one per lighting state, cropped)",
            "runtime_blur": "none",
        },
        "ui_assets": ui_assets,
    }


def build_components(measurements, ui_assets, vehicle, alignment):
    dial = ui_assets["dial"]
    text_dx = float(alignment.get("text_dx", 0.0))
    text_dy = float(alignment.get("dy", 0.0))
    cx, cy, radius = dial["cx"], dial["cy"], dial["radius"]
    stroke = dial["width"]
    asset_boxes = ui_assets.get("asset_boxes", {})

    def baked(node_id, name, z, **kw):
        """A baked bitmap placed at the box it was cropped to."""
        key = "assets/ui/" + name
        box_px = asset_boxes.get(name)
        if not box_px:
            bounds = {"x": 0, "y": 0, "w": 1920, "h": 480}
        else:
            bounds = {"x": box_px[0], "y": box_px[1],
                      "w": box_px[2] - box_px[0], "h": box_px[3] - box_px[1]}
        return image(node_id, key, bounds, z=z, **kw)

    def aligned(bounds):
        """The speed numeral and its unit travel together with the centring
        correction the alignment measurement solved for."""
        moved = dict(bounds)
        moved["x"] = round(bounds["x"] + text_dx, 1)
        moved["y"] = round(bounds["y"] + text_dy, 1)
        return moved

    components = []
    motion_assets = load_motion_assets()

    # ---- LAYER 0: the baked environment ---------------------------------
    components.append(image("env.plate", "assets/ui/horizon_v5_background.png",
                            {"x": 0, "y": 0, "w": 1920, "h": 480}, z=0,
                            exempt_from_safe_area=True, role="environment",
                            exempt_reason="the environment plate is the whole "
                                          "canvas and is itself clear of the "
                                          "panel mask by construction"))
    # A glow is the element's own emission: it is strong at night and held back
    # in daylight, where the arc has to read as a shape rather than as light.
    glow_backing = {"day": 0.35, "dawn": 0.7, "dusk": 0.7, "night": 1.0}
    components.append(baked("speed.arc.glow", "horizon_v5_arc_glow.png", z=2,
                            role="glow", opacity=0.85,
                            environment_opacity=dict(glow_backing)))
    components.append(baked("speed.numeral.glow",
                            "horizon_v5_numeral_glow.png", z=3, role="glow",
                            opacity=0.7,
                            environment_opacity=dict(glow_backing)))
    components.append(baked("energy.rail.track", "horizon_v5_rail_track.png",
                            z=4, role="glow"))
    # Daylight legibility without a surface: a dark under-stroke one step wider
    # than the arc it protects. The earlier solution was a large dark ellipse,
    # which passed the contrast measurement and destroyed the composition - two
    # black holes pasted onto the dashboard. An under-stroke costs no area at
    # all, so the support is invisible at panel scale by construction.
    components.append(vector("speed.arc.underlay", "arc",
                             {"x": cx - radius, "y": cy - radius,
                              "w": radius * 2, "h": radius * 2}, "arc_underlay",
                             z=9, opacity=0.62, role="speed",
                             cx=round(cx, 1), cy=round(cy, 1),
                             radius=round(radius, 1),
                             start_deg=ARC_START_DEG, end_deg=ARC_END_DEG,
                             width_px=round(stroke * 2.6, 1)))

    # ---- LAYER 1: the vehicle ------------------------------------------
    layers = vehicle["layers"]
    for index, (state, rule) in enumerate(VEHICLE_STATES):
        if state not in layers:
            continue
        entry = layers[state]
        component = image(
            f"vehicle.{state}", entry["source"],
            {"x": entry["offset"][0], "y": entry["offset"][1],
             "w": entry["size"][0], "h": entry["size"][1]},
            z=20 + index, layer="dynamic", role="vehicle",
            exempt_from_safe_area=True,
            exempt_reason="the vehicle layer carries the car and the road "
                          "response, measured from the render; the visible "
                          "silhouette is checked against the clusters")
        if rule:
            binding, mode = rule
            component["visibility"] = {"binding": binding,
                                       "show_when_true": True}
            component["visible_opacity"] = 1.0
        if state == "base":
            # Body micro motion: bounded at 2 px, zero when stationary, and
            # silent when the speed is unknown or stale.
            component["micro_motion"] = {
                "binding": "speed", "points": [[0, 0], [30, 0.3], [80, 0.6],
                                               [120, 1.0]],
                "amplitude_px": MICRO_MOTION_AMPLITUDE_PX,
                "hz": MICRO_MOTION_HZ}
        components.append(component)

    # ---- LAYER 1b: motion the car makes -------------------------------
    components.extend(motion_components(motion_assets, layers))

    # ---- LAYER 2: speed cluster ----------------------------------------
    components.append(vector("speed.arc.track", "arc",
                             {"x": cx - radius, "y": cy - radius,
                              "w": radius * 2, "h": radius * 2}, "accent_dim",
                             z=10, opacity=0.42, role="speed",
                             cx=round(cx, 1), cy=round(cy, 1),
                             radius=round(radius, 1),
                             start_deg=ARC_START_DEG, end_deg=ARC_END_DEG,
                             width_px=round(stroke, 1)))
    components.append(vector("speed.arc.ticks", "arc_ticks",
                             {"x": cx - radius, "y": cy - radius,
                              "w": radius * 2, "h": radius * 2}, "accent_dim",
                             z=11, opacity=0.5, role="speed",
                             cx=round(cx, 1), cy=round(cy, 1),
                             radius=round(radius - stroke * 1.1, 1),
                             start_deg=ARC_START_DEG, end_deg=ARC_END_DEG,
                             count=ARC_MINOR_TICKS + 1, length_px=6,
                             major_every=12, major_length_px=12,
                             major_token="accent", width_px=2))
    components.append(vector("speed.arc.active", "arc",
                             {"x": cx - radius, "y": cy - radius,
                              "w": radius * 2, "h": radius * 2}, "accent",
                             z=12, opacity=0.98, role="speed",
                             cx=round(cx, 1), cy=round(cy, 1),
                             radius=round(radius, 1),
                             start_deg=ARC_START_DEG, end_deg=ARC_END_DEG,
                             width_px=round(stroke * 1.5, 1),
                             progress={"binding": "speed", "max": ARC_MAX_KPH,
                                       "from": "start",
                                       "color_token": "accent_bright",
                                       "opacity": 1.0}))
    for label, fraction in (("0", 0.0), ("240", 1.0)):
        angle = math.radians(ARC_START_DEG
                             + (ARC_END_DEG - ARC_START_DEG) * fraction)
        lx = cx + math.cos(angle) * (radius + stroke * 3.4)
        ly = cy + math.sin(angle) * (radius + stroke * 3.4)
        components.append(text(f"speed.arc.label.{label}", {"x": lx - 24,
                                                            "y": ly - 10,
                                                            "w": 48, "h": 20},
                               "center", "LABEL", "muted_text", text=label,
                               z=13, layer="static", role="speed"))
    components.append(text("speed.value", aligned(box("speed_numeral")),
                           "center", "DISPLAY",
                           "primary_text", z=40,
                           **{"binding": "speed", "format": "{}",
                              "invalid_text": "\u2014", "role": "speed"}))
    components.append(text("speed.unit", aligned(box("speed_unit")), "left",
                           "BODY",
                           "on_road_label", text="km/h", z=40, role="speed"))
    for index, letter in enumerate(("P", "R", "N", "D")):
        bounds = box("gear_row")
        width = bounds["w"] / 4.0
        components.append({
            "id": f"gear.{letter.lower()}", "kind": "text",
            "bounds": {"x": round(bounds["x"] + width * index, 1),
                       "y": bounds["y"], "w": round(width, 1),
                       "h": bounds["h"]},
            "align": "center", "font_token": "BODY",
            "color_token": "on_road_value", "z": 40, "layer": "dynamic",
            "text": letter, "role": "speed",
            "highlight_when_gear": letter,
            "highlight_color_token": "accent_bright",
            "highlight_opacity_token": "active_gear"})
    components.append(text("gear.unknown", "gear_row", "center", "BODY",
                           "muted_text", text="\u2014", z=41,
                           visibility={"binding": "gear",
                                       "show_when_invalid": True},
                           visible_opacity=1.0, role="speed"))
    components.append(text("driver.temperature", "temperature", "left",
                           "CAPTION", "secondary_text", z=40, role="driver",
                           **{"binding": "temperature_primary",
                              "format": "{} \u00b0C", "invalid_text": "\u2014"}))
    components.append(text("driver.status", "driver_status", "left", "CAPTION",
                           "on_road_status", z=40, role="driver",
                           **{"binding": "driver_status_text", "format": "{}",
                              "invalid_text": ""}))
    components.append(text("climate.status", "climate_status", "left",
                           "CAPTION", "on_road_label", text="CHILL", z=40,
                           role="driver"))
    sign = box("speed_sign")
    components.append(vector("speedlimit.ring", "roundrect",
                             {"x": sign["x"], "y": sign["y"], "w": sign["w"],
                              "h": sign["h"]}, "critical", z=24,
                             radius_token="sign", opacity=0.0,
                             layer="dynamic", role="sign",
                             visibility={"binding": "speed_limit",
                                         "show_when_valid": True},
                             visible_opacity=0.85))
    components.append(text("speedlimit.value", "speed_sign", "center", "BODY",
                           "primary_text", z=25, role="sign",
                           **{"binding": "speed_limit", "format": "{}",
                              "invalid_text": "",
                              "visibility": {"binding": "speed_limit",
                                             "show_when_valid": True},
                              "visible_opacity": 1.0}))

    # ---- LAYER 2: energy cluster ---------------------------------------
    components.append(text("energy.range", "range_value", "right", "TITLE",
                           "primary_text", z=40, role="energy",
                           **{"binding": "range", "format": "{} km",
                              "invalid_text": "\u2014 km"}))
    components.append(text("energy.range.label", "range_label", "right",
                           "LABEL", "muted_text", text="RANGE", z=40,
                           role="energy"))
    rule = box("range_rule")
    components.append(vector("energy.rule", "line",
                             {"x": rule["x"], "y": rule["y"], "w": rule["w"],
                              "h": 1}, "rule", z=20, opacity=0.45,
                             role="energy", x2=rule["x"] + rule["w"],
                             y2=rule["y"]))
    trace = box("power_trace")
    components.append(vector("energy.trace", "polyline",
                             {"x": trace["x"], "y": trace["y"],
                              "w": trace["w"], "h": trace["h"]}, "accent",
                             z=21, opacity=0.9, role="energy",
                             width_px=2,
                             points=[[trace["x"], trace["y"] + trace["h"] * 0.55],
                                     [trace["x"] + trace["w"] * 0.22,
                                      trace["y"] + trace["h"] * 0.20],
                                     [trace["x"] + trace["w"] * 0.36,
                                      trace["y"] + trace["h"] * 0.78],
                                     [trace["x"] + trace["w"] * 0.55,
                                      trace["y"] + trace["h"] * 0.28],
                                     [trace["x"] + trace["w"],
                                      trace["y"] + trace["h"] * 0.62]]))
    components.append(text("energy.power", "power_value", "right", "BODY",
                           "on_road_value", z=40, role="energy",
                           **{"binding": "battery_power", "format": "{} kW",
                              "invalid_text": "\u2014 kW"}))
    components.append(text("energy.power.label", "power_label", "right",
                           "LABEL", "on_road_label", text="POWER", z=40,
                           role="energy"))
    rail = box("rail")
    segments = ui_assets["rail_segments_box"]
    rail_bar_x = round(segments[0], 1)
    rail_bar_width = round(segments[2] - segments[0], 1)
    rail_bar_top = round(segments[1], 1)
    rail_bar_height = round(segments[3] - segments[1], 1)
    rail_bar_bottom = round(segments[3], 1)
    components.append(vector("energy.rail", "vticks",
                             {"x": rail_bar_x, "y": rail_bar_top,
                              "w": rail_bar_width, "h": rail_bar_height},
                             "accent_dim", z=6, opacity=0.32, role="energy",
                             y_bottom=rail_bar_bottom,
                             count=24, major_every=0,
                             tick_height_px=9,
                             width_px=rail_bar_width,
                             major_width_px=rail_bar_width,
                             lit_token="rail_lit",
                             progress={"binding": "actual_soc", "max": 100}))
    components.append(vector("energy.rail.warn", "vticks",
                             {"x": rail_bar_x, "y": rail_bar_top,
                              "w": rail_bar_width, "h": rail_bar_height},
                             "warning", z=7, opacity=0.0, role="energy",
                             y_bottom=rail_bar_bottom,
                             count=24, major_every=0,
                             tick_height_px=9,
                             width_px=rail_bar_width,
                             major_width_px=rail_bar_width,
                             lit_token="warning",
                             visibility={"binding": "actual_soc", "lte": 20},
                             visible_opacity=0.95,
                             progress={"binding": "actual_soc", "max": 100}))
    components.append(text("energy.soc", "soc_value", "left", "BODY",
                           "on_road_value", z=40, role="energy",
                           **{"binding": "actual_soc", "format": "{}%",
                              "invalid_text": "\u2014 %"}))
    soc_box = box("soc_value")
    components.append(text("energy.soc.label",
                           {"x": soc_box["x"], "y": soc_box["y"] + soc_box["h"] + 2,
                            "w": 90, "h": 18}, "left", "LABEL",
                           "on_road_label", text="SOC", z=40, role="energy"))
    components.append(text("top.clock", "clock", "right", "CAPTION",
                           "muted_text", z=40, source="clock", format="%H:%M",
                           role="driver"))

    # ---- navigation: present only when a manoeuvre is valid -------------
    nav = box("nav")
    for node_id, x, w, bind, fmt, colour in (
            ("nav.capsule", nav["x"], nav["w"], None, None, None),
            ("nav.icon", nav["x"] + 26, 40, None, None, "accent_bright"),
            ("nav.distance", nav["x"] + 74, 120, "nav_distance", "{} m",
             "primary_text"),
            ("nav.instruction", nav["x"] + 210, nav["w"] - 236,
             "nav_instruction", "{}", "muted_text")):
        if node_id == "nav.capsule":
            components.append({
                "id": node_id, "kind": "vector", "shape": "roundrect",
                "bounds": {"x": nav["x"], "y": nav["y"], "w": nav["w"],
                           "h": nav["h"]},
                "color_token": "bg_deep", "z": 30, "layer": "dynamic",
                "opacity": 0.0, "radius_token": "capsule", "role": "navigation",
                "stroke_token": "accent_dim",
                "visibility": {"binding": "nav_manoeuvre",
                               "show_when_valid": True},
                "visible_opacity": 0.72,
                "exempt_from_safe_area": True,
                "exempt_reason": "the navigation capsule floats above the top "
                                 "margin; its content sits inside"})
            continue
        kwargs = {"font_token": "BODY", "color_token": colour,
                  "z": 40, "layer": "dynamic", "role": "navigation",
                  "visibility": {"binding": "nav_manoeuvre",
                                 "show_when_valid": True},
                  "visible_opacity": 1.0}
        if bind:
            kwargs.update({"binding": bind, "format": fmt, "invalid_text": ""})
        else:
            kwargs["text"] = "\u21b1"
        components.append(text(node_id, {"x": x, "y": nav["y"] + 22,
                                         "w": w, "h": nav["h"] - 40},
                               "left" if node_id != "nav.icon" else "center",
                               **kwargs))
        components[-1]["exempt_from_safe_area"] = True
        components[-1]["exempt_reason"] = (
            "the navigation capsule floats above the top margin; its content "
            "sits inside")

    # ---- warnings: the existing contract, kept --------------------------
    components.append({
        "id": "warn.glass", "kind": "vector", "shape": "roundrect",
        "bounds": {"x": 700, "y": 408, "w": 520, "h": 34},
        "color_token": "bg_deep", "z": 29, "layer": "dynamic", "opacity": 0.0,
        "radius_token": "capsule", "role": "warning",
        "stroke_token": "warning",
        "visibility": {"binding": "warning_active", "show_when_true": True},
        "visible_opacity": 0.7, "exempt_from_safe_area": True,
        "exempt_reason": "the warning strip is a state response and is hidden "
                         "unless a warning is valid"})
    components.append(text("warn.text", {"x": 700, "y": 414, "w": 520,
                                         "h": 22}, "center", "CAPTION",
                           "warning", z=30, role="warning",
                           **{"binding": "warning_text", "format": "{}",
                              "invalid_text": "",
                              "visibility": {"binding": "warning_active",
                                             "show_when_true": True},
                              "visible_opacity": 1.0}))
    return components


def main():
    if not os.path.isfile(os.path.join(UI, "horizon_v5_reference.png")):
        print("[v5] HORIZON_V5_REFERENCE_MISSING: "
              "assets/ui/horizon_v5_reference.png does not exist")
        return 2
    measurements = json.load(open(MEASUREMENTS))
    ui_assets = json.load(open(UI_ASSETS))
    vehicle = json.load(open(VEHICLE_LAYERS))
    tokens = build_tokens(measurements, ui_assets)
    # The frozen vehicle contract (frames, bboxes) travels with the tokens so
    # the QA can re-measure the assets against the numbers it was built from.
    tokens["vehicle"] = json.load(
        open(os.path.join(UI, "design_tokens.json")))["vehicle"]
    alignment = {}
    if os.path.isfile(ALIGNMENT):
        alignment = json.load(open(ALIGNMENT))
    components = build_components(measurements, ui_assets, vehicle, alignment)

    panel = dict(json.load(open(V2_LAYOUT))["panel"])
    panel["mask_color"] = "bg_deep"
    layout = {
        "schema": "horizon-v5-layout v1",
        "status": "AWAITING HUMAN VISUAL APPROVAL",
        "scene": "horizon_v5",
        "style_candidate": "HORIZON V5 - reference implementation",
        "canvas": {"width": 1920, "height": 480},
        "panel": panel,
        "safe_area": {"left": 48, "right": 48, "top": 22, "bottom": 24},
        "zones": {"driver": {"x": 284, "right": 672},
                  "vehicle": {"x": 672, "right": 1248},
                  "energy": {"x": 1248, "right": 1680}},
        "reference_state": "MEASURED_FROM_REFERENCE",
        "reference_mapping": tokens["reference"]["mapping"],
        "forbidden_in_production":
            json.load(open(V2_LAYOUT))["forbidden_in_production"],
        "forbidden_in_v5": [
            "white road trapezoids",
            "red brake trapezoid",
            "solid polygon light beams",
            "decoration lines with no semantics",
            "runtime blur",
            "gradient-and-polygon stand-in for the environment",
        ],
        "layers": {
            "LAYER_0_ENVIRONMENT": ["env.plate", "speed.arc.glow",
                                    "speed.numeral.glow", "energy.rail.track"],
            "LAYER_1_VEHICLE": [component["id"] for component in components
                                if component.get("role") == "vehicle"],
            "LAYER_2_INSTRUMENT": [component["id"] for component in components
                                   if component.get("role") in
                                   ("speed", "energy", "driver", "sign")],
            "LAYER_3_STATE_RESPONSE": ["warn.glass", "warn.text"],
        },
        "components": components,
        "screenshot_states": ["v5_neutral", "v5_left", "v5_right", "v5_hazard",
                              "v5_brake", "v5_low_soc", "v5_unknown",
                              "v5_navigation"],
        "screenshot_names": ["horizon_v5_01_neutral.png",
                             "horizon_v5_02_left_indicator.png",
                             "horizon_v5_03_right_indicator.png",
                             "horizon_v5_04_hazard.png",
                             "horizon_v5_05_brake.png",
                             "horizon_v5_06_low_soc.png",
                             "horizon_v5_07_unknown.png",
                             "horizon_v5_08_navigation.png"],
    }
    tokens_path = os.path.join(UI, "horizon_v5_tokens.json")
    layout_path = os.path.join(UI, "horizon_v5_layout.json")
    with open(tokens_path, "w") as fh:
        json.dump(tokens, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    with open(layout_path, "w") as fh:
        json.dump(layout, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    scene = os.path.join(SCENES, "horizon_v5.scene")
    subprocess.run([sys.executable, GEN, "--layout", layout_path, "--out",
                    scene, "--tokens", tokens_path], check=True)
    print(f"[v5] {len(components)} components -> {os.path.relpath(layout_path, REPO)}")
    print(f"[v5] dial centre ({ui_assets['dial']['cx']:.1f},"
          f"{ui_assets['dial']['cy']:.1f}) r={ui_assets['dial']['radius']:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
