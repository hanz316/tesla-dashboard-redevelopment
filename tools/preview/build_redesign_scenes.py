#!/usr/bin/env python3
"""Generate the three Horizon redesign scene files (A / B / C).

The committed artefacts are the generated `scenes/horizon_redesign_*.scene`
files - that is what the previewer and (later) the device runtime read. This
generator exists because the three designs repeat the same vehicle geometry
and the same trusted-source rules, and hand-maintaining three copies of the
same numbers is how layouts drift apart.

Design brief (human review round, commit a5073d6):
  A - OEM MINIMAL         typography, spacing, vehicle. Calmest.
  B - SPATIAL HMI         vehicle and UI share one spatial field.
  C - PERFORMANCE LUXURY  instrument structure, precision rails.

All three: 1920x480, near-black spatial gradient, trapezoid safe area, real
VehicleState only, no DRIVE / ALL CLOSED / UART OK in the normal state.

Usage:
    python3 tools/preview/build_redesign_scenes.py
"""

import json
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

CANVAS = {
    "width": 1920,
    "height": 480,
    "safe_area": {"top_corner_cut": 116, "bottom_corner_cut": 51},
    # The panel's trapezoid mask is near-black, not pure black, so the masked
    # corners do not read as a different material from the background.
    "mask_color": "#04060A",
}

# Left/right content edges that stay inside the trapezoid at every row.
SAFE_L = 176
SAFE_R = 1744


def txt(node_id, **kw):
    node = {"id": node_id, "type": "text", "z": kw.pop("z", 40)}
    node.update(kw)
    return node


def vec(node_id, shape, **kw):
    node = {"id": node_id, "type": "vector", "shape": shape,
            "z": kw.pop("z", 5)}
    node.update(kw)
    return node


def vehicle(x, y, w, h, z=20):
    return {"id": "vehicle", "type": "vehicle_visual", "x": x, "y": y,
            "width": w, "height": h, "z": z, "anchor": {"x": 0.5, "y": 0.5},
            "asset": "vehicle.base",
            "parts": {
                "door_fl": {"sequence": "vehicle.door.fl", "bind": "door_fl"},
                "door_fr": {"sequence": "vehicle.door.fr", "bind": "door_fr"},
                "door_rl": {"sequence": "vehicle.door.rl", "bind": "door_rl"},
                "door_rr": {"sequence": "vehicle.door.rr", "bind": "door_rr"},
            }}


# --------------------------------------------------------------- shared bits

def ground_pool(x, y, w, h, color="#1A222B", opacity=0.60, z=4):
    """Soft ambient pool under the car. Deliberately very diffuse so it reads
    as light on a surface, not as an ellipse."""
    return vec("ground.pool", "radial", x=x, y=y, width=w, height=h,
               **{"from": color, "to": "#04060A"}, opacity=opacity, z=z)


def soc_percent_rules():
    """The one rule that must never be broken across all three designs:
    a known-untrusted SOC is never rendered as a percentage.

    Three distinct cases, and they must not collapse into one:
      * trusted            -> draw the percentage
      * present, untrusted -> hide it entirely (no 97%, no fake value)
      * absent (UART lost) -> fall through to the normal invalid path, which
                              renders a dimmed placeholder
    """
    return [{"when": {"all": [{"signal": "soc.trusted", "is_true": False},
                              {"signal": "soc.valid", "valid": True}]},
             "alpha": 0.0}]


def untrusted_only():
    """Visible only when SOC exists but is known-untrusted."""
    return [{"when": {"all": [{"signal": "soc.trusted", "is_true": False},
                              {"signal": "soc.valid", "valid": True}]},
             "alpha": 1.0}]


def uart_lost_only():
    return [{"when": {"signal": "uart_health", "equals": "UART LOST"},
             "alpha": 1.0},
            {"when": {"signal": "uart_health", "valid": True}, "alpha": 0.0}]


