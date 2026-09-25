#!/usr/bin/env python3
"""Generate every V6 instrument screen as a scene file.

Seven vehicle looks plus Settings and Developer. The committed artefacts are
the generated `scenes/v6_*.scene` files; this generator exists because the
screens share one design language and one set of rules, and nine hand-written
copies is how a rule gets broken in eight of them.

The design language is the one already committed for Horizon (near-black
spatial gradient, trapezoid safe area, amber accent, quiet typography). This
file does not invent a new one; it extends the existing language across the
rest of the set.

Rules enforced for every screen:

* **no fabricated data** - a signal that is invalid renders as `--`, never as
  0, OFF or CLOSED (`invalid_text` / `text_when` rules below);
* **SOC comes from Commander's `actual_soc` only** - the MCU's SOC byte is a
  rejected mapping on this car, so no screen may draw it as a percentage;
* **no mock in production** - mock exists only in the previewer's MOCK_STATES;
* **the device budget is respected** - each screen declares its cost and the
  generator refuses a screen that exceeds it (see BUDGET).

Usage:
    python3 tools/preview/build_v6_pages.py
    python3 tools/preview/build_v6_pages.py --report assets/checkpoints/v6_pages/pages_report.json
"""

import argparse
import json
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCENES = os.path.join(REPO_ROOT, "scenes")

CANVAS = {"width": 1920, "height": 480,
          "safe_area": {"top_corner_cut": 116, "bottom_corner_cut": 51},
          "mask_color": "#04060A"}
SAFE_L, SAFE_R = 176, 1744

# Palette: taken from the committed Horizon scenes so the whole set matches.
INK = "#04060A"
INK2 = "#0A0E13"
PRIMARY = "#E8EDF2"
SECONDARY = "#C9D4DF"
MUTED = "#8A96A2"
DIM = "#5A646E"
RAIL = "#171E25"
RAIL2 = "#1A222B"
AMBER = "#D8A657"
GOLD = "#CBB27A"

# Per-screen budget. Derived from docs/HORIZON_REDESIGN.md section 7: cost is
# dominated by large-area fills, 1 px ticks are nearly free, and the static
# layers are meant to be baked into a background bitmap so that per-frame
# work is single-digit paths. The numbers below are that policy as a gate.
BUDGET = {
    # Baked once into the background bitmap: cheap per frame, but each one is a
    # large fill that has to be composited, so the count stays small.
    "static_fills": 3,
    # Static text is baked with the background: the constraint is the bitmap,
    # not the label count.
    "static_text": 14,
    # Shown only when a rule fires (the warning layer). One is plenty: a second
    # simultaneous banner would mean two things are wrong at once.
    "conditional_fills": 1,
    # Text that is empty in the steady state (lamps, indicators, the warning
    # banner): real work only while something is lit or wrong.
    "conditional_text": 6,
    # The per-frame work. This is the number that decides 30 fps.
    "dynamic_paths": 12,
    "dynamic_text": 12,
    "bitmaps": 2,           # the vehicle layer plus the baked background
    "nodes": 40,
}

# The developer screen is not shown in production and exists to show raw
# counters, so it is allowed more live text than a driving screen.
PER_SCREEN_BUDGET = {"v6_developer": {"dynamic_text": 18}}


def txt(node_id, **kw):
    node = {"id": node_id, "type": "text", "z": kw.pop("z", 40),
            "layer": kw.pop("layer", "dynamic")}
    node.update(kw)
    return node


def vec(node_id, shape, **kw):
    node = {"id": node_id, "type": "vector", "shape": shape,
            "z": kw.pop("z", 5), "layer": kw.pop("layer", "static")}
    node.update(kw)
    return node


def image(node_id, path, x, y, w, h, z=20):
    return {"id": node_id, "type": "image", "asset": path, "x": x, "y": y,
            "width": w, "height": h, "z": z, "layer": "static"}


def sequence(node_id, seq, bind, x, y, w, h, z=20, layer="dynamic"):
    return {"id": node_id, "type": "image_anim", "sequence": seq, "bind": bind,
            "x": x, "y": y, "width": w, "height": h, "z": z, "layer": layer}


def vehicle(x, y, w, h, z=20):
    """The vehicle layer, with its moving panels and their own lighting."""
    return {"id": "vehicle", "type": "vehicle_visual", "x": x, "y": y,
            "width": w, "height": h, "z": z, "layer": "dynamic",
            "anchor": {"x": 0.5, "y": 0.5}, "asset": "vehicle.base",
            "parts": {
                "door_fl": {"sequence": "vehicle.door.fl", "bind": "door_fl"},
                "door_fr": {"sequence": "vehicle.door.fr", "bind": "door_fr"},
                "door_rl": {"sequence": "vehicle.door.rl", "bind": "door_rl"},
                "door_rr": {"sequence": "vehicle.door.rr", "bind": "door_rr"},
                "frunk": {"sequence": "vehicle.frunk", "bind": "frunk"},
                "trunk": {"sequence": "vehicle.trunk", "bind": "trunk"}},
            "overlays": [
                {"asset": "vehicle.brake", "bind": "brake"},
                {"asset": "vehicle.headlight", "bind": "headlight"}],
            "indicators": {
                "left": {"sequence": "vehicle.indicator.left",
                         "bind": "indicator_left"},
                "right": {"sequence": "vehicle.indicator.right",
                          "bind": "indicator_right"}}}


