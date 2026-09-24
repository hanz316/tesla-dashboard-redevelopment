#!/usr/bin/env python3
"""Three Horizon style candidates, generated from one approved base.

The human review says the current Horizon is too plain: functional, clean, but
still an engineering preview. Three candidates add technology, depth and visual
energy - without adding information. Each is a design source in
assets/ui/horizon_v3_*.json; the scenes are generated from them, so nothing is
hand-painted and every candidate is reproducible.

The accepted information architecture, the approved speed/km/h spacing, the
UNKNOWN rules and the "no debug text" rule are inherited unchanged from v2.1.
What differs between candidates is only the *decorative and state-reactive*
layer, at three intensities:

    A  CYBER HUD        restrained: thin cyan lines, sparse ticks, a faint
                        ground glow. The most OEM-conservative of the three.
    B  CONCEPT EV       the primary candidate: layered horizon, digital road
                        plane, atmospheric band, energy rail, stage lighting.
    C  PERFORMANCE      most expressive: stronger perspective, more visible HUD
                        geometry, an active speed scale, reactive accents.

Usage:
    python3 tools/preview/build_horizon_v3.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.path.join(REPO, "assets", "ui", "horizon_v2_layout.json")
UI = os.path.join(REPO, "assets", "ui")
GEN = os.path.join(REPO, "tools", "preview", "build_horizon_v2.py")

# Each candidate: how strong the shared HUD language is, plus what it adds.
CANDIDATES = {
    "a_cyber_hud": {
        "name": "Candidate A - Cyber HUD",
        "intensity": 1.0,
        "accent_line_opacity": 0.35,
        "ticks": 25,
        "road_lines": 2,
        "stage": False,
        "atmosphere": False,
        "energy_rail": "vertical",
        "active_scale": False,
    },
    "b_concept_ev": {
        "name": "Candidate B - Concept EV (primary)",
        "intensity": 1.4,
        "accent_line_opacity": 0.50,
        "ticks": 33,
        "road_lines": 4,
        "stage": True,
        "atmosphere": True,
        "energy_rail": "horizontal",
        "active_scale": False,
    },
    "c_performance": {
        "name": "Candidate C - Futuristic Performance",
        "intensity": 1.8,
        "accent_line_opacity": 0.72,
        "ticks": 41,
        "road_lines": 6,
        "stage": True,
        "atmosphere": True,
        "energy_rail": "segmented",
        "active_scale": True,
    },
}

ACCENT = "accent"


def line(node_id, x, y, x2, y2, colour, opacity, width=1, z=6,
         layer="static", alpha_when=None, role="hud"):
    node = {"id": node_id, "kind": "vector", "shape": "line",
            "bounds": {"x": min(x, x2), "y": min(y, y2),
                       "w": abs(x2 - x), "h": abs(y2 - y)},
            "x2": x2, "y2": y2, "color_token": colour, "width_px": width,
            "opacity": opacity, "z": z, "layer": layer, "role": role}
    if alpha_when:
        node["visibility"] = alpha_when
    return node


def radial(node_id, x, y, w, h, colour, opacity, z=2, role="stage"):
    return {"id": node_id, "kind": "vector", "shape": "radial",
            "bounds": {"x": x, "y": y, "w": w, "h": h},
            "color_token": colour, "color_to_token": "background",
            "opacity_token": None, "opacity": opacity, "z": z,
            "layer": "static", "exempt_from_safe_area": True, "role": role}


def ticks(node_id, x, y, width, count, colour, opacity, length=6, z=6,
          progress=None, lit_token=None):
    node = {"id": node_id, "kind": "vector", "shape": "tickrow",
            "bounds": {"x": x, "y": y, "w": width, "h": length},
            "count": count, "height_px": length, "color_token": colour,
            "opacity": opacity, "z": z, "layer": "static", "role": "hud"}
    if progress:
        node["progress"] = {"binding": progress, "max": 200}
        node["lit_token"] = lit_token or ACCENT
    return node


def band(node_id, x, y, w, h, from_token, to_token, opacity, z=2,
         layer="static", role="atmosphere"):
    return {"id": node_id, "kind": "vector", "shape": "vgradient",
            "bounds": {"x": x, "y": y, "w": w, "h": h},
            "color_token": from_token, "color_to_token": to_token,
            "opacity_token": None, "opacity": opacity, "z": z, "layer": layer,
            "exempt_from_safe_area": True, "role": role}


def state_alpha(binding, opacity, z=8, layer="dynamic", role="state"):
    """Visible only while a signal is true."""
    return {"binding": binding, "show_when_true": True, "opacity": opacity,
            "z": z, "layer": layer, "role": role}


def indicator_band(side, intensity):
    x = 612 if side == "left" else 1248
    return {
        "id": f"hud.indicator.{side}",
        "kind": "vector", "shape": "line",
        "bounds": {"x": x, "y": 190, "w": 2, "h": 170},
        "color_token": "warning", "width_px": 3, "opacity": 0.0,
        "z": 12, "layer": "dynamic", "role": "state",
        "visibility": {"binding": f"indicator_{side}", "show_when_true": True},
        "visible_opacity": round(0.45 * intensity, 3),
    }


def build(base, spec):
    layout = json.loads(json.dumps(base))
    layout["scene"] = f"horizon_v3_{spec['key']}"
    layout["status"] = "AWAITING HUMAN VISUAL SELECTION"
    layout["style_candidate"] = spec["name"]
    layout["revision"] = "v3"
    layout["derived_from"] = os.path.relpath(BASE, REPO)
    opacity = spec["accent_line_opacity"]
    extra = []

    # --- shared HUD language ------------------------------------------
    extra.append(ticks("hud.speed.ticks", 124, 90, 296, spec["ticks"],
                       ACCENT, opacity, length=7, z=7))
    extra.append(line("hud.speed.scale", 124, 96, 420, 96, ACCENT, opacity,
                      z=6))
    if spec["active_scale"]:
        # Only C: the tick field lights up to the current speed, so the scale
        # carries a reading without adding a number.
        extra[-1] = ticks("hud.speed.ticks", 124, 90, 296, spec["ticks"],
                          ACCENT, opacity, length=7, z=7,
                          progress="speed", lit_token=ACCENT)
    extra.append(line("hud.horizon.light", 360, 296, 1560, 296, ACCENT,
                      round(opacity * (1.4 if spec["atmosphere"] else 1.0), 3),
                      z=5))
    if spec["atmosphere"]:
        extra.append(band("hud.atmosphere", 300, 236, 1320, 60,
                          "surface", "background", 0.42, z=2))
    # perspective road lines, converging behind the car
    # Road lines stay inside the vehicle zone (560..1360) so they never run
    # through the driver or energy columns.
    for index in range(spec["road_lines"]):
        spread = 60 + index * 46
        extra.append(line(f"hud.road.l{index}", max(566, 960 - spread * 1.3), 456,
                          960 - spread * 0.5, 300, ACCENT,
                          round(opacity * 0.5, 3), z=4, role="road"))
        extra.append(line(f"hud.road.r{index}", min(1354, 960 + spread * 1.3), 456,
                          960 + spread * 0.5, 300, ACCENT,
                          round(opacity * 0.5, 3), z=4, role="road"))
    # vehicle grounding glow
    extra.append(radial("hud.vehicle.glow", 720, 352, 480, 92, ACCENT,
                        round(0.10 * spec["intensity"], 3), z=3))
    if spec["stage"]:
        extra.append(radial("hud.vehicle.stage", 640, 120, 640, 320, ACCENT,
                            0.10, z=2))
        extra.append(line("hud.stage.edge.l", 560, 118, 560, 430, ACCENT,
                          0.28, z=5))
        extra.append(line("hud.stage.edge.r", 1360, 118, 1360, 430, ACCENT,
                          0.28, z=5))

    # --- energy rail ---------------------------------------------------
    if spec["energy_rail"] == "vertical":
        # Right of the energy text column (which ends at x 1806), not across it.
        extra.append(line("hud.energy.rail", 1814, 150, 1814, 350, ACCENT,
                          opacity, z=6))
    elif spec["energy_rail"] == "horizontal":
        extra.append(line("hud.energy.rail", 1060, 300, 1606, 300, ACCENT,
                          opacity, z=6))
        extra.append(ticks("hud.energy.ticks", 1440, 300, 166, 6, ACCENT,
                           opacity, length=5, z=6))
    else:
        extra.append(line("hud.energy.rail", 1000, 300, 1606, 300, ACCENT,
                          0.8, z=6))
        extra.append(ticks("hud.energy.ticks", 1400, 300, 206, 12, ACCENT,
                           opacity, length=7, z=6))
        extra.append({
            "id": "hud.energy.flow", "kind": "vector", "shape": "line",
            "bounds": {"x": 1000, "y": 300, "w": 180, "h": 3},
            "color_token": ACCENT, "width_px": 3, "opacity": 0.85, "z": 7,
            "layer": "dynamic", "role": "state",
            "visibility": {"binding": "battery_power", "show_when_valid": True},
        })

    # --- state-reactive language (all three, intensity differs) --------
    extra.append(indicator_band("left", spec["intensity"]))
    extra.append(indicator_band("right", spec["intensity"]))
    extra.append({
        "id": "hud.brake.glow", "kind": "vector", "shape": "radial",
        "bounds": {"x": 800, "y": 330, "w": 320, "h": 110},
        "color_token": "critical", "color_to_token": "background",
        "opacity": 0.0, "z": 9, "layer": "dynamic", "role": "state",
        "exempt_from_safe_area": True,
        "visibility": {"binding": "brake", "show_when_true": True},
        "visible_opacity": round(0.20 * spec["intensity"], 3),
    })
    if spec["stage"]:
        extra.append({
            "id": "hud.headlight.road", "kind": "vector", "shape": "polygon",
            "points": [[960, 300], [1500, 456], [1420, 456], [960, 330]],
            "bounds": {"x": 960, "y": 300, "w": 540, "h": 156},
            "color_token": ACCENT, "opacity": 0.0, "z": 4,
            "layer": "dynamic", "role": "state",
            "visibility": {"binding": "headlight", "show_when_true": True},
            "visible_opacity": round(0.12 * spec["intensity"], 3),
        })
    for door, (x, y) in (("fl", (668, 150)), ("fr", (1204, 150)),
                         ("rl", (668, 320)), ("rr", (1204, 320))):
        extra.append({
            "id": f"hud.door.{door}", "kind": "vector", "shape": "roundrect",
            "bounds": {"x": x, "y": y, "w": 48, "h": 48},
            "radius_token": "pill", "color_token": "warning",
            "stroke_token": "warning", "opacity": 0.0, "z": 11,
            "layer": "dynamic", "role": "state",
            "visibility": {"binding": f"door_{door}", "show_when_true": True},
            "visible_opacity": 0.55,
        })
    extra.append({
        "id": "hud.frunk.marker", "kind": "vector", "shape": "line",
        "bounds": {"x": 880, "y": 120, "w": 160, "h": 2},
        "color_token": "warning", "width_px": 3, "opacity": 0.0, "z": 11,
        "layer": "dynamic", "role": "state",
        "visibility": {"binding": "frunk", "show_when_true": True},
        "visible_opacity": 0.55,
    })
    extra.append({
        "id": "hud.trunk.marker", "kind": "vector", "shape": "line",
        "bounds": {"x": 880, "y": 392, "w": 160, "h": 2},
        "color_token": "warning", "width_px": 3, "opacity": 0.0, "z": 11,
        "layer": "dynamic", "role": "state",
        "visibility": {"binding": "trunk", "show_when_true": True},
        "visible_opacity": 0.55,
    })

    layout["components"] = layout["components"] + extra
    layout["style_layers"] = {
        "STATIC_BACKGROUND": ["background", "atmosphere.ambient", "road.plane",
                              "hud.atmosphere", "hud.vehicle.stage"],
        "STATIC_OVERLAY": [node["id"] for node in extra
                           if node.get("layer") == "static"],
        "STATE_OVERLAY": [node["id"] for node in extra
                          if node.get("layer") == "dynamic"],
        "CHEAP_ANIMATION": ["hud.indicator.left", "hud.indicator.right",
                            "hud.energy.flow"],
    }
    return layout


def main():
    base = json.load(open(BASE))
    written = []
    for key, spec in CANDIDATES.items():
        spec = dict(spec, key=key)
        layout = build(base, spec)
        path = os.path.join(UI, f"horizon_v3_{key}_layout.json")
        with open(path, "w") as fh:
            json.dump(layout, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        scene = os.path.join(REPO, "scenes", f"horizon_v3_{key}.scene")
        subprocess.run([sys.executable, GEN, "--layout", path, "--out", scene],
                       check=True, capture_output=True)
        written.append((key, path, scene))
        print(f"[v3] {spec['name']:38s} -> {os.path.relpath(scene, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
