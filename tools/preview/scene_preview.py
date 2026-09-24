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

# Named typographic roles. Real automotive HMI typography is part of the
# design, not an implementation detail, so scenes refer to a role instead of
# an absolute path. DIN is the instrumentation face; Helvetica Neue Light /
# UltraLight carries the large calm numerals; SF Pro carries small labels.
FONT_ROLES = {
    "display": ("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", 0),
    "display_condensed":
        ("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", 0),
    "ultralight": ("/System/Library/Fonts/HelveticaNeue.ttc", 5),
    "light": ("/System/Library/Fonts/HelveticaNeue.ttc", 7),
    "medium": ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    "bold": ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
    "system": ("/System/Library/Fonts/SFNS.ttf", 0),
}
_FONT_CACHE = {}

# Mock states required by the Horizon redesign review. Preview only.
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

MOCK_STATES.update({
    "normal_drive": {
        "speed": 88, "gear": 4, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "temperature_primary": 22,
        "uart_health": "UART OK",
        "closures": "ALL CLOSED",
    },
    "door_fl_open": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "door_fl": True,
        "temperature_primary": 22,
        "uart_health": "UART OK",
        "closures": "OPEN FL",
    },
    # No telemetry at all: every value must render as unavailable rather than
    # as a stale or invented number.
    "uart_lost": {
        "uart_health": "UART LOST",
    },
    # SOC known-untrusted (the real MCU reports a stuck 97%). The percentage
    # must be suppressed; range is still allowed because it is trusted.
    "soc_untrusted": {
        "speed": 88, "gear": 4, "soc": 97, "soc_trusted": False,
        "range": 253, "range_trusted": True,
        "temperature_primary": 22,
        "uart_health": "UART OK",
        "closures": "ALL CLOSED",
    },
    # Developer preview only. These exist so the Horizon vehicle-state QA can
    # cover every lighting channel and every moving panel separately; they are
    # mock data and are never used by production (see the production guard in
    # the provider and VehicleVisualController::applyMockState).
    "vehicle_brake": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True, "brake": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "ALL CLOSED",
    },
    "vehicle_left": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True, "indicator_left": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "ALL CLOSED",
    },
    "vehicle_right": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True, "indicator_right": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "ALL CLOSED",
    },
    "vehicle_hazard": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "indicator_left": True, "indicator_right": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "ALL CLOSED",
    },
    "vehicle_headlight": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True, "headlight": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "ALL CLOSED",
    },
    "vehicle_brake_left": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "brake": True, "indicator_left": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "ALL CLOSED",
    },
    "vehicle_brake_hazard": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "brake": True, "indicator_left": True, "indicator_right": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "ALL CLOSED",
    },
    "vehicle_door_fr": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True, "door_fr": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "OPEN FR",
    },
    "vehicle_door_rl": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True, "door_rl": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "OPEN RL",
    },
    "vehicle_door_rr": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True, "door_rr": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "OPEN RR",
    },
    "vehicle_frunk": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True, "frunk": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "OPEN FRUNK",
    },
    "vehicle_trunk_brake": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "trunk": True, "brake": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "OPEN TRUNK",
    },
    # The trunk carries the inner indicator lamps: these three exist so the
    # ownership compositing can be validated against direct renders.
    "vehicle_trunk_left": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "trunk": True, "indicator_left": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "OPEN TRUNK",
    },
    "vehicle_trunk_right": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "trunk": True, "indicator_right": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "OPEN TRUNK",
    },
    "vehicle_trunk_hazard": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "trunk": True, "indicator_left": True, "indicator_right": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "OPEN TRUNK",
    },
    "vehicle_fl_rr_brake": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "door_fl": True, "door_rr": True, "brake": True,
        "temperature_primary": 22, "uart_health": "UART OK",
        "closures": "OPEN FL RR",
    },
    # A stale signal must render as unknown, never as a confident "closed".
    "vehicle_stale_doors": {
        "speed": 0, "gear": 1, "soc": 63, "soc_trusted": True,
        "range": 253, "range_trusted": True,
        "uart_health": "UART STALE", "closures": "DOORS --",
    },
    # A fully populated DEV state for the V6 page set: every signal the pages
    # can bind, including the Commander telemetry that drives the energy and
    # pulse screens. Developer preview only - production Horizon never sees
    # this, which is why the SOC here comes from the Commander field and not
    # from the rejected MCU byte.
    "v6_pages_dev": {
        "speed": 88, "gear": 4, "soc": 97, "soc_trusted": False,
        "range": 253, "range_trusted": True, "temperature_primary": 22,
        "uart_health": "UART OK", "closures": "ALL CLOSED",
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False,
        "indicator_left": True, "indicator_right": False,
        "brake": False, "headlight": True,
        "closures_detail": "FL -  FR -  RL -  RR -   FRUNK -  TRUNK -",
        "lights_detail": "HEADLIGHT ON · RUNNING ON · INDICATOR L",
        "tires_detail": "F 2.83 2.85 · R 2.93 2.75 bar",
        "actual_soc": 63,
        "battery_power": -12.4, "battery_power_abs": 12.4,
        "battery_voltage": 372.5, "battery_current": -33.2,
        "total_charged_energy": 812.4, "total_discharged_energy": 790.1,
        "accelerator_position": 18.0,
        "commander_link": 1, "commander_detail": "NativeBle · v1.2.0",
        "nav_manoeuvre": "IN 300 M TURN RIGHT",
        "nav_distance": 300, "nav_eta": "14:32",
        "nav_capability": "BASIC_MANEUVER",
        "trip_distance": 42.6, "trip_time_text": "0:58",
        "average_speed": 44.0,
        "warning_active": False, "warning_text": "",
        "developer_mode": True,
        "appearance_text": "AUTO", "brightness_text": "80 %",
        "speed_unit_text": "km/h", "temperature_unit_text": "°C",
        "tire_pressure_unit_text": "bar", "clock_text": "24 h",
        "default_page_text": "Horizon", "warning_sound_text": "ON",
        "developer_mode_text": "ON",
        "dev_uart": "UART OK · /dev/ttyS5 38400 · READ-ONLY",
        "dev_parser": "2637 frames · 0 checksum errors",
        "dev_commander": "CMDR NativeBle · connected · SOC override active",
        "dev_soc": "SOC: MCU 97 (rejected) → Commander 63",
        "dev_gear": "GEAR: mapping unconfirmed (0x02 byte 3 LIKELY)",
        "dev_frame": "frame 18.4 ms · 54 fps · budget 33.3 ms",
        "dev_memory": "RSS 3.7 MB · resident assets 1.6 MB",
        "dev_hint": "DEV/REPLAY · mock state, never vehicle data",
    },
    # ---------------------------------------------------------- Horizon V2
    # Developer fixtures for the Horizon V2 screenshot harness and its layout
    # QA. These are the only place a Horizon V2 screen gets its values, and they
    # live in the previewer's mock table like every other fixture: the runtime
    # projection is the production path and has no mock data at all.
    "h2_closed_off": {
        # Rendered value check: the car closed with every lamp off, so a render
        # of it must equal a render of the base asset alone.
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": False, "headlight": False,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_neutral": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_brake": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": True, "indicator_left": False, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_left": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": True, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_right": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": True,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_hazard": {
        # Hazard is both channels, exactly as the runtime's safety layer
        # presents it; there is no third lamp.
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": True, "indicator_right": True,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_door_fl": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": True, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_all_doors": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": True, "door_fr": True, "door_rl": True, "door_rr": True,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_frunk": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": True, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_trunk": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": True, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_door_fr": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": False, "door_fr": True, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_door_rl": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": True, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_door_rr": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": True,
        "frunk": False, "trunk": False, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_trunk_left": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": True, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": True, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_trunk_hazard": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": True, "indicator_right": True,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": True, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_mixed": {
        "speed": 88, "gear": 4, "range": 253, "actual_soc": 63,
        "temperature_primary": 22, "position_light": True, "headlight": True,
        "brake": True, "indicator_left": True, "indicator_right": False,
        "door_fl": True, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": True, "trunk": True, "battery_power": -12.4,
        "warning_active": False, "warning_text": "",
    },
    "h2_low_soc": {
        "speed": 74, "gear": 4, "range": 42, "actual_soc": 14,
        "temperature_primary": 19, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -18.5,
        "warning_active": False, "warning_text": "",
    },
    "h2_unknown": {
        # Nothing from the car and nothing from the module: every value on the
        # screen must be its placeholder, and no zero may stand in for a value
        # nobody sent.
        "warning_active": False, "warning_text": "",
    },
    "h2_navigation": {
        "speed": 68, "gear": 4, "range": 251, "actual_soc": 62,
        "temperature_primary": 23, "position_light": True, "headlight": True,
        "brake": False, "indicator_left": False, "indicator_right": False,
        "door_fl": False, "door_fr": False, "door_rl": False, "door_rr": False,
        "frunk": False, "trunk": False, "battery_power": -14.2,
        "warning_active": False, "warning_text": "",
        "nav_manoeuvre": "IN 300 M TURN RIGHT", "nav_distance": 300,
        "nav_instruction": "TURN RIGHT ONTO QUEEN ST",
    },
})



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
    if "lte" in cond:
        return sig.valid and sig.value is not None and float(sig.value) <= float(cond["lte"])
    if "gte" in cond:
        return sig.valid and sig.value is not None and float(sig.value) >= float(cond["gte"])
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