# --------------------------------------------------------------- shared kit

def background(top=INK, bottom=INK2):
    return [vec("bg", "vgradient", x=0, y=0, width=1920, height=480,
                **{"from": top, "to": bottom}, z=0, layer="static")]


def ambient(x, y, w, h, color=RAIL2, opacity=0.55):
    return vec("bg.pool", "radial", x=x, y=y, width=w, height=h,
               **{"from": color, "to": INK}, opacity=opacity, z=1,
               layer="static")


def top_rail(right_text=None):
    """Temperature and clock on one shared baseline, with a hairline rule."""
    nodes = [
        txt("top.temp", x=SAFE_L, y=42, size=22, align="left", color=MUTED,
            font_role="medium", font=22, tracking=1.5, bind="temperature_primary",
            format="{}°C", invalid_text="-- °C", layer="dynamic"),
        txt("top.clock", x=SAFE_R, y=42, size=22, align="right", color=MUTED,
            font_role="medium", font=22, tracking=1.5, source="clock",
            format="%H:%M", layer="dynamic"),
        vec("top.rule", "line", x=SAFE_L, y=64, x2=SAFE_R, y2=64, color=RAIL,
            width_px=1, z=6, layer="static"),
    ]
    if right_text:
        nodes.append(
            txt("top.note", x=SAFE_R, y=64 + 22, size=18, align="right",
                color=DIM, font_role="medium", font=18, tracking=1.2,
                text=right_text, layer="static"))
    return nodes


# Gear values follow the internal enum: 1 = P, 2 = R, 3 = N, 4 = D. There is
# deliberately no entry for 0: 0 is "unknown", and mapping it to P would put a
# confident letter on the panel for a gear nobody has decoded.
GEAR_MAP = {"1": "P", "2": "R", "3": "N", "4": "D"}


def gear_node(x, y, size=34, align="left", color=SECONDARY):
    """Gear text.

    The value_map is a PREVIEW convenience so a mock state renders as a letter.
    No numeric-to-letter mapping is confirmed on the real car: the 0x01 nibble
    is a rejected mapping and the 0x02 candidate is only LIKELY. On the device
    an unconfirmed gear stays invalid and this renders `--`.
    """
    return [txt("status.gear", x=x, y=y, size=size, align=align, color=color,
                font_role="bold", font=size, bind="gear", value_map=GEAR_MAP,
                invalid_text="--", invalid_alpha=0.55, tracking=2.0,
                layer="dynamic")]


def soc_nodes(x, y, align="left", size=30):
    """SOC, from Commander's actual_soc only.

    The MCU's SOC byte reads a stuck 97 % on this car and is a rejected
    mapping, so no screen draws it. `actual_soc` is fed by the Commander
    adapter; until that transport is live the value is invalid and the screen
    shows `--`.
    """
    return [
        txt("soc.value", x=x, y=y, size=size, align=align, color=SECONDARY,
            font_role="bold", font=size, bind="actual_soc", format="{}%",
            invalid_text="-- %", invalid_alpha=0.5, layer="dynamic"),
        txt("soc.label", x=x, y=y + size * 0.9, size=16, align=align,
            color=DIM, font_role="medium", font=16, tracking=2.0,
            text="SOC / COMMANDER", layer="static"),
    ]


def range_nodes(x, y, align="left", size=30):
    return [
        txt("range.value", x=x, y=y, size=size, align=align, color=SECONDARY,
            font_role="bold", font=size, bind="range", format="{} km",
            invalid_text="-- km", invalid_alpha=0.5, layer="dynamic"),
        txt("range.label", x=x, y=y + size * 0.9, size=16, align=align,
            color=DIM, font_role="medium", font=16, tracking=2.0,
            text="RANGE", layer="static"),
    ]


def commander_badge(x, y, align="right"):
    """Commander link state. Never claims data it does not have."""
    return [
        txt("commander.state", x=x, y=y, size=18, align=align,
            color=GOLD, font_role="medium", font=18, tracking=1.6,
            bind="commander_link", value_map={"1": "CMDR", "0": "CMDR —"},
            invalid_text="CMDR --", invalid_alpha=0.45, layer="dynamic"),
        txt("commander.detail", x=x, y=y + 20, size=14, align=align,
            color=DIM, font_role="medium", font=14, tracking=1.2,
            bind="commander_detail", format="{}", invalid_text="",
            layer="dynamic"),
    ]


