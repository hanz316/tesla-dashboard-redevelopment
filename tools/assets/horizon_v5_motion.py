#!/usr/bin/env python3
"""VehicleMotionVisualSystem: what the car does when it is moving.

The reference shot is a parked car in a night scene. A driving car needs motion
that *means* something, and the review is explicit about how: continuous curves
with anchors, no thresholds and no sudden switching, every effect bounded and
deterministic, and nothing that the device cannot afford.

This module is the single definition of those curves. The layout builder, the
asset baker, the tests and the evidence all read it, so the numbers on screen
and the numbers in the report cannot drift apart.

Channels
--------
  wheel_motion_level        baked wheel-spin blend weight
  road_flow_level           wet-road streak translation rate + opacity
  wet_streak_level          taillight / indicator reflection length on the road
  aero_wake_level           cyan airflow trail behind the car (0 at 0 km/h)
  micro_motion_level        vehicle body vertical micro motion (<= 2 px)

Every channel is a monotone piecewise-smooth function of speed with anchors at
0, 30, 80 and 120 km/h, evaluated with smoothstep between anchors so the first
derivative is continuous at the anchors as well as inside the segments.

Usage:
    python3 tools/assets/horizon_v5_motion.py --levels
    python3 tools/assets/horizon_v5_motion.py --json assets/ui/horizon_v5_motion.json
"""

import argparse
import json
import math
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(REPO, "assets", "ui", "horizon_v5_motion.json")

# anchor speeds in km/h, shared by every channel
SPEEDS = [0.0, 30.0, 80.0, 120.0]

CHANNELS = {
    "wheel_motion_level": [0.0, 0.35, 0.70, 1.0],
    "road_flow_level": [0.0, 0.30, 0.75, 1.0],
    "wet_streak_level": [0.0, 0.30, 0.70, 1.0],
    # The wake is the only channel that is exactly zero until the car is
    # actually moving: 0 km/h must show no airflow at all.
    "aero_wake_level": [0.0, 0.05, 0.45, 1.0],
    "micro_motion_level": [0.0, 0.30, 0.60, 1.0],
}

# Bounded, in pixels. The body never floats or bounces: 2 px at 120 km/h.
MICRO_MOTION_AMPLITUDE_PX = 2.0
MICRO_MOTION_HZ = 0.55

# Baked wheel spin levels: the arc the wheel sweeps during one exposure.
# Three baked wheel levels. There is no "still" asset: at 0 km/h every wheel
# overlay is transparent and the car's own sharp wheel is what shows.
WHEEL_LEVELS = [("low", 22.0), ("medium", 70.0), ("high", 190.0)]
WHEEL_ANCHOR_SPEEDS = [30.0, 80.0, 120.0]

# Road flow: how far the streak texture travels across the panel per second of
# travel, expressed so the runtime only has to translate and wrap.
ROAD_FLOW_PX_PER_LEVEL = 190.0

# Speed at which the vehicle silhouette is used for state selection etc.
SPEED_MAX = 240.0


