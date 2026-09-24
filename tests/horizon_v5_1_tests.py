#!/usr/bin/env python3
"""Objective checks for Horizon V5.1: motion, and later the daylight system.

The review's rule is that a motion effect may not switch on. Every channel is
therefore checked for continuity (sampled every km/h, no step), monotonicity
(the evidence numbers must increase with speed) and the two hard anchors: no
wake and no wheel blur at 0 km/h.

Usage:
    python3 tests/horizon_v5_1_tests.py
"""

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools", "assets"))
LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v5_layout.json")
SCENE = os.path.join(REPO, "scenes", "horizon_v5.scene")
MOTION = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                      "horizon_v5_1_motion_metrics.json")
ASSETS = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                      "horizon_v5_motion_assets.json")
ENVIRONMENT = os.path.join(REPO, "assets", "ui", "horizon_v5_environment.json")
METRICS = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                       "horizon_v5_1_metrics.json")

FAILURES = []


def check(condition, label):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILURES.append(label)
    return condition


def main():
    import horizon_v5_motion as motion

    print("motion curves")
    for name in motion.CHANNELS:
        values = [motion.channel(name, speed / 2.0) for speed in range(0, 481)]
        steps = [abs(values[index + 1] - values[index])
                 for index in range(len(values) - 1)]
        check(max(steps) < 0.02,
              f"{name} is continuous: the largest step between half-km/h "
              f"samples is {max(steps):.4f}")
        monotone = all(values[index] <= values[index + 1] + 1e-9
                       for index in range(len(values) - 1))
        check(monotone, f"{name} never decreases with speed")
        check(all(0.0 <= value <= 1.0 for value in values),
              f"{name} stays inside [0, 1]")
    check(motion.channel("aero_wake_level", 0.0) == 0.0,
          "the aerodynamic wake is exactly zero at 0 km/h")
    check(motion.channel("wheel_motion_level", 0.0) == 0.0,
          "the wheel motion is exactly zero at 0 km/h")
    for speed in (0, 30, 80, 120):
        row = motion.levels(speed)
        print(f"  note {speed:3d} km/h -> wheel {row['wheel_motion_level']:.2f}"
              f" flow {row['road_flow_level']:.2f}"
              f" streak {row['wet_streak_level']:.2f}"
              f" wake {row['aero_wake_level']:.2f}"
              f" micro {row['micro_motion_amplitude_px']:.2f} px")

    print("wheel level windows")
    windows = motion.opacity_windows()
    for speed in (0, 15, 30, 55, 80, 100, 120, 200):
        total = sum(_interp(points, speed) for points in windows.values())
        expected = 0.0 if speed == 0 else (1.0 if speed >= 30 else None)
        if expected is not None:
            check(abs(total - expected) < 1e-6,
                  f"at {speed} km/h the baked wheel weights sum to {total:.3f}")
        else:
            check(0.0 < total < 1.0,
                  f"at {speed} km/h the baked wheel weights blend ({total:.3f})")

    print("layout wiring")
    scene = json.load(open(SCENE))
    nodes = {node["id"]: node for node in scene["nodes"]}
    for node_id in ("motion.roadflow", "motion.wake", "motion.streak.brake",
                    "motion.streak.indicator_left",
                    "motion.streak.indicator_right",
                    "motion.wheel.low", "motion.wheel.medium",
                    "motion.wheel.high"):
        check(node_id in nodes, f"{node_id} exists")
    check("micro_motion" in nodes.get("vehicle.base", {}),
          "the vehicle layer carries bounded micro motion")
    wake = nodes.get("motion.wake", {})
    check(wake.get("opacity_from", {}).get("points", [[None, 1]])[0][1] == 0.0,
          "the wake node's own curve starts at zero opacity")
    for node_id, node in nodes.items():
        if not node_id.startswith("motion."):
            continue
        check(not any(key in json.dumps(node).lower()
                      for key in ("blur", "particle", "shader")),
              f"{node_id} uses only baked assets and value-driven transforms")

    print("measured evidence")
    if os.path.isfile(MOTION):
        report = json.load(open(MOTION))
        check(report["monotone_increasing"],
              "motion intensity measured from pixels rises 0 < 30 < 80 < 120")
        check(report["zero_at_0_kmh"],
              "0 km/h measures exactly zero wheel and wake difference")
        check(report["streak_monotone_increasing"],
              "the taillight's wet-road streak length rises with speed")
        for speed, row in sorted(report["per_speed"].items(),
                                 key=lambda item: int(item[0])):
            print(f"  note {speed:>3} km/h  wheel "
                  f"{row['wheel_region_mean_diff']:.2f}  wake "
                  f"{row['wake_region_mean_diff']:.2f}  flow "
                  f"{row['roadflow_region_mean_diff']:.2f}")
        check(os.path.isfile(os.path.join(REPO, report["comparison"])),
              "the motion comparison sheet exists")
    else:
        print("  note the motion evidence has not been generated in this "
              "checkout (run tools/preview/horizon_v5_motion_evidence.py)")

    if not os.path.isfile(ASSETS):
        print("  note the motion asset report is not in this checkout")

    print("environment time system")
    import horizon_v5_environment_time as environment_time
    profile = environment_time.monthly_profile()
    check(len(profile) == 12, "the regional profile covers 12 months")
    check(all(entry["sunrise_minutes"] < entry["sunset_minutes"]
              for entry in profile.values()),
          "every month has sunrise before sunset")
    january = profile["01"]["sunrise_minutes"]
    july = profile["07"]["sunrise_minutes"]
    check(january > july,
          f"January sunrise ({january / 60:.2f} h) is later than July "
          f"({july / 60:.2f} h)")
    check(profile["01"]["sunset_minutes"] < profile["07"]["sunset_minutes"],
          "January sunset is earlier than July")
    check(profile["04"]["sunrise_minutes"] < profile["01"]["sunrise_minutes"]
          and profile["04"]["sunrise_minutes"] > july,
          "April sits between winter and summer")
    calculated = environment_time.schedule(
        2026, 7, 15, latitude=43.70, longitude=-79.40)
    check(abs(calculated["sunrise_minutes"]
              - profile["07"]["sunrise_minutes"]) < 20,
          "the calculated sunrise agrees with the regional profile inside 20 "
          "minutes")
    check(calculated["source"] == "calculated"
          and environment_time.schedule(2026, 7, 15)["source"]
          == "monthly_regional_profile",
          "the schedule reports which fallback tier it used")

    # One minute of samples through both windows: no step in the weights and no
    # step in the interpolated palette. This is the 17:59/18:00 failure the
    # review names, expressed as a number.
    worst_weight = 0.0
    worst_palette = 0.0
    sunrise = environment_time.schedule(2026, 9, 24)["sunrise_minutes"]
    sunset = environment_time.schedule(2026, 9, 24)["sunset_minutes"]
    for centre in (sunrise, sunset):
        previous_weights = None
        previous_palette = None
        for minute in range(int(centre) - 120, int(centre) + 121):
            weights = environment_time.phase_weights(minute, sunrise, sunset)
            palette = environment_time.palette(weights)
            check_sum = abs(sum(weights.values()) - 1.0)
            if check_sum > 1e-6:
                check(False, f"the phase weights sum to one at minute {minute}")
                break
            if previous_weights is not None:
                worst_weight = max(worst_weight,
                                   max(abs(weights[name] - previous_weights[name])
                                       for name in weights))
                worst_palette = max(worst_palette,
                                    _palette_step(previous_palette, palette))
            previous_weights = weights
            previous_palette = palette
    # smoothstep's maximum slope is 1.5 per window, so the per-minute bound is
    # 1.5/window_minutes; 105 minutes gives 0.0143.
    check(worst_weight < 0.02,
          f"the largest phase-weight change over one minute is "
          f"{worst_weight:.4f} (bound 1.5/window = 0.0143)")
    check(worst_palette <= 4.0,
          f"the largest palette change over one minute is {worst_palette:.1f} "
          f"of 255")
    night_palette = environment_time.palette({"night": 1.0, "dawn": 0.0,
                                              "day": 0.0, "dusk": 0.0})
    day_palette = environment_time.palette({"night": 0.0, "dawn": 0.0,
                                            "day": 1.0, "dusk": 0.0})
    check(night_palette["primary_text"]
          == environment_time.PALETTES["night"]["primary_text"]
          and day_palette["primary_text"]
          == environment_time.PALETTES["day"]["primary_text"],
          "the palette endpoints are exactly the phase palettes")
    semantic = environment_time.SEMANTIC_COLOURS
    check(all(palette[name] == value for name, value in semantic.items()
              for palette in (night_palette, day_palette)),
          "brake red, indicator amber and ready green keep their meaning in "
          "every phase")

    print("environment evidence")
    if os.path.isfile(METRICS):
        metrics = json.load(open(METRICS))
        for label, entry in metrics["transition_continuity"].items():
            # A switch would be one step equal to the whole transition. The
            # contract is that no single 2-minute sample covers more than a
            # tenth of it, which the smoothstep windows satisfy by construction.
            fraction = entry["max_step_fraction_of_transition"]
            check(fraction <= 0.10,
                  f"the {label} transition's largest 2-minute step is "
                  f"{fraction:.3f} of the whole transition "
                  f"({entry['max_frame_mean_difference']} of 255)")
            check(entry["max_palette_step"] <= 10.0,
                  f"the {label} palette step stays at "
                  f"{entry['max_palette_step']} of 255 per 2 minutes")
        # WCAG: 3:1 for large text and for graphics, 4.5:1 for small text. The
        # primary readouts are 58-98 px, the labels are 16-22 px, the arc and
        # the rail are graphics.
        for name, entry in metrics["daylight_contrast"].items():
            floor = 4.5 if name in ("muted_text", "dim_text") else 3.0
            check(entry["min_ratio"] >= floor,
                  f"daylight contrast for {name} is {entry['min_ratio']}:1 "
                  f"(floor {floor})")
        memory = metrics["memory"]
        check(memory["two_plate_transition_bytes"]
              == memory["plate_rgba_bytes"] * 2,
              "a transition holds exactly two environment plates")
        check(memory["resident_estimate_mb"] < 24.0,
              f"the resident estimate is {memory['resident_estimate_mb']} MB, "
              f"inside the budget for a 250 MB device")
        months = [row["sunrise_h"] for row in metrics["seasons"]]
        check(months[0] > months[2],
              f"the seasonal frames keep winter sunrise ({months[0]} h) later "
              f"than summer ({months[2]} h)")
    else:
        print("  note the environment evidence has not been generated in this "
              "checkout (run tools/preview/horizon_v5_environment_evidence.py)")
    print("")
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for failure in FAILURES:
            print(f"  {failure}")
        return 1
    print("all horizon v5.1 motion checks passed")
    return 0


def _palette_step(left, right):
    worst = 0.0
    for name, value in left.items():
        other = right.get(name, value)
        for index in (1, 3, 5):
            worst = max(worst, abs(int(value[index:index + 2], 16)
                                   - int(other[index:index + 2], 16)))
    return worst


def _interp(points, value):
    if value <= points[0][0]:
        return float(points[0][1])
    if value >= points[-1][0]:
        return float(points[-1][1])
    for index in range(len(points) - 1):
        low, high = points[index], points[index + 1]
        if low[0] <= value <= high[0]:
            span = float(high[0] - low[0]) or 1.0
            t = (value - low[0]) / span
            return float(low[1]) + (float(high[1]) - float(low[1])) * t
    return float(points[-1][1])


if __name__ == "__main__":
    sys.exit(main())