def status_lamps(x, y, align="left"):
    """Indicator / hazard / headlight marks. Absent when not requested."""
    def lamp(name, bind, color):
        return txt(name, x=x, y=y, size=22, align=align, color=color,
                   font_role="bold", font=22, text="●",
                   text_when=[
                       {"when": {"signal": bind, "is_true": True},
                        "text": "●", "valid": True},
                       {"when": {"signal": bind, "valid": True},
                        "text": "", "valid": True}],
                   layer="dynamic")
    return [
        {"id": "lamp.left", "type": "text", "z": 40, "layer": "dynamic",
         "x": x, "y": y, "size": 22, "align": align, "color": AMBER,
         "font_role": "bold", "font": 22,
         "text_when": [
             {"when": {"signal": "indicator_left", "is_true": True},
              "text": "◀", "valid": True},
             {"when": {"signal": "indicator_left", "valid": True},
              "text": "", "valid": True}]},
        {"id": "lamp.right", "type": "text", "z": 40, "layer": "dynamic",
         "x": x + 34, "y": y, "size": 22, "align": align, "color": AMBER,
         "font_role": "bold", "font": 22,
         "text_when": [
             {"when": {"signal": "indicator_right", "is_true": True},
              "text": "▶", "valid": True},
             {"when": {"signal": "indicator_right", "valid": True},
              "text": "", "valid": True}]},
        txt("lamp.headlight", x=x + 68, y=y, size=22, align=align,
            color=SECONDARY, font_role="bold", font=22,
            text_when=[
                {"when": {"signal": "headlight", "is_true": True},
                 "text": "◐", "valid": True},
                {"when": {"signal": "headlight", "valid": True},
                 "text": "", "valid": True}], layer="dynamic"),
        txt("lamp.brake", x=x + 102, y=y, size=22, align=align, color="#C0392B",
            font_role="bold", font=22,
            text_when=[
                {"when": {"signal": "brake", "is_true": True},
                 "text": "▮", "valid": True},
                {"when": {"signal": "brake", "valid": True},
                 "text": "", "valid": True}], layer="dynamic"),
    ]


def closure_line(x, y, align="left"):
    """Door/frunk/trunk state. `?` means unknown, `-` means closed.

    UNKNOWN != CLOSED: a missing door signal renders `?`, never `-`.
    """
    return [txt("status.closures", x=x, y=y, size=20, align=align, color=MUTED,
                font_role="medium", font=20, tracking=1.4,
                bind="closures", format="{}", invalid_text="CLOSURES ?",
                invalid_alpha=0.5, layer="dynamic")]


def warning_layer():
    """The only loud element. Present only when something is actually wrong."""
    return [
        vec("warn.backdrop", "roundrect", x=560, y=18, width=800, height=64,
            radius=10, fill="#161A20", stroke="#3A2A1E", z=30,
            opacity=0.0, layer="static",
            rules=[{"when": {"signal": "warning_active", "is_true": True},
                    "opacity": 0.92}]),
        txt("warn.text", x=960, y=50, size=26, align="center", color=AMBER,
            font_role="bold", font=26, tracking=2.0, z=31,
            bind="warning_text", format="{}", invalid_text="",
            invalid_alpha=0.0, layer="dynamic"),
        txt("uart.lost", x=960, y=50, size=26, align="center", color="#D8674F",
            font_role="bold", font=26, tracking=2.0, z=32, text="UART LOST",
            text_when=[
                {"when": {"signal": "uart_health", "equals": "UART LOST"},
                 "text": "UART LOST", "valid": True},
                {"when": {"signal": "uart_health", "valid": True},
                 "text": "", "valid": True}],
            layer="dynamic"),
    ]


def speed_block(x, y, size=176, align="center", unit_size=26):
    return [
        txt("speed.value", x=x, y=y, size=size, align=align, color=PRIMARY,
            font_role="bold", font=size, bind="speed", format="{}",
            invalid_text="--", invalid_alpha=0.45, tracking=-2, layer="dynamic"),
        txt("speed.unit", x=x, y=y + size * 0.42, size=unit_size, align=align,
            color=MUTED, font_role="medium", font=unit_size, tracking=3.0,
            text="km/h", layer="static"),
    ]


# ------------------------------------------------------------------ screens

def screen_horizon():
    """主驾驶页 - the page you drive on: speed, range, gear, lamps, warnings."""
    nodes = background() + [
        ambient(200, 30, 1520, 520, opacity=0.55),
        vec("ground.pool", "radial", x=360, y=396, width=1200, height=150,
            **{"from": RAIL2, "to": INK}, opacity=0.62, z=4, layer="static"),
    ] + top_rail() + [
        vec("speed.frame", "line", x=SAFE_L, y=150, x2=SAFE_L, y2=330,
            color=RAIL, width_px=1, z=6, layer="static"),
    ] + speed_block(760, 236) + [
        vec("speed.tick0", "line", x=612, y=330, x2=672, y2=330, color=DIM,
            width_px=1, z=6, layer="static"),
    ] + gear_node(SAFE_L, 170, 34) + [
        txt("gear.label", x=SAFE_L, y=200, size=16, align="left", color=DIM,
            font_role="medium", font=16, tracking=2.0, text="GEAR", layer="static"),
    ] + closure_line(SAFE_L, 236) + status_lamps(SAFE_L, 268) \
        + range_nodes(SAFE_R, 170, align="right") \
        + soc_nodes(SAFE_R, 258, align="right", size=26) \
        + commander_badge(SAFE_R, 336) + warning_layer()
    return {"id": "v6_horizon", "name": "Horizon", "name_zh": "地平线（主驾驶）",
            "function": "驾驶主页面：速度为核心，右侧续航/SOC，左侧档位与门状态，"
                        "顶部时间与温度，警告与 UART 状态只在真实触发时出现",
            "data": ["speed", "range", "actual_soc (Commander)", "gear (未确认→--)",
                     "closures", "indicator_left/right", "headlight", "brake",
                     "temperature_primary", "clock", "warning_*", "commander_link"],
            "nodes": nodes}