def progress_color(progress, state):
    """The fill colour of a value-driven bar.

    A bar whose colour depends on its own value (SOC turning amber, then red)
    states that as `color_when` rules on the progress block, the same way a node
    states its own colour. Falls back to a plain `color`.
    """
    for rule in progress.get("color_when", []):
        if condition_holds(rule["when"], state):
            return rule["color"]
    return progress.get("color", "#3D9BFF")


def progress_ratio(progress, state):
    """Value / max, or None when there is no value to draw."""
    sig = state.signal(progress["signal"])
    if not sig.valid or sig.value is None:
        return None
    maximum = float(progress.get("max", 100.0))
    if maximum <= 0:
        return 0.0
    return max(0.0, min(1.0, float(sig.value) / maximum))


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
        # The node's own placeholder, not a generic "--": those placeholders
        # carry meaning on the panel ("NO ROUTE", "CLOSURES ?", "-- km") and
        # the runtime uses the same field, so the preview must not show a
        # different picture from the device.
        if "invalid_text" in node:
            return node["invalid_text"], False
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

def load_font(size, bold=False, role=None):
    key = (role, size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    candidates = []
    if role and role in FONT_ROLES:
        candidates.append(FONT_ROLES[role])
    candidates += [((FONT_BOLD if bold else FONT_REG), 0)]
    candidates.append((FALLBACK_FONT, 0))
    for path, index in candidates:
        try:
            font = ImageFont.truetype(path, size, index=index)
            _FONT_CACHE[key] = font
            return font
        except Exception:
            continue
    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def hex_to_rgb(value, alpha=255):
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


def alpha_when(node, state, default_key="alpha"):
    """Conditional opacity - how contextual UI appears and disappears."""
    for rule in node.get("alpha_when", []):
        if condition_holds(rule["when"], state):
            return rule["alpha"]
    return node.get(default_key, 1.0)


def resolve_color(node, state, default_key="color"):
    color = pick_color(node, state, default_key)
    alpha = alpha_when(node, state)
    return hex_to_rgb(color, max(0, min(255, int(round(alpha * 255)))))


def draw_text(img, node, state):
    text, valid = resolve_value(node, state)
    alpha = alpha_when(node, state)
    if not valid:
        text = node.get("invalid_text", text)
        alpha *= node.get("invalid_alpha", 1.0)
        color = node.get("invalid_color", pick_color(node, state))
    else:
        color = pick_color(node, state)
    font = load_font(node.get("font", 32), node.get("bold", False),
                     node.get("font_role"))
    draw = ImageDraw.Draw(img)
    x = node.get("x", 0)
    y = node.get("y", 0)
    anchor_map = {"center": "mm", "left": "lm", "right": "rm"}
    anchor = anchor_map.get(node.get("align", "center"), "mm")
    fill = hex_to_rgb(color, max(0, min(255, int(round(alpha * 255)))))
    if alpha <= 0.0 or text == "":
        return
    shadow = node.get("shadow", True)
    tracking = node.get("tracking", 0)
    if tracking:
        # PIL has no letter-spacing, so draw glyph by glyph. Needed because
        # wide-tracked small capitals are most of the "OEM" read.
        total = 0
        widths = []
        for ch in text:
            w = draw.textlength(ch, font=font)
            widths.append(w)
            total += w + tracking
        total -= tracking
        if anchor == "mm":
            cx = x - total / 2.0
        elif anchor == "rm":
            cx = x - total
        else:
            cx = x
        for ch, w in zip(text, widths):
            if shadow:
                draw.text((cx + 1, y + 1), ch, font=font,
                          fill=(0, 0, 0, int(160 * alpha)))
            draw.text((cx, y), ch, font=font, fill=fill)
            cx += w + tracking
        return
    if shadow:
        draw.text((x + 1, y + 1), text, font=font,
                  fill=(0, 0, 0, int(160 * alpha)), anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


def draw_vector(img, node, state):
    draw = ImageDraw.Draw(img, "RGBA")
    x, y = node.get("x", 0), node.get("y", 0)
    w, h = node.get("width", 0), node.get("height", 0)
    shape = node.get("shape", "rect")
    opacity = node.get("opacity", 1.0)
    opacity *= alpha_when(node, state)
    # A fully transparent shape must not be drawn at all. Handing Pillow an
    # alpha-0 fill is not the same as not drawing: it still writes the pixels
    # (flattening whatever was under it), which is how a hidden element left a
    # visible rectangle behind.
    if opacity <= 0.003:
        return

    if shape == "vgradient":
        top = hex_to_rgb(node["from"], int(255 * opacity))
        bottom = hex_to_rgb(node["to"], int(255 * opacity))
        for row in range(h):
            t = row / max(1, h - 1)
            col = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(4))
            draw.line([(x, y + row), (x + w, y + row)], fill=col)
        return

    if shape == "hgradient":
        # Left-to-right fade. Used for the soft light streak behind the car
        # and for the horizon band, where a hard edge would read as a panel.
        left = hex_to_rgb(node["from"], int(255 * opacity))
        right = hex_to_rgb(node["to"], int(255 * opacity))
        for col in range(w):
            t = col / max(1, w - 1)
            mix = tuple(int(left[i] + (right[i] - left[i]) * t) for i in range(4))
            draw.line([(x + col, y), (x + col, y + h)], fill=mix)
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

    if shape == "line":
        draw.line([(x, y), (node.get("x2", x), node.get("y2", y))],
                  fill=hex_to_rgb(node.get("color", "#2A333D"),
                                  int(255 * opacity)),
                  width=node.get("width_px", 1))
        return

    if shape == "polygon":
        pts = [tuple(p) for p in node["points"]]
        draw.polygon(pts, fill=hex_to_rgb(node.get("fill", "#101519"),
                                          int(255 * opacity)))
        if "stroke" in node:
            draw.line(pts + [pts[0]],
                      fill=hex_to_rgb(node["stroke"], int(255 * opacity)),
                      width=node.get("width_px", 1))
        return

    if shape == "arc":
        return draw_arc(draw, node, state, opacity)

    if shape == "ticks":
        return draw_arc_ticks(draw, node, state, opacity)

    if shape == "tickrow":
        return draw_tick_row(draw, node, state, opacity)

    if shape == "vbar":
        return draw_vbar(draw, node, state, opacity)

    if shape == "vticks":
        return draw_vticks(draw, node, state, opacity)

    if shape == "roundrect":
        radius = node.get("radius", 10)
        progress = node.get("progress")
        # A value-driven bar may be just the fill: when the layout draws its own
        # track as a separate node, this shape must not paint a filled block
        # underneath it.
        if "fill" in node or progress is None:
            draw.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                                   fill=hex_to_rgb(node.get("fill", "#182028"),
                                                   int(255 * opacity)))
        if "stroke" in node:
            # The stroke has to honour the same opacity as the fill, or a hidden
            # element still draws its outline - which is exactly how an empty
            # navigation rectangle stayed visible on a screen with no route.
            draw.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                                   outline=hex_to_rgb(node["stroke"],
                                                      int(255 * opacity)), width=2)
        if progress:
            ratio = progress_ratio(progress, state)
            if ratio is not None:
                fill_w = max(4.0, w * ratio)
                draw.rounded_rectangle([x, y, x + fill_w, y + h], radius=radius,
                                       fill=hex_to_rgb(progress_color(progress, state),
                                                       int(255 * opacity *
                                                           progress.get("opacity", 1.0))))
        return

    draw.rectangle([x, y, x + w, y + h],
                   fill=hex_to_rgb(node.get("fill", "#000000"),
                                   int(255 * opacity)))