def smoothstep(edge0, edge1, value):
    if edge1 <= edge0:
        return 0.0 if value < edge0 else 1.0
    t = min(1.0, max(0.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def channel(name, speed):
    """Piecewise smooth interpolation between the anchors for one channel."""
    values = CHANNELS[name]
    if speed <= SPEEDS[0]:
        return values[0]
    if speed >= SPEEDS[-1]:
        return values[-1]
    for index in range(len(SPEEDS) - 1):
        low, high = SPEEDS[index], SPEEDS[index + 1]
        if low <= speed <= high:
            blend = smoothstep(low, high, speed)
            return values[index] + (values[index + 1] - values[index]) * blend
    return values[-1]


def levels(speed):
    """Every motion level for one speed, plus the derived offsets."""
    wheel = channel("wheel_motion_level", speed)
    # Which two baked wheel levels blend, and how much of the upper one.
    scaled = wheel * (len(WHEEL_LEVELS) - 1) if WHEEL_LEVELS else 0.0
    lower = max(0, min(int(math.floor(scaled)), len(WHEEL_LEVELS) - 2))
    fraction = scaled - lower
    flow = channel("road_flow_level", speed)
    micro = channel("micro_motion_level", speed)
    return {
        "speed": float(speed),
        "wheel_motion_level": round(wheel, 4),
        "wheel_blend": {"lower": WHEEL_LEVELS[lower][0],
                        "upper": WHEEL_LEVELS[lower + 1][0],
                        "fraction": round(fraction, 4)},
        "road_flow_level": round(flow, 4),
        "road_flow_offset_px": round(flow * ROAD_FLOW_PX_PER_LEVEL, 2),
        "wet_streak_level": round(channel("wet_streak_level", speed), 4),
        "wet_streak_length_px": round(
            channel("wet_streak_level", speed) * 1.0, 4),
        "aero_wake_level": round(channel("aero_wake_level", speed), 4),
        "micro_motion_level": round(micro, 4),
        "micro_motion_amplitude_px": round(micro * MICRO_MOTION_AMPLITUDE_PX, 3),
        "motion_factor": round(smoothstep(0.0, 120.0, speed), 4),
    }


def opacity_windows():
    """One triangular window per baked wheel level.

    The windows sum to 1 from 30 km/h upward and to 0 at 0 km/h, so the sharp
    wheel the car render already contains is what a parked car shows, and two
    baked levels crossfade continuously at every speed in between.
    """
    windows = {}
    for index, (name, _degrees) in enumerate(WHEEL_LEVELS):
        speed = WHEEL_ANCHOR_SPEEDS[index]
        low = WHEEL_ANCHOR_SPEEDS[index - 1] if index > 0 else 0.0
        high = (WHEEL_ANCHOR_SPEEDS[index + 1]
                if index + 1 < len(WHEEL_ANCHOR_SPEEDS) else SPEED_MAX)
        windows[name] = [[low, 0.0 if index > 0 else 0.0],
                         [speed, 1.0],
                         [high, 0.0 if index + 1 < len(WHEEL_ANCHOR_SPEEDS)
                          else 1.0]]
    return windows


def definition():
    steps = [levels(speed) for speed in (0, 5, 10, 15, 20, 30, 50, 80, 100,
                                         120, 160, 200, 240)]
    return {
        "schema": "horizon-v5-motion v1",
        "why": "the car has to read as driving, and every motion channel has to "
               "be a continuous bounded function of speed rather than a "
               "threshold, so nothing ever flashes on",
        "anchor_speeds_kmh": SPEEDS,
        "channels": CHANNELS,
        "interpolation": "smoothstep inside each segment, evaluated at the "
                         "anchors, so the value and its first derivative are "
                         "continuous",
        "wheel_levels": [{"name": name, "spin_deg": degrees}
                         for name, degrees in WHEEL_LEVELS],
        "wheel_opacity_windows": opacity_windows(),
        "micro_motion": {"amplitude_px": MICRO_MOTION_AMPLITUDE_PX,
                         "hz": MICRO_MOTION_HZ,
                         "why": "1-2 px of vertical body motion at speed; no "
                                "spring, no bounce, no floating"},
        "road_flow": {"px_per_level": ROAD_FLOW_PX_PER_LEVEL,
                      "why": "the streak texture only translates and wraps; the "
                             "device never blurs or synthesises anything"},
        "levels_at_speeds": steps,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=OUT)
    parser.add_argument("--levels", action="store_true")
    parser.add_argument("--speed", type=float, default=None)
    args = parser.parse_args()
    if args.levels or args.speed is not None:
        speeds = [args.speed] if args.speed is not None else [0, 30, 80, 120]
        for speed in speeds:
            print(json.dumps(levels(speed)))
        return 0
    document = definition()
    with open(args.json, "w") as handle:
        json.dump(document, handle, indent=1)
        handle.write("\n")
    print(f"[v5-motion] channels {list(CHANNELS)}")
    for speed in (0, 30, 80, 120):
        row = levels(speed)
        print(f"[v5-motion] {speed:3d} km/h  wheel {row['wheel_motion_level']:.2f}"
              f"  flow {row['road_flow_level']:.2f}"
              f"  streak {row['wet_streak_level']:.2f}"
              f"  wake {row['aero_wake_level']:.2f}"
              f"  micro {row['micro_motion_amplitude_px']:.2f} px")
    print(f"[v5-motion] {os.path.relpath(args.json, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