def screen_mono():
    """极简单色页 - lowest cost: speed, unit, gear, one status dot row."""
    nodes = background(INK, "#080B10") + [
        txt("mono.rule", x=SAFE_L, y=120, size=1, align="left", color=INK,
            text="", layer="static"),
        vec("mono.baseline", "line", x=SAFE_L, y=360, x2=SAFE_R, y2=360,
            color=RAIL, width_px=1, z=6, layer="static"),
    ] + speed_block(960, 216, size=196) + gear_node(SAFE_L, 200, 40) \
        + closure_line(SAFE_L, 250) + status_lamps(SAFE_L, 286) \
        + [
            txt("mono.clock", x=SAFE_R, y=200, size=34, align="right",
                color=SECONDARY, font_role="bold", font=34, source="clock",
                format="%H:%M", layer="dynamic"),
            txt("mono.range", x=SAFE_R, y=250, size=24, align="right",
                color=MUTED, font_role="medium", font=24, bind="range",
                format="{} km", invalid_text="-- km", invalid_alpha=0.5,
                layer="dynamic"),
        ] + warning_layer()
    for node in nodes:
        if node.get("type") == "text":
            node["shadow"] = False
            if node.get("invalid_text"):
                node["invalid_alpha"] = 0.85
    return {"id": "v6_mono", "name": "Mono", "name_zh": "单色极简",
            "environment_tokens": {
                INK: "glass_fill", "#080B10": "glass_fill",
                PRIMARY: "primary_text", SECONDARY: "secondary_text",
                MUTED: "muted_text", DIM: "dim_text", RAIL: "glass_border"},
            "function": "最省资源的一页：无渐变池、无弧线，只有速度、档位、"
                        "门状态与时间；作为低性能档与夜间备选",
            "data": ["speed", "gear", "closures", "range", "clock"],
            "nodes": nodes}


def screen_pulse():
    """脉冲页 - speed arc, power flow and accelerator trace."""
    nodes = background(INK, "#070B12") + [
        ambient(760, 60, 900, 420, opacity=0.4),
        vec("pulse.arc", "arc", cx=960, cy=340, radius=286, width_px=6,
            start_deg=140, end_deg=400, color=RAIL,
            z=6, layer="static",
            progress={"signal": "speed", "max": 200, "color": SECONDARY,
                      "opacity": 0.95, "from": "start"}),
        vec("pulse.ticks", "ticks", cx=960, cy=340, radius=312,
            start_deg=140, end_deg=400, count=37, length_px=10,
            major_every=4, major_length_px=18, color="#232C36",
            major_color="#3A4653", z=5, layer="static"),
    ] + speed_block(960, 226, size=150) + [
        txt("pulse.accel.label", x=SAFE_L, y=170, size=16, align="left",
            color=DIM, font_role="medium", font=16, tracking=2.0,
            text="THROTTLE", layer="static"),
        vec("pulse.accel.bar", "vbar", x=SAFE_L, y=200, width=6, height=140,
            radius=3, track_color=RAIL2, z=6, layer="dynamic",
            progress={"signal": "accelerator_position", "max": 100,
                      "color": SECONDARY, "opacity": 0.9}),
        txt("pulse.power.label", x=SAFE_R, y=170, size=16, align="right",
            color=DIM, font_role="medium", font=16, tracking=2.0,
            text="BATTERY kW", layer="static"),
        vec("pulse.power.bar", "vbar", x=SAFE_R - 6, y=200, width=6, height=140,
            radius=3, track_color=RAIL2, z=6, layer="dynamic",
            progress={"signal": "battery_power_abs", "max": 250,
                      "color": AMBER, "opacity": 0.9}),
        txt("pulse.power.value", x=SAFE_R, y=360, size=26, align="right",
            color=SECONDARY, font_role="bold", font=26,
            bind="battery_power", format="{} kW", invalid_text="-- kW",
            invalid_alpha=0.5, layer="dynamic"),
    ] + gear_node(SAFE_L, 300, 32) + status_lamps(SAFE_L, 340) \
        + commander_badge(SAFE_R, 100) + warning_layer()
    return {"id": "v6_pulse", "name": "Pulse", "name_zh": "脉冲",
            "function": "运动感页面：速度弧扫描 + 油门/电池功率柱，"
                        "数据来自 Commander 的真实遥测，缺数据时留空",
            "data": ["speed", "accelerator_position (Commander)",
                     "battery_power (Commander)", "gear", "indicators"],
            "nodes": nodes}