def _arc_bounds(node):
    r = node["radius"]
    cx, cy = node["cx"], node["cy"]
    return [cx - r, cy - r, cx + r, cy + r]


def draw_arc(draw, node, state, opacity):
    """Stroke arc with an optional value-driven sweep.

    Angles follow PIL/NanoVG convention: 0 deg at 3 o'clock, clockwise.
    """
    bounds = _arc_bounds(node)
    width = node.get("width_px", 4)
    start = node.get("start_deg", 0)
    end = node.get("end_deg", 360)
    draw.arc(bounds, start=start, end=end,
             fill=hex_to_rgb(node.get("color", "#232B34"),
                             int(255 * opacity)), width=width)
    prog = node.get("progress")
    if not prog:
        return
    sig = state.signal(prog["signal"])
    if not sig.valid or sig.value is None:
        return
    maximum = float(prog.get("max", 100.0))
    ratio = 0.0 if maximum <= 0 else float(sig.value) / maximum
    ratio = max(0.0, min(1.0, ratio))
    if ratio <= 0.0:
        return
    sweep = (end - start) * ratio
    if prog.get("from") == "end":
        lo, hi = end - sweep, end
    else:
        lo, hi = start, start + sweep
    draw.arc(bounds, start=lo, end=hi,
             fill=hex_to_rgb(prog.get("color", "#C9D4DF"),
                             int(255 * opacity * prog.get("opacity", 1.0))),
             width=prog.get("width_px", width))