def uart_ok_only():
    return [{"when": {"signal": "uart_health", "equals": "UART LOST"},
             "alpha": 0.0}]


def door_open_only():
    return [{"when": {"signal": "door_fl", "is_true": True}, "alpha": 1.0},
            {"when": {"signal": "door_fl", "valid": True}, "alpha": 0.0}]


def clock_node(x, y, size=22, align="right", color="#A8B3BE", z=40):
    return txt("top.clock", x=x, y=y, size=size, align=align, color=color,
               font_role="medium", font=size, source="clock", format="%H:%M",
               tracking=1.5, z=z)


# ----------------------------------------------------------------- design A

def scene_a():
    nodes = [
        vec("bg", "vgradient", x=0, y=0, width=1920, height=480,
            **{"from": "#04060A", "to": "#0A0E13"}, z=0),
        vec("bg.pool", "radial", x=200, y=30, width=1520, height=520,
            **{"from": "#121A22", "to": "#04060A"}, opacity=0.55, z=1),
        ground_pool(360, 396, 1200, 150, opacity=0.62),

        # TOP RAIL - temperature and time only, on one shared baseline.
        txt("top.temp", x=SAFE_L, y=42, size=22, align="left",
            color="#8A96A2", font_role="medium", font=22, tracking=1.5,
            bind="temperature_primary", format="{}°C"),
        clock_node(SAFE_R, 42, color="#A8B3BE"),
        vec("top.rule", "line", x=SAFE_L, y=64, x2=SAFE_R, y2=64,
            color="#171E25", width_px=1, z=6),

        # CENTRE - vehicle with a soft pool, no labels above it. The car is
        # kept clear of both text columns: contextual text is drawn above the
        # vehicle layer, so anything placed over the car would collide with it.
        vehicle(610, 40, 700, 401),

        # LEFT - one speed composition: value, unit, gear, one rule.
        txt("speed.value", x=452, y=282, size=176, align="right",
            color="#E8EDF2", font_role="display", font=176,
            bind="speed", format="{}", invalid_color="#5A646E",
            invalid_text="--"),
        txt("speed.unit", x=452, y=344, size=24, align="right",
            color="#7C8894", font_role="medium", font=24, tracking=3.0,
            text="KM/H", alpha=0.85),
        vec("speed.divider", "line", x=498, y=248, x2=498, y2=346,
            color="#232B34", width_px=2, z=42),
        txt("speed.gear", x=534, y=296, size=46, align="left",
            color="#C9D4DF", font_role="medium", font=46, bind="gear",
            value_map={"1": "P", "2": "R", "3": "N", "4": "D"},
            format="{}", invalid_color="#5A646E", invalid_text="–"),
        vec("speed.rule", "line", x=SAFE_L, y=378, x2=560, y2=378,
            color="#1C232A", width_px=1, z=6),

        # RIGHT - energy: one vertical indicator plus value and range.
        vec("energy.track", "vbar", x=1712, y=150, width=4, height=222,
            track_color="#1A222A", radius=2, opacity=1.0,
            progress={"signal": "soc", "max": 100, "color": "#C9D4DF"},
            alpha_when=soc_percent_rules(), z=42),
        txt("energy.value", x=1688, y=282, size=100, align="right",
            color="#E8EDF2", font_role="display", font=100, bind="soc",
            format="{}", invalid_color="#5A646E", invalid_text="--",
            alpha_when=soc_percent_rules()),
        txt("energy.pct", x=1700, y=302, size=30, align="left",
            color="#7C8894", font_role="medium", font=30, text="%",
            alpha_when=soc_percent_rules()),
        txt("energy.range", x=1688, y=344, size=28, align="right",
            color="#8A96A2", font_role="medium", font=28, tracking=1.5,
            bind="range", format="{} km", invalid_color="#5A646E"),
        txt("energy.untrusted", x=1688, y=222, size=20, align="right",
            color="#8A96A2", font_role="medium", font=20, tracking=2.5,
            text="CHARGE EST.", alpha=0.0, alpha_when=untrusted_only()),

        # CONTEXT - silent unless something is actually wrong. Sits under the
        # speed block, i.e. inside the left information column, because that
        # is the only region of design A that is never covered by the car.
        vec("ctx.dot", "roundrect", x=SAFE_L, y=404, width=8, height=8,
            radius=4, fill="#D8A657", alpha=0.0, alpha_when=door_open_only(),
            z=44),
        txt("ctx.door", x=SAFE_L + 20, y=409, size=21, align="left",
            color="#CBB27A", font_role="medium", font=21, tracking=3.0,
            text="FRONT LEFT DOOR", alpha=0.0, alpha_when=door_open_only()),
        vec("ctx.uart.dot", "roundrect", x=SAFE_L, y=404, width=8, height=8,
            radius=4, fill="#D8A657", alpha=0.0, alpha_when=uart_lost_only(),
            z=44),
        txt("ctx.uart", x=SAFE_L + 20, y=409, size=21, align="left",
            color="#D8A657", font_role="medium", font=21, tracking=3.0,
            text="DRIVE DATA LOST", alpha=0.0, alpha_when=uart_lost_only()),
    ]
    return scene("horizon_redesign_a", nodes)