def screen_route():
    """导航/行程页 - manoeuvre when the capability model has data, trip otherwise."""
    nodes = background(INK, "#070A10") + [
        vec("route.rail", "line", x=SAFE_L, y=140, x2=SAFE_R, y2=140,
            color=RAIL, width_px=1, z=6, layer="static"),
        txt("route.manoeuvre", x=SAFE_L, y=100, size=52, align="left",
            color=PRIMARY, font_role="bold", font=52, bind="nav_manoeuvre",
            format="{}", invalid_text="NO ROUTE", invalid_alpha=0.45,
            layer="dynamic"),
        txt("route.distance", x=SAFE_L, y=176, size=34, align="left",
            color=SECONDARY, font_role="bold", font=34, bind="nav_distance",
            format="{} m", invalid_text="-- m", invalid_alpha=0.4,
            layer="dynamic"),
        txt("route.eta", x=SAFE_R, y=176, size=28, align="right", color=MUTED,
            font_role="medium", font=28, bind="nav_eta", format="ETA {}",
            invalid_text="ETA --", invalid_alpha=0.4, layer="dynamic"),
        txt("route.capability", x=SAFE_R, y=100, size=16, align="right",
            color=DIM, font_role="medium", font=16, tracking=1.6,
            bind="nav_capability", format="NAV {}", invalid_text="NAV UNKNOWN",
            layer="dynamic"),
        vec("trip.rule", "line", x=SAFE_L, y=280, x2=SAFE_R, y2=280,
            color=RAIL, width_px=1, z=6, layer="static"),
        txt("trip.label", x=SAFE_L, y=308, size=16, align="left", color=DIM,
            font_role="medium", font=16, tracking=2.0, text="TRIP",
            layer="static"),
        txt("trip.distance", x=SAFE_L, y=336, size=30, align="left",
            color=SECONDARY, font_role="bold", font=30, bind="trip_distance",
            format="{:.1f} km", invalid_text="-- km", invalid_alpha=0.5,
            layer="dynamic"),
        txt("trip.time", x=700, y=336, size=30, align="left", color=SECONDARY,
            font_role="bold", font=30, bind="trip_time_text", format="{}",
            invalid_text="--:--", invalid_alpha=0.5, layer="dynamic"),
        txt("trip.average", x=SAFE_R, y=336, size=30, align="right",
            color=SECONDARY, font_role="bold", font=30, bind="average_speed",
            format="avg {:.0f} km/h", invalid_text="avg --", invalid_alpha=0.5,
            layer="dynamic"),
        txt("route.note", x=960, y=250, size=18, align="center", color=DIM,
            font_role="medium", font=18, text_when=[
                {"when": {"signal": "nav_manoeuvre", "valid": False},
                 "text": "NO ROUTE DATA — PHONE NAVIGATION IS THE FALLBACK",
                 "valid": True}], layer="dynamic"),
    ] + warning_layer()
    return {"id": "v6_route", "name": "Route", "name_zh": "行程 / 导航",
            "function": "导航与行程页：有导航能力模型数据时显示机动与距离，"
                        "没有数据时明确显示 NO ROUTE，并提示手机导航兜底；"
                        "行程指标始终可用（真实信号）",
            "data": ["nav_manoeuvre / nav_distance / nav_eta / nav_capability",
                     "trip_distance", "trip_time", "average_speed"],
            "nodes": nodes}


def screen_studio():
    """车辆陈列页 - the vehicle with its real door/lamp state."""
    nodes = background(INK, "#06090E") + [
        ambient(480, 20, 960, 460, opacity=0.5),
        vehicle(610, 40, 700, 401),
        txt("studio.title", x=SAFE_L, y=96, size=30, align="left", color=PRIMARY,
            font_role="bold", font=30, tracking=2.0, text="VEHICLE",
            layer="static"),
        txt("studio.closures", x=SAFE_L, y=150, size=22, align="left",
            color=SECONDARY, font_role="medium", font=22, tracking=1.4,
            bind="closures_detail", format="{}", invalid_text="CLOSURES ?",
            invalid_alpha=0.5, layer="dynamic"),
        txt("studio.lights", x=SAFE_L, y=200, size=22, align="left", color=MUTED,
            font_role="medium", font=22, tracking=1.4, bind="lights_detail",
            format="{}", invalid_text="LIGHTS ?", invalid_alpha=0.5,
            layer="dynamic"),
        txt("studio.tires", x=SAFE_L, y=250, size=22, align="left", color=MUTED,
            font_role="medium", font=22, tracking=1.4, bind="tires_detail",
            format="{}", invalid_text="TIRES ?", invalid_alpha=0.5,
            layer="dynamic"),
        txt("studio.tires.note", x=SAFE_L, y=282, size=15, align="left",
            color=DIM, font_role="medium", font=15,
            text="SCALE VERIFIED · WHEEL ORDER UNKNOWN", layer="static"),
        txt("studio.gear", x=SAFE_R, y=150, size=34, align="right",
            color=SECONDARY, font_role="bold", font=34, bind="gear",
            value_map=GEAR_MAP, invalid_text="--", invalid_alpha=0.5,
            layer="dynamic"),
        txt("studio.gear.note", x=SAFE_R, y=184, size=15, align="right",
            color=DIM, font_role="medium", font=15,
            text="GEAR MAPPING UNCONFIRMED", layer="static"),
    ] + commander_badge(SAFE_R, 336) + warning_layer()
    return {"id": "v6_studio", "name": "Studio", "name_zh": "车辆陈列",
            "function": "停车/检查页：车辆渲染 + 门/盖/灯的真实状态 + 胎压与档位；"
                        "全部走 VehicleVisualController 的图层输出",
            "data": ["vehicle layers (doors, frunk, trunk, brake, indicators)",
                     "closures_detail", "lights_detail", "tires_detail", "gear"],
            "nodes": nodes}