def draw_arc_ticks(draw, node, state, opacity):
    """Radial tick marks - the quiet instrument texture in designs B and C."""
    import math
    cx, cy = node["cx"], node["cy"]
    start = node.get("start_deg", 0)
    end = node.get("end_deg", 360)
    count = node.get("count", 40)
    outer = node["radius"]
    length = node.get("length_px", 6)
    major_every = node.get("major_every", 0)
    major_length = node.get("major_length_px", length)
    color = hex_to_rgb(node.get("color", "#2A333D"), int(255 * opacity))
    major_color = hex_to_rgb(node.get("major_color", node.get("color",
                                                             "#3A4550")),
                             int(255 * opacity))
    for i in range(count):
        t = i / max(1, count - 1)
        ang = math.radians(start + (end - start) * t)
        is_major = major_every and (i % major_every == 0)
        ln = major_length if is_major else length
        x0 = cx + math.cos(ang) * outer
        y0 = cy + math.sin(ang) * outer
        x1 = cx + math.cos(ang) * (outer - ln)
        y1 = cy + math.sin(ang) * (outer - ln)
        draw.line([(x0, y0), (x1, y1)],
                  fill=major_color if is_major else color,
                  width=node.get("width_px", 1))


def draw_tick_row(draw, node, state, opacity):
    """Linear tick rule. Optionally lights the ticks below a bound value."""
    x, y = node.get("x", 0), node.get("y", 0)
    span = node.get("width", 0)
    count = node.get("count", 24)
    height = node.get("height_px", 8)
    major_every = node.get("major_every", 0)
    major_height = node.get("major_height_px", height)
    color = hex_to_rgb(node.get("color", "#252E37"), int(255 * opacity))
    major_color = hex_to_rgb(node.get("major_color", "#323D48"),
                             int(255 * opacity))
    lit_color = hex_to_rgb(node.get("lit_color", "#C9D4DF"), int(255 * opacity))
    lit_ratio = None
    prog = node.get("progress")
    if prog:
        sig = state.signal(prog["signal"])
        if sig.valid and sig.value is not None:
            maximum = float(prog.get("max", 100.0))
            lit_ratio = 0.0 if maximum <= 0 else max(
                0.0, min(1.0, float(sig.value) / maximum))
    for i in range(count):
        t = i / max(1, count - 1)
        is_major = major_every and (i % major_every == 0)
        hh = major_height if is_major else height
        col = major_color if is_major else color
        if lit_ratio is not None and t <= lit_ratio:
            col = lit_color
        draw.line([(x + span * t, y - hh), (x + span * t, y)], fill=col,
                  width=node.get("width_px", 1))