# ----------------------------------------------------------------- design B

def scene_b():
    # One wide shallow arc is the ground line the car stands on. It also
    # carries the energy sweep, so the energy reading is part of the space
    # rather than a separate widget.
    arc_cx, arc_cy, arc_r = 960, -960, 1400
    nodes = [
        vec("bg", "vgradient", x=0, y=0, width=1920, height=480,
            **{"from": "#03050A", "to": "#080C12"}, z=0),
        # Horizon depth: two mirrored fades meeting under the car.
        vec("space.band.l", "hgradient", x=0, y=300, width=960, height=140,
            **{"from": "#04060A", "to": "#101820"}, opacity=0.85, z=1),
        vec("space.band.r", "hgradient", x=960, y=300, width=960, height=140,
            **{"from": "#101820", "to": "#04060A"}, opacity=0.85, z=1),
        vec("space.arc", "arc", cx=arc_cx, cy=arc_cy, radius=arc_r,
            start_deg=70, end_deg=110, width_px=2, color="#1A222B", z=2),
        vec("space.arc.ticks", "ticks", cx=arc_cx, cy=arc_cy, radius=arc_r,
            start_deg=70, end_deg=110, count=41, major_every=10,
            length_px=10, major_length_px=20, color="#141B22",
            major_color="#222C35", width_px=1, z=2),
        ground_pool(320, 386, 1280, 160, opacity=0.55),

        vehicle(580, 22, 760, 435),

        # LEFT - the speed block is tied to the car by a short connector, so
        # it reads as attached to the object instead of living in a column.
        vec("speed.tie", "line", x=508, y=316, x2=580, y2=316,
            color="#1E262E", width_px=1, z=12),
        txt("speed.value", x=468, y=300, size=170, align="right",
            color="#EAEFF4", font_role="ultralight", font=170,
            bind="speed", format="{}", invalid_color="#525C66",
            invalid_text="--"),
        txt("speed.unit", x=468, y=356, size=22, align="right",
            color="#76828E", font_role="medium", font=22, tracking=3.5,
            text="KM/H", alpha=0.8),

        # Gear as a vertical P-R-N-D scale with one lit entry.
        vec("gear.rule", "line", x=246, y=196, x2=246, y2=340,
            color="#1C242B", width_px=1, z=12),
        txt("gear.p", x=200, y=200, size=26, align="left", color="#5A646E",
            font_role="medium", font=26, text="P", alpha=0.25,
            alpha_when=[{"when": {"signal": "gear", "equals": 1},
                         "alpha": 0.95}]),
        txt("gear.r", x=200, y=244, size=26, align="left", color="#5A646E",
            font_role="medium", font=26, text="R", alpha=0.25,
            alpha_when=[{"when": {"signal": "gear", "equals": 2},
                         "alpha": 0.95}]),
        txt("gear.n", x=200, y=288, size=26, align="left", color="#5A646E",
            font_role="medium", font=26, text="N", alpha=0.25,
            alpha_when=[{"when": {"signal": "gear", "equals": 3},
                         "alpha": 0.95}]),
        txt("gear.d", x=200, y=332, size=26, align="left", color="#5A646E",
            font_role="medium", font=26, text="D", alpha=0.25,
            alpha_when=[{"when": {"signal": "gear", "equals": 4},
                         "alpha": 0.95}]),

        # RIGHT - energy rides the same ground arc as the car.
        vec("energy.arc", "arc", cx=arc_cx, cy=arc_cy, radius=arc_r,
            start_deg=70, end_deg=110, width_px=3, color="#161D24", z=30,
            opacity=1.0,
            progress={"signal": "soc", "max": 100, "color": "#C9D4DF",
                      "width_px": 3, "from": "end", "opacity": 0.95},
            alpha_when=soc_percent_rules()),
        txt("energy.value", x=1452, y=352, size=72, align="left",
            color="#E8EDF2", font_role="light", font=72, bind="soc",
            format="{}", invalid_color="#525C66", invalid_text="--",
            alpha_when=soc_percent_rules()),
        txt("energy.pct", x=1584, y=364, size=24, align="left",
            color="#76828E", font_role="medium", font=24, text="%",
            alpha_when=soc_percent_rules()),
        txt("energy.range", x=1452, y=392, size=24, align="left",
            color="#8A96A2", font_role="medium", font=24, tracking=1.5,
            bind="range", format="{} km", invalid_color="#5A646E"),
        txt("energy.untrusted", x=1452, y=330, size=18, align="left",
            color="#8A96A2", font_role="medium", font=18, tracking=2.5,
            text="CHARGE EST. - SEE RANGE", alpha=0.0,
            alpha_when=untrusted_only()),

        # BOTTOM RAIL - the top stays open because the car owns it.
        txt("rail.temp", x=SAFE_L, y=446, size=20, align="left",
            color="#6E7A86", font_role="medium", font=20, tracking=1.5,
            bind="temperature_primary", format="{}°C"),
        clock_node(SAFE_R, 446, size=20, color="#7C8894"),
        vec("rail.rule", "line", x=SAFE_L, y=424, x2=SAFE_R, y2=424,
            color="#141B22", width_px=1, z=6),

        # CONTEXT - on the open part of the spatial field, top left, with a
        # short rule that points toward the car. The car owns the centre.
        vec("ctx.rule", "line", x=SAFE_L, y=48, x2=528, y2=48,
            color="#3A3324", width_px=1, alpha=0.0, alpha_when=door_open_only(),
            z=44),
        txt("ctx.door", x=SAFE_L, y=72, size=20, align="left", color="#CBB27A",
            font_role="medium", font=20, tracking=4.0, text="FRONT LEFT DOOR",
            alpha=0.0, alpha_when=door_open_only()),
        vec("ctx.uart.rule", "line", x=SAFE_L, y=48, x2=528, y2=48,
            color="#3A3224", width_px=1, alpha=0.0, alpha_when=uart_lost_only(),
            z=44),
        txt("ctx.uart", x=SAFE_L, y=72, size=20, align="left", color="#D8A657",
            font_role="medium", font=20, tracking=4.0, text="DRIVE DATA LOST",
            alpha=0.0, alpha_when=uart_lost_only()),
    ]
    return scene("horizon_redesign_b", nodes)


