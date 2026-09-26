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
    # The chase camera is a camera behaviour, not a decoration: it starts at the
    # accepted V5.4 presentation and orbits towards the car's rear as speed
    # rises. The anchor at 30 km/h is small on purpose - the view must be
    # almost unchanged at city speed and only become obvious on a highway.
    "chase_yaw_level": [0.0, 0.18, 0.68, 1.0],
}

# Chase camera maximum, in degrees of camera orbit towards the car's rear.
# Selected from the measured sweep, not asserted: +4/+7/+10/+13/+16 were
# rendered (assets/checkpoints/horizon_v55/horizon_v55_chase_yaw_sweep.png) and
# measured (horizon_v55_yaw_selection.json). The automatic rule - the smallest
# angle clearing a third of the largest silhouette change with the anchor and
# the presented height intact - picks 7 deg; the review also requires 80 km/h to
# be clearly rear-three-quarter (0.68 of the maximum), which the sweep shows
# needs a maximum of 10 deg. 10 deg is therefore the production value, and its
# body-anchor drift is measured at 0.0 px at every baked angle.
CHASE_YAW_MAX_DEG = 10.0

# The screen motion vector: every effect that has to agree about which way the
# world is moving reads these, so the car, the road, the reflection and the wake
# can never point in different directions. The car travels away from the
# camera, so road-level detail travels towards the viewer: +y on screen.
SCREEN_MOTION_AXIS = (0.0, 1.0)
ENVIRONMENT_PARALLAX_FAR_PX = 1.0
ENVIRONMENT_PARALLAX_NEAR_PX = 7.0
WAKE_TRAIL_PX = 18.0
REFLECTION_STRETCH_MAX = 0.12

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


def screen_motion_vector(speed):
    """The one vector every motion effect is derived from.

    Direction is shared, magnitude is shared, and every component is exactly
    zero at a standstill: road flow, wake, reflection stretch and environment
    parallax cannot disagree about which way the world is moving because they
    are all reads of this structure.
    """
    intensity = smoothstep(0.0, 120.0, float(speed))
    yaw = channel("chase_yaw_level", speed) * CHASE_YAW_MAX_DEG
    return {
        "speed": float(speed),
        "intensity": round(intensity, 4),
        "screen_axis": list(SCREEN_MOTION_AXIS),
        "why": "the car travels away from the camera, so the road travels "
               "towards the viewer along +y; the wake trails the other way",
        "chase_yaw_deg": round(yaw, 3),
        "camera_azimuth_deg": round(-yaw, 3),
        "road_flow_offset_px": round(
            channel("road_flow_level", speed) * ROAD_FLOW_PX_PER_LEVEL, 2),
        "wake_trail_px": round(
            channel("aero_wake_level", speed) * WAKE_TRAIL_PX, 2),
        "reflection_stretch": round(
            channel("road_flow_level", speed) * REFLECTION_STRETCH_MAX, 4),
        "environment_parallax_px": {
            "far": round(intensity * ENVIRONMENT_PARALLAX_FAR_PX, 2),
            "near": round(intensity * ENVIRONMENT_PARALLAX_NEAR_PX, 2)},
        "wheel_motion_level": round(channel("wheel_motion_level", speed), 4),
        "wet_streak_level": round(channel("wet_streak_level", speed), 4),
    }


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
        "chase_yaw_level": round(channel("chase_yaw_level", speed), 4),
        "chase_yaw_deg": round(channel("chase_yaw_level", speed)
                               * CHASE_YAW_MAX_DEG, 3),
        "screen_motion": screen_motion_vector(speed),
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
        "screen_motion_vector": {
            "axis": list(SCREEN_MOTION_AXIS),
            "why": "one direction and one magnitude for the camera yaw, the "
                   "road flow, the wake, the reflection stretch and the "
                   "environment parallax, so they cannot disagree",
            "components": {
                "camera_yaw_deg": CHASE_YAW_MAX_DEG,
                "environment_parallax_far_px": ENVIRONMENT_PARALLAX_FAR_PX,
                "environment_parallax_near_px": ENVIRONMENT_PARALLAX_NEAR_PX,
                "wake_trail_px": WAKE_TRAIL_PX,
                "reflection_stretch": REFLECTION_STRETCH_MAX},
            "axis_convention": "the car travels away from the camera, so road "
                               "level detail travels towards the viewer (+y)"},
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