def draw_vticks(draw, node, state, opacity):
    """Vertical tick column; lights bottom-up with the bound value."""
    x = node.get("x", 0)
    bottom = node.get("y", 0)
    span = node.get("height", 0)
    count = node.get("count", 24)
    width = node.get("width_px", 8)
    major_every = node.get("major_every", 0)
    major_width = node.get("major_width_px", width)
    color = hex_to_rgb(node.get("color", "#252E37"), int(255 * opacity))
    major_color = hex_to_rgb(node.get("major_color", "#323D48"),
                             int(255 * opacity))
    lit_color = hex_to_rgb(node.get("lit_color", "#C9D4DF"), int(255 * opacity))
    lit_ratio = None
    prog = node.get("progress")
    if prog:
        sig = state.signal(prog["signal"])
        if sig.valid and sig.value is not None:
            maximum = float(prog.get("max", 100.0))
            lit_ratio = 0.0 if maximum <= 0 else max(
                0.0, min(1.0, float(sig.value) / maximum))
    for i in range(count):
        t = i / max(1, count - 1)
        is_major = major_every and (i % major_every == 0)
        ww = major_width if is_major else width
        col = major_color if is_major else color
        if lit_ratio is not None and t <= lit_ratio:
            col = lit_color
        yy = bottom - span * t
        draw.line([(x, yy), (x + ww, yy)], fill=col,
                  width=node.get("tick_height_px", 2))