# ----------------------------------------------------------------- design C

def scene_c():
    nodes = [
        vec("bg", "vgradient", x=0, y=0, width=1920, height=480,
            **{"from": "#04060A", "to": "#0A0F15"}, z=0),
        # Structured field: one wide light streak sitting behind the car.
        vec("field.streak.l", "hgradient", x=280, y=232, width=680, height=110,
            **{"from": "#04060A", "to": "#131B23"}, opacity=0.9, z=1),
        vec("field.streak.r", "hgradient", x=960, y=232, width=680, height=110,
            **{"from": "#131B23", "to": "#04060A"}, opacity=0.9, z=1),
        ground_pool(340, 392, 1240, 152, color="#1C242D", opacity=0.62),

        vehicle(600, 34, 720, 412),

        # TOP - precision rail with an integrated readout at each end.
        vec("rail.ticks", "tickrow", x=176, y=46, width=1568, count=113,
            major_every=8, height_px=4, major_height_px=9,
            color="#1B222A", major_color="#2A343E", width_px=1, z=6),
        txt("rail.temp", x=176, y=22, size=20, align="left", color="#8A96A2",
            font_role="medium", font=20, tracking=2.0,
            bind="temperature_primary", format="{}°C"),
        clock_node(1744, 22, size=20, align="left", color="#A8B3BE"),

        # LEFT - speed with a linear instrument scale underneath it.
        txt("speed.value", x=452, y=268, size=158, align="right",
            color="#EDF1F5", font_role="display_condensed", font=158,
            bind="speed", format="{}", invalid_color="#535D67",
            invalid_text="--"),
        txt("speed.unit", x=452, y=330, size=22, align="right",
            color="#76828E", font_role="medium", font=22, tracking=3.0,
            text="KM/H", alpha=0.85),
        vec("speed.scale", "tickrow", x=176, y=392, width=380, count=39,
            major_every=5, height_px=5, major_height_px=11,
            color="#1D242C", major_color="#2C3742", lit_color="#C9D4DF",
            width_px=2, progress={"signal": "speed", "max": 240}, z=8),
        vec("speed.scale.rule", "line", x=176, y=392, x2=556, y2=392,
            color="#161C23", width_px=1, z=7),

        # Gear as a horizontal row with a lit underline on the active entry.
        txt("gear.p", x=176, y=336, size=24, align="left", color="#5A646E",
            font_role="medium", font=24, text="P", alpha=0.3,
            alpha_when=[{"when": {"signal": "gear", "equals": 1},
                         "alpha": 0.95}]),
        txt("gear.r", x=222, y=336, size=24, align="left", color="#5A646E",
            font_role="medium", font=24, text="R", alpha=0.3,
            alpha_when=[{"when": {"signal": "gear", "equals": 2},
                         "alpha": 0.95}]),
        txt("gear.n", x=268, y=336, size=24, align="left", color="#5A646E",
            font_role="medium", font=24, text="N", alpha=0.3,
            alpha_when=[{"when": {"signal": "gear", "equals": 3},
                         "alpha": 0.95}]),
        txt("gear.d", x=314, y=336, size=24, align="left", color="#5A646E",
            font_role="medium", font=24, text="D", alpha=0.3,
            alpha_when=[{"when": {"signal": "gear", "equals": 4},
                         "alpha": 0.95}]),
        vec("gear.rule.p", "line", x=176, y=356, x2=196, y2=356,
            color="#C9D4DF", width_px=2, alpha=0.0,
            alpha_when=[{"when": {"signal": "gear", "equals": 1},
                         "alpha": 0.95}], z=44),
        vec("gear.rule.r", "line", x=222, y=356, x2=242, y2=356,
            color="#C9D4DF", width_px=2, alpha=0.0,
            alpha_when=[{"when": {"signal": "gear", "equals": 2},
                         "alpha": 0.95}], z=44),
        vec("gear.rule.n", "line", x=268, y=356, x2=288, y2=356,
            color="#C9D4DF", width_px=2, alpha=0.0,
            alpha_when=[{"when": {"signal": "gear", "equals": 3},
                         "alpha": 0.95}], z=44),
        vec("gear.rule.d", "line", x=314, y=356, x2=334, y2=356,
            color="#C9D4DF", width_px=2, alpha=0.0,
            alpha_when=[{"when": {"signal": "gear", "equals": 4},
                         "alpha": 0.95}], z=44),

        # RIGHT - segmented energy column plus a thin linear energy line.
        vec("energy.ticks", "vticks", x=1746, y=372, height=222, count=25,
            major_every=4, width_px=10, major_width_px=18,
            tick_height_px=2, color="#1D242C", major_color="#2C3742",
            lit_color="#C9D4DF", progress={"signal": "soc", "max": 100},
            alpha_when=soc_percent_rules(), z=42),
        vec("energy.line", "vbar", x=1712, y=150, width=3, height=222,
            track_color="#161C23", radius=1, opacity=1.0,
            progress={"signal": "soc", "max": 100, "color": "#9FB0BF"},
            alpha_when=soc_percent_rules(), z=42),
        txt("energy.value", x=1676, y=268, size=88, align="right",
            color="#EDF1F5", font_role="display_condensed", font=88,
            bind="soc", format="{}", invalid_color="#535D67",
            invalid_text="--", alpha_when=soc_percent_rules()),
        txt("energy.pct", x=1688, y=290, size=28, align="left",
            color="#76828E", font_role="medium", font=28, text="%",
            alpha_when=soc_percent_rules()),
        txt("energy.range", x=1676, y=330, size=26, align="right",
            color="#8A96A2", font_role="medium", font=26, tracking=1.5,
            bind="range", format="{} km", invalid_color="#5A646E"),
        txt("energy.untrusted", x=1676, y=214, size=18, align="right",
            color="#8A96A2", font_role="medium", font=18, tracking=2.5,
            text="CHARGE EST.", alpha=0.0, alpha_when=untrusted_only()),

        # CONTEXT - an instrument flag at the foot of the energy column,
        # right aligned, so it belongs to the readout cluster.
        vec("ctx.tick", "line", x=1744, y=386, x2=1744, y2=400,
            color="#3A3324", width_px=2, alpha=0.0,
            alpha_when=door_open_only(), z=44),
        txt("ctx.door", x=1732, y=412, size=20, align="right", color="#CBB27A",
            font_role="medium", font=20, tracking=4.0, text="FRONT LEFT DOOR",
            alpha=0.0, alpha_when=door_open_only()),
        vec("ctx.uart.tick", "line", x=1744, y=386, x2=1744, y2=400,
            color="#3A3224", width_px=2, alpha=0.0,
            alpha_when=uart_lost_only(), z=44),
        txt("ctx.uart", x=1732, y=412, size=20, align="right", color="#D8A657",
            font_role="medium", font=20, tracking=4.0, text="DRIVE DATA LOST",
            alpha=0.0, alpha_when=uart_lost_only()),
    ]
    return scene("horizon_redesign_c", nodes)


def scene(name, nodes):
    return {
        "scene": name,
        "version": 1,
        "status": "horizon redesign candidate - not production approved",
        "canvas": CANVAS,
        "manifest": "assets/manifest.json",
        "notes": [
            "All values come from VehicleState. Mock data exists only in "
            "tools/preview/scene_preview.py MOCK_STATES.",
            "No DRIVE / ALL CLOSED / UART OK text: a healthy car is silent.",
            "UART health is a Developer Mode concern; only UART LOST surfaces, "
            "and it surfaces through the warning path.",
            "A known-untrusted SOC is never drawn as a percentage.",
        ],
        "nodes": nodes,
    }


def main():
    out_dir = os.path.join(REPO_ROOT, "scenes")
    for name, builder in (("horizon_redesign_a", scene_a),
                          ("horizon_redesign_b", scene_b),
                          ("horizon_redesign_c", scene_c)):
        scene_dict = builder()
        path = os.path.join(out_dir, name + ".scene")
        with open(path, "w") as fh:
            json.dump(scene_dict, fh, indent=2)
            fh.write("\n")
        print(f"[scene] {len(scene_dict['nodes']):3d} nodes -> {path}")


if __name__ == "__main__":
    main()