def screen_energy():
    """能量页 - Commander's battery telemetry; SOC only from actual_soc."""
    nodes = background(INK, "#070B10") + [
        vec("energy.rail", "line", x=SAFE_L, y=140, x2=SAFE_R, y2=140,
            color=RAIL, width_px=1, z=6, layer="static"),
        txt("energy.title", x=SAFE_L, y=100, size=30, align="left", color=PRIMARY,
            font_role="bold", font=30, tracking=2.0, text="ENERGY", layer="static"),
    ] + soc_nodes(SAFE_L, 200, align="left", size=60) + [
        txt("energy.soc.note", x=SAFE_L, y=290, size=15, align="left", color=DIM,
            font_role="medium", font=15,
            text="MCU SOC BYTE REJECTED — COMMANDER ONLY", layer="static"),
        vec("energy.bar", "vbar", x=700, y=170, width=10, height=180, radius=5,
            track_color=RAIL2, z=6, layer="dynamic",
            progress={"signal": "actual_soc", "max": 100, "color": SECONDARY,
                      "opacity": 0.95}),
        txt("energy.power.label", x=900, y=170, size=16, align="left", color=DIM,
            font_role="medium", font=16, tracking=2.0, text="BATTERY",
            layer="static"),
        txt("energy.power", x=900, y=200, size=38, align="left", color=SECONDARY,
            font_role="bold", font=38, bind="battery_power", format="{} kW",
            invalid_text="-- kW", invalid_alpha=0.5, layer="dynamic"),
        txt("energy.voltage", x=900, y=256, size=24, align="left", color=MUTED,
            font_role="medium", font=24, bind="battery_voltage", format="{:.1f} V",
            invalid_text="-- V", invalid_alpha=0.5, layer="dynamic"),
        txt("energy.current", x=900, y=292, size=24, align="left", color=MUTED,
            font_role="medium", font=24, bind="battery_current", format="{:.1f} A",
            invalid_text="-- A", invalid_alpha=0.5, layer="dynamic"),
        txt("energy.remaining", x=SAFE_R, y=200, size=38, align="right",
            color=SECONDARY, font_role="bold", font=38, bind="range",
            format="{} km", invalid_text="-- km", invalid_alpha=0.5,
            layer="dynamic"),
        txt("energy.remaining.label", x=SAFE_R, y=246, size=16, align="right",
            color=DIM, font_role="medium", font=16, tracking=2.0,
            text="REMAINING", layer="static"),
        txt("energy.charged", x=SAFE_R, y=292, size=24, align="right",
            color=MUTED, font_role="medium", font=24, bind="total_charged_energy",
            format="+{:.1f} kWh", invalid_text="-- kWh", invalid_alpha=0.5,
            layer="dynamic"),
        txt("energy.discharged", x=SAFE_R, y=328, size=24, align="right",
            color=MUTED, font_role="medium", font=24,
            bind="total_discharged_energy", format="-{:.1f} kWh",
            invalid_text="-- kWh", invalid_alpha=0.5, layer="dynamic"),
    ] + commander_badge(SAFE_R, 100) + warning_layer()
    return {"id": "v6_energy", "name": "Energy", "name_zh": "能量",
            "function": "能量页：SOC 只取指挥官 actual_soc（MCU 的 SOC 字节是"
                        "已否决映射，永不显示）；功率/电压/电流/充放电量同源；"
                        "指挥官不在线时全部显示 --",
            "data": ["actual_soc (Commander)", "battery_power/voltage/current",
                     "total_charged/discharged_energy", "range"],
            "nodes": nodes}


def screen_nocturne():
    """夜间页 - darkest, quietest, still legal."""
    nodes = background("#020305", "#05070B") + [
        vec("noct.rule", "line", x=SAFE_L, y=380, x2=SAFE_R, y2=380,
            color="#12161C", width_px=1, z=6, layer="static"),
    ] + [
        txt("noct.speed", x=SAFE_L + 20, y=210, size=150, align="left",
            color="#9BA6B2", font_role="bold", font=150, bind="speed",
            format="{}", invalid_text="--", invalid_alpha=0.35, tracking=-2,
            layer="dynamic"),
        txt("noct.unit", x=SAFE_L + 20, y=290, size=22, align="left",
            color="#4E5862", font_role="medium", font=22, tracking=3.0,
            text="km/h", layer="static"),
        txt("noct.clock", x=SAFE_R, y=210, size=44, align="right",
            color="#7C8794", font_role="medium", font=44, source="clock",
            format="%H:%M", layer="dynamic"),
        txt("noct.range", x=SAFE_R, y=270, size=24, align="right",
            color="#4E5862", font_role="medium", font=24, bind="range",
            format="{} km", invalid_text="-- km", invalid_alpha=0.4,
            layer="dynamic"),
        txt("noct.warn", x=960, y=420, size=24, align="center", color="#B4643C",
            font_role="bold", font=24, bind="warning_text", format="{}",
            invalid_text="", invalid_alpha=0.0, layer="dynamic"),
        txt("noct.uart", x=SAFE_L + 20, y=420, size=18, align="left",
            color="#6B4A3A", font_role="medium", font=18,
            text_when=[
                {"when": {"signal": "uart_health", "equals": "UART LOST"},
                 "text": "UART LOST", "valid": True}], layer="dynamic"),
    ]
    return {"id": "v6_nocturne", "name": "Nocturne", "name_zh": "夜行",
            "function": "夜间低扰页面：极暗配色与最少元素，只保留速度、时间、"
                        "续航与真实警告，减少夜间眩光",
            "data": ["speed", "range", "clock", "warning_text", "uart_health"],
            "nodes": nodes}