def draw_vbar(draw, node, state, opacity):
    """Vertical track with a bottom-up value fill (energy in designs A/B/C)."""
    x, y = node.get("x", 0), node.get("y", 0)
    w, h = node.get("width", 4), node.get("height", 100)
    radius = node.get("radius", w // 2)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                           fill=hex_to_rgb(node.get("track_color", "#1A222A"),
                                           int(255 * opacity)))
    prog = node.get("progress")
    if not prog:
        return
    ratio = progress_ratio(prog, state)
    if ratio is None:
        return
    if ratio <= 0.0:
        return
    fill_h = max(2.0, h * ratio)
    draw.rounded_rectangle([x, y + h - fill_h, x + w, y + h], radius=radius,
                           fill=hex_to_rgb(progress_color(prog, state),
                                           int(255 * opacity *
                                               prog.get("opacity", 1.0))))


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
    else:
        # to_state: closed draws nothing. `--t` selects the position along the
        # motion, so QA can render an intermediate angle; t = 1 is the fully
        # open terminal state, which is the runtime's steady state.
        if not (sig.valid and sig.value):
            return None
        position = min(1.0, max(0.0, float(t_norm)))
        idx = int(round(position * (frames - 1)))
    path = provider.path_for(os.path.join(seq["dir"], f"{idx:03d}.png"))
    return path if os.path.isfile(path) else None


def moving_lighting_contract():
    """The trunk-attached lighting contract, if the asset set provides one.

    A panel that carries lighting can only be composited correctly if its light
    is rendered with the panel - a 2D warp of a closed-position overlay is not
    exact for a panel with depth. See
    tools/blender/build_trunk_lighting_variants.py.
    """
    path = os.path.join(REPO_ROOT, "assets",
                        "vehicle_state_moving_lighting.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as fh:
            return json.load(fh).get("panels", {})
    except (OSError, ValueError):
        return {}


def active_channels(state):
    """Which lighting channels the state asks for, from the mock/state signals."""
    channels = set()
    for name, bind in (("INDICATOR_LEFT", "indicator_left"),
                       ("INDICATOR_RIGHT", "indicator_right")):
        sig = state.signal(bind)
        if sig.valid and sig.value:
            channels.add(name)
    return channels


def panel_lighting_frames(provider, panel_id, seq_id, bind, state, t_norm,
                          contract):
    """Frames for a moving panel, using its lighting variants when needed.

    Returns (paths, covered). `covered` names the lighting channels the
    returned images already contain, so the fixed-position overlay for those
    channels is not drawn again at the closed-position location. A state that
    lights both channels (hazard) returns both variants: the two inner lamps
    are disjoint, so drawing them in sequence is exact.
    """
    path = sequence_frame(provider, seq_id, bind, state, t_norm)
    if path is None:
        return [], set()
    entry = contract.get(panel_id)
    if not entry:
        return [path], set()
    carriers = set(entry.get("carries", []))
    active = active_channels(state) & carriers
    if not active:
        return [path], set()
    # One variant image per channel set. Drawing two full-vehicle variants in
    # sequence would let the second one's unlit pixels overwrite the first one's
    # lit lamp, so "both" is its own render rather than a composition.
    if {"INDICATOR_LEFT", "INDICATOR_RIGHT"} <= active:
        variant = "ind_both"
    elif "INDICATOR_LEFT" in active:
        variant = "ind_left"
    else:
        variant = "ind_right"
    spec = (entry.get("variants") or {}).get(variant)
    if not spec:
        return [path], set()
    candidate = provider.path_for(
        os.path.join(spec["dir"], os.path.basename(path)))
    if not os.path.isfile(candidate):
        return [path], set()
    return [candidate], active


def paste_scaled(base, path, x, y, w, h):
    img = Image.open(path).convert("RGBA")
    if (img.width, img.height) != (w, h):
        img = img.resize((w, h), Image.LANCZOS)
    base.alpha_composite(img, (int(x), int(y)))


_DELTA_INDEX = None
_DELTA_WARNED = False


def delta_index():
    """Map every state render to the layer that contains only its changes.

    Every state render in the asset set is a whole car, so compositing two of
    them repaints the first one's open panel back to closed. The bake step
    (tools/assets/bake_vehicle_deltas.py) writes, for each state frame, the
    pixels that frame changes about the car; composing the base with those
    layers is what makes "door FL + door RL open" represent two open doors
    instead of one.

    Returns {source_path: layer_path}, or None when the bake has not been run
    (then the old full-frame behaviour is used and a warning is printed once).
    """
    global _DELTA_INDEX
    if _DELTA_INDEX is not None:
        return _DELTA_INDEX or None
    root = os.path.join(REPO_ROOT, "assets", "rendered", "vehicle")
    report_path = os.path.join(root, "delta", "delta_report.json")
    if not os.path.isfile(report_path):
        _DELTA_INDEX = {}
        return None
    index = {}
    with open(report_path) as fh:
        report = json.load(fh)
    for group in report.get("groups", {}).values():
        source_dir = os.path.join(REPO_ROOT, group["source"])
        for entry in group.get("entries", []):
            index[os.path.join(source_dir, entry["frame"])] = os.path.join(
                REPO_ROOT, entry["layer"])
    _DELTA_INDEX = index
    return index or None


def state_layer_path(path):
    """The delta layer for a state frame, or the frame itself when unavailable."""
    global _DELTA_WARNED
    index = delta_index()
    if index is None:
        if not _DELTA_WARNED:
            _DELTA_WARNED = True
            print("[preview] warning: no baked delta layers; state renders will "
                  "be composited as whole cars (open panels can be repainted "
                  "closed by a later layer). Run "
                  "tools/assets/bake_vehicle_deltas.py")
        return path
    mapped = index.get(path)
    if mapped and os.path.isfile(mapped):
        return mapped
    if mapped is None and not _DELTA_WARNED:
        _DELTA_WARNED = True
        print(f"[preview] warning: {os.path.basename(path)} has no baked layer")
    return path


def draw_vehicle_visual(img, node, state, provider, t_norm,
                        vehicle_image=None, vehicle_crop=False):
    x, y = node.get("x", 0), node.get("y", 0)
    w, h = node.get("width", 356), node.get("height", 236)
    if vehicle_image:
        # A/B checkpoint mode: composite a rendered vehicle instead of the
        # provider asset. Aspect ratio is preserved inside the node box.
        veh = Image.open(vehicle_image).convert("RGBA")
        if vehicle_crop:
            # Trim the transparent margin so the node box maps to the car
            # itself. Without this the placement maths depends on however much
            # empty space the render happened to contain.
            bbox = veh.getchannel("A").getbbox()
            if bbox:
                veh = veh.crop(bbox)
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
    contract = moving_lighting_contract()
    covered = set()
    for panel_id, part in node.get("parts", {}).items():
        paths, took = panel_lighting_frames(
            provider, panel_id, part["sequence"], part.get("bind"), state,
            t_norm, contract)
        covered |= took
        for path in paths:
            # Base + per-state deltas: a layer carries only what its state
            # changes, so it can never repaint another panel to closed.
            paste_scaled(img, state_layer_path(path), x, y, w, h)
    for ov in node.get("overlays", []):
        sig = state.signal(ov["bind"]) if ov.get("bind") else Signal(True, True)
        if not (sig.valid and sig.value):
            continue
        path = resolve_asset_path(provider, ov["asset"])
        if path and os.path.isfile(path):
            paste_scaled(img, state_layer_path(path), x, y, w, h)
    for side, part in node.get("indicators", {}).items():
        # A channel already delivered by a moving panel's own lighting variant
        # must not be drawn again at the closed-position location.
        if (side == "left" and "INDICATOR_LEFT" in covered) or \
           (side == "right" and "INDICATOR_RIGHT" in covered):
            continue
        path = sequence_frame(provider, part["sequence"], part.get("bind"),
                              state, t_norm)
        if path:
            paste_scaled(img, state_layer_path(path), x, y, w, h)


def apply_safe_area(img, canvas):
    safe = canvas.get("safe_area", {})
    top = int(safe.get("top_corner_cut", 0))
    bottom = int(safe.get("bottom_corner_cut", 0))
    if top <= 0 and bottom <= 0:
        return img
    d = ImageDraw.Draw(img)
    w, h = img.size
    mask = hex_to_rgb(canvas.get("mask_color", "#000000"))
    d.polygon([(0, 0), (top, 0), (bottom, h), (0, h)], fill=mask)
    d.polygon([(w, 0), (w - top, 0), (w - bottom, h), (w, h)],
              fill=mask)
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
           banner=None, vehicle_image=None, vehicle_crop=False):
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
                                vehicle_image, vehicle_crop)
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
    ap.add_argument("--vehicle-image-for", action="append", default=[],
                    help="per-state vehicle render, STATE=PATH. Lets one "
                         "review pass show the closed car in every state and "
                         "the door-open render only in the door state.")
    ap.add_argument("--vehicle-crop", action="store_true",
                    help="trim the vehicle render to its alpha bbox before "
                         "fitting it into the node box")
    ap.add_argument("--out-name", default=None,
                    help="override the output filename prefix")
    ap.add_argument("--vehicle-box", default=None,
                    help="override the vehicle_visual box for this render, "
                         "format WxH@X,Y (checkpoint framing only; the scene "
                         "file itself is not modified)")
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
    vehicle_images = {}
    for item in args.vehicle_image_for:
        if "=" not in item:
            sys.exit("--vehicle-image-for must look like door_fl_open=path.png")
        key, value = item.split("=", 1)
        vehicle_images[key] = value
    default_vehicle_image = args.vehicle_image
    if args.vehicle_image or vehicle_images:
        # Checkpoint mode: the vehicle that actually gets composited is the
        # render passed on the command line, so the provider banner would be
        # describing a different asset and stamping it on a real Model 3
        # render is simply wrong.
        banner = None
        print("[preview] checkpoint mode: provider placeholder banner "
              "suppressed because an explicit vehicle render was supplied")
    print(f"[preview] vehicle source: {kind} -> {os.path.relpath(root, REPO_ROOT)}")
    if provider.warning:
        print(f"[preview] WARNING: {provider.warning}")

    states = list(MOCK_STATES) if args.all_states else [args.state]

    # Optional vehicle-box override (checkpoint framing).
    if args.vehicle_box:
        try:
            size_part, pos_part = args.vehicle_box.split("@")
            bw, bh = (int(v) for v in size_part.lower().split("x"))
            bx, by = (int(v) for v in pos_part.split(","))
        except Exception:
            sys.exit("--vehicle-box must look like 860x440@530,22")
        for node in scene["nodes"]:
            if node.get("type") == "vehicle_visual":
                node["x"], node["y"] = bx, by
                node["width"], node["height"] = bw, bh
        print(f"[preview] vehicle box override: {bw}x{bh} at ({bx},{by})")

    for name in states:
        if name not in MOCK_STATES:
            sys.exit(f"unknown state: {name} (see --list-states)")
        filename = (args.out_name or f"{scene['scene']}_{name}") + ".png"
        out = os.path.join(args.out, filename)
        vehicle_image = vehicle_images.get(name, default_vehicle_image)
        render(scene, provider, MOCK_STATES[name], out, args.t, banner,
               vehicle_image, args.vehicle_crop)
        print(f"[preview] {name:15} -> {out}")


if __name__ == "__main__":
    main()