def screen_settings():
    """设置页 - every switchable behaviour in one place."""
    rows = [
        ("外观", "SETTING 外观 APPEARANCE", "APPEARANCE", "settings.appearance",
         "appearance_text"),
        ("亮度", "SETTING 亮度 BRIGHTNESS", "BRIGHTNESS", "settings.brightness",
         "brightness_text"),
        ("速度单位", "SETTING 速度单位 SPEED UNIT", "SPEED UNIT",
         "settings.speed_unit", "speed_unit_text"),
        ("温度单位", "SETTING 温度单位 TEMPERATURE", "TEMPERATURE",
         "settings.temperature_unit", "temperature_unit_text"),
        ("胎压单位", "SETTING 胎压单位 TIRE PRESSURE", "TIRE PRESSURE",
         "settings.tire_pressure_unit", "tire_pressure_unit_text"),
        ("时钟", "SETTING 时钟 CLOCK", "CLOCK", "settings.clock", "clock_text"),
        ("默认页面", "SETTING 默认页面 DEFAULT PAGE", "DEFAULT PAGE",
         "settings.default_page", "default_page_text"),
        ("警告声音", "SETTING 警告声音 WARNING SOUND", "WARNING SOUND",
         "settings.warning_sound", "warning_sound_text"),
        ("开发者模式", "SETTING 开发者模式 DEVELOPER MODE", "DEVELOPER MODE",
         "settings.developer_mode", "developer_mode_text"),
    ]
    nodes = background(INK, "#070A0F") + [
        txt("settings.title", x=SAFE_L, y=64, size=30, align="left",
            color=PRIMARY, font_role="bold", font=30, tracking=2.0,
            text="SETTINGS", layer="static"),
    ]
    # Two columns so nine rows still read at 480 px tall.
    for index, (_label, _id, name, _key, bind) in enumerate(rows):
        col = index // 5
        row = index % 5
        x_label = SAFE_L + col * 800
        x_value = x_label + 620
        y = 140 + row * 62
        nodes.append(txt(f"{name}.label", x=x_label, y=y, size=20,
                         align="left", color=MUTED, font_role="medium",
                         font=20, tracking=1.4, text=name, layer="static"))
        nodes.append(txt(f"{name}.value", x=x_value, y=y, size=20,
                         align="right", color=SECONDARY, font_role="bold",
                         font=20, bind=bind, format="{}",
                         invalid_text="--", invalid_alpha=0.5,
                         layer="dynamic"))
        nodes.append(vec(f"{name}.rule", "line", x=x_label, y=y + 20,
                         x2=x_value, y2=y + 20, color=RAIL, width_px=1, z=6,
                         layer="static"))
    nodes.append(txt("settings.note", x=960, y=440, size=15, align="center",
                     color=DIM, font_role="medium", font=15,
                     text="WIFI / BLUETOOTH / CAMERA / MCU UPDATE ARE "
                          "DEVICE-BACKED — NOT SHOWN IN SIMULATION",
                     layer="static"))
    return {"id": "v6_settings", "name": "Settings", "name_zh": "设置",
            "function": "全部可配置项：外观、亮度、单位、时钟制式、默认页、"
                        "警告音、开发者模式；需要设备能力（Wi-Fi/蓝牙/摄像头/"
                        "MCU 更新）的项在模拟中标为不可用",
            "data": ["settings.* signals from DashboardSettings"],
            "nodes": nodes}


def screen_developer():
    """诊断页 - sources, protocol health, performance, mock switching."""
    nodes = background("#05070A", "#0A0D12") + [
        txt("dev.title", x=SAFE_L, y=64, size=30, align="left", color=PRIMARY,
            font_role="bold", font=30, tracking=2.0, text="DEVELOPER",
            layer="static"),
        txt("dev.banner", x=SAFE_R, y=64, size=20, align="right", color=AMBER,
            font_role="bold", font=20, tracking=2.0, text="DEV / REPLAY ONLY",
            text_when=[{"when": {"signal": "developer_mode", "is_true": True},
                        "text": "DEV / REPLAY ONLY", "valid": True},
                       {"when": {"signal": "developer_mode", "valid": True},
                        "text": "", "valid": True}], layer="dynamic"),
        txt("dev.uart", x=SAFE_L, y=130, size=22, align="left", color=SECONDARY,
            font_role="medium", font=22, bind="dev_uart", format="{}",
            invalid_text="UART --", invalid_alpha=0.5, layer="dynamic"),
        txt("dev.parser", x=SAFE_L, y=166, size=22, align="left", color=MUTED,
            font_role="medium", font=22, bind="dev_parser", format="{}",
            invalid_text="PARSER --", invalid_alpha=0.5, layer="dynamic"),
        txt("dev.commander", x=SAFE_L, y=202, size=22, align="left", color=MUTED,
            font_role="medium", font=22, bind="dev_commander", format="{}",
            invalid_text="COMMANDER --", invalid_alpha=0.5, layer="dynamic"),
        txt("dev.soc", x=SAFE_L, y=238, size=22, align="left", color=MUTED,
            font_role="medium", font=22, bind="dev_soc", format="{}",
            invalid_text="SOC --", invalid_alpha=0.5, layer="dynamic"),
        txt("dev.gear", x=SAFE_L, y=274, size=22, align="left", color=MUTED,
            font_role="medium", font=22, bind="dev_gear", format="{}",
            invalid_text="GEAR --", invalid_alpha=0.5, layer="dynamic"),
        txt("dev.frame", x=SAFE_R, y=130, size=22, align="right", color=SECONDARY,
            font_role="medium", font=22, bind="dev_frame", format="{}",
            invalid_text="FRAME --", invalid_alpha=0.5, layer="dynamic"),
        txt("dev.memory", x=SAFE_R, y=166, size=22, align="right", color=MUTED,
            font_role="medium", font=22, bind="dev_memory", format="{}",
            invalid_text="RSS --", invalid_alpha=0.5, layer="dynamic"),
        txt("dev.hint", x=SAFE_R, y=210, size=16, align="right", color=DIM,
            font_role="medium", font=16, bind="dev_hint", format="{}",
            invalid_text="", layer="dynamic"),
    ] + commander_badge(SAFE_R, 260) + warning_layer()
    return {"id": "v6_developer", "name": "Developer", "name_zh": "诊断",
            "function": "开发/诊断页：UART 与解析健康、指挥官链路与仲裁结果、"
                        "档位与 SOC 的映射状态、帧率与内存、mock/replay 提示；"
                        "生产构建隐藏该页",
            "data": ["uart health", "parser counters", "commander link",
                     "mapping confidence", "frame budget", "rss"],
            "nodes": nodes}


SCREENS = [screen_horizon, screen_mono, screen_pulse, screen_route,
           screen_studio, screen_energy, screen_nocturne, screen_settings,
           screen_developer]


def audit(screen):
    """Count what the device budget cares about and refuse a violation."""
    counts = {"static_fills": 0, "conditional_fills": 0, "dynamic_paths": 0,
              "static_text": 0, "conditional_text": 0, "dynamic_text": 0,
              "bitmaps": 0, "nodes": len(screen["nodes"])}
    for node in screen["nodes"]:
        ntype = node.get("type")
        # A node whose visibility is rule-gated is not part of the static bake
        # and not part of the steady-state frame either: it is the warning
        # layer, and it costs nothing until something is actually wrong.
        conditional = bool(node.get("rules") or node.get("text_when"))
        dynamic = node.get("layer") == "dynamic" or conditional
        if ntype == "text":
            # Literal labels can be baked with the background; anything bound to
            # a signal or the clock is a control update every frame.
            if conditional:
                counts["conditional_text"] += 1
            elif node.get("bind") or node.get("source") == "clock":
                counts["dynamic_text"] += 1
            else:
                counts["static_text"] += 1
        elif ntype in ("image", "image_anim", "vehicle_visual"):
            counts["bitmaps"] += 1
            if dynamic:
                counts["dynamic_paths"] += 1
        elif ntype == "vector":
            shape = node.get("shape")
            area = node.get("width", 0) * node.get("height", 0)
            large_fill = shape in ("vgradient", "hgradient", "radial") or \
                (shape == "roundrect" and area > 40000)
            if large_fill:
                if conditional:
                    counts["conditional_fills"] += 1
                else:
                    counts["static_fills"] += 1
            if dynamic or "progress" in node:
                counts["dynamic_paths"] += 1
    budget = dict(BUDGET)
    budget.update(PER_SCREEN_BUDGET.get(screen["id"], {}))
    violations = {key: counts[key] for key in budget
                  if counts.get(key, 0) > budget[key]}
    return counts, violations


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report",
                    default=os.path.join(REPO_ROOT, "assets", "checkpoints",
                                         "v6_pages", "pages_report.json"))
    args = ap.parse_args()

    os.makedirs(SCENES, exist_ok=True)
    registry, failures = [], []
    for builder in SCREENS:
        screen = builder()
        counts, violations = audit(screen)
        scene = {
            "scene": screen["id"],
            "version": 1,
            "status": "v6 page set - generated by tools/preview/build_v6_pages.py",
            "title": screen["name"],
            "role": screen["function"],
            "canvas": CANVAS,
            "manifest": "assets/manifest.json",
            "notes": [
                "Signals come from VehicleState only; invalid renders as --.",
                "SOC is drawn from Commander's actual_soc: the MCU SOC byte is "
                "a rejected mapping on this car.",
                "Mock data exists only in tools/preview/scene_preview.py "
                "MOCK_STATES and is labelled developer mode.",
            ],
            "budget": counts,
            "nodes": screen["nodes"],
        }
        path = os.path.join(SCENES, f"{screen['id']}.scene")
        if "environment_tokens" in screen:
            scene["environment_tokens"] = screen["environment_tokens"]
        with open(path, "w") as fh:
            json.dump(scene, fh, indent=2)
            fh.write("\n")
        entry = {"id": screen["id"], "name": screen["name"],
                 "name_zh": screen["name_zh"], "function": screen["function"],
                 "data": screen["data"], "scene": os.path.relpath(path, REPO_ROOT),
                 "budget": counts, "budget_violations": violations}
        registry.append(entry)
        if violations:
            failures.append((screen["id"], violations))
        print(f"[pages] {screen['id']:16s} nodes={counts['nodes']:3d} "
              f"baked: fills={counts['static_fills']} "
              f"text={counts['static_text']:2d} | per frame: "
              f"paths={counts['dynamic_paths']:2d} "
              f"text={counts['dynamic_text']:2d} "
              f"bitmaps={counts['bitmaps']} | conditional: "
              f"text={counts['conditional_text']} "
              f"fills={counts['conditional_fills']}"
              + (f"  VIOLATION {violations}" if violations else ""))

    report = {"schema": "v6-pages v1", "canvas": CANVAS, "budget": BUDGET,
              "pages": registry, "violations": [f[0] for f in failures]}
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"[pages] {len(registry)} screens -> {args.report}")
    if failures:
        print(f"[pages] BUDGET VIOLATIONS: {[f[0] for f in failures]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
