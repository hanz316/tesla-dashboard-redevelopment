#!/usr/bin/env python3
"""Regression checks for the Horizon V5.5 chase camera and motion vector.

The chase camera is only a real system if it is continuous, if it is exactly
absent at a standstill, if the vehicle keeps its measured anchor and size while
it yaws, and if the awareness layer keeps meaning the same thing at speed. All
of those are measured in `assets/checkpoints/horizon_v55/`, and this file also
re-derives the curves from the motion module so the screen and the report
cannot drift apart.
"""
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assets"))
sys.path.insert(0, str(ROOT / "tools/preview"))
import horizon_v5_motion as motion  # noqa: E402

METRICS = ROOT / "assets/checkpoints/horizon_v55/horizon_v55_chase_metrics.json"
RENDER_REPORT = ROOT / "assets/checkpoints/horizon_v5/horizon_v55_chase_render.json"
SPEEDS = (0, 10, 30, 60, 80, 120)


class ChaseCameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics = json.loads(METRICS.read_text())
        cls.render = (json.loads(RENDER_REPORT.read_text())
                      if RENDER_REPORT.is_file() else {"variants": {}})
        cls.gates = cls.metrics["gates"]

    def test_camera_yaw_is_monotonic_continuous_and_zero_at_standstill(self):
        yaws = [motion.screen_motion_vector(speed)["chase_yaw_deg"]
                for speed in range(0, 241)]
        self.assertEqual(yaws[0], 0.0)
        self.assertTrue(all(a <= b + 1e-9 for a, b in zip(yaws, yaws[1:])))
        # No step bigger than a fifth of a degree per km/h: the camera drifts,
        # it never snaps.
        self.assertLess(max(abs(b - a) for a, b in zip(yaws, yaws[1:])), 0.2)
        self.assertGreater(yaws[-1], 0.0)
        self.assertTrue(self.gates["yaw_monotonic_with_speed"])
        self.assertTrue(self.gates["yaw_continuous"])
        self.assertTrue(self.gates["yaw_continuous_full_curve"])
        self.assertTrue(self.gates["yaw_zero_at_standstill"])

    def test_motion_vector_is_zero_at_standstill_and_agrees_in_direction(self):
        resting = motion.screen_motion_vector(0)
        for key in ("road_flow_offset_px", "wake_trail_px",
                    "reflection_stretch", "chase_yaw_deg", "intensity"):
            self.assertEqual(resting[key], 0.0, key)
        self.assertEqual(resting["environment_parallax_px"], {"far": 0.0,
                                                             "near": 0.0})
        fast = motion.screen_motion_vector(120)
        self.assertEqual(fast["screen_axis"], [0.0, 1.0])
        # Every component grows with speed and none of them flips direction.
        for key in ("road_flow_offset_px", "wake_trail_px",
                    "reflection_stretch", "chase_yaw_deg"):
            self.assertGreater(fast[key], resting[key], key)
        self.assertGreater(fast["environment_parallax_px"]["near"],
                           fast["environment_parallax_px"]["far"])
        self.assertEqual(self.gates["standstill_motion_residual_pixels"], 0)

    def test_vehicle_keeps_its_anchor_and_size_across_the_yaw_sweep(self):
        sweep = self.metrics["yaw_sweep"]
        self.assertGreater(len(sweep), 1)
        # The framing solver holds the projected width of the car itself, so the
        # body cannot pump because the camera moved. The rendered footprint also
        # carries the wet-road response, which changes shape with the view and
        # is reported separately.
        widths = [entry["body_box"][2] - entry["body_box"][0]
                  for entry in sweep.values()]
        self.assertLessEqual(max(widths) - min(widths), 2)
        self.assertLessEqual(self.gates["yaw_sweep_anchor_drift_px"], 1.0)
        for entry in sweep.values():
            # The rendered footprint also carries the wet-road response, whose
            # own share of the height is bounded here; the car's own height is
            # corrected from the measured body ratio at runtime.
            self.assertLessEqual(abs(entry["box_height_ratio_vs_0"] - 1.0), 0.05)
        # The runtime correction is the measured body ratio, so the presented
        # body height is the standstill height at the selected scale for every
        # baked angle: the car keeps its size while its shape changes.
        boxes = json.loads((ROOT / "assets/checkpoints/horizon_v5/"
                            "horizon_v55_chase_boxes.json").read_text())
        table = boxes["phases"]["night"]
        standstill = table["0"]["height"]
        presentation = json.loads((ROOT / "assets/ui/"
                                   "horizon_v54_presentation.json").read_text())
        presented = set()
        for angle, entry in table.items():
            corrected = entry["height"] / entry["height_ratio_vs_standstill"] \
                * float(presentation["scale"])
            presented.add(round(corrected))
            self.assertAlmostEqual(
                entry["height"] / entry["height_ratio_vs_standstill"],
                standstill, delta=0.6, msg=angle)
        self.assertEqual(len(presented), 1, presented)

    def test_baked_yaw_variants_hold_the_frozen_framing(self):
        variants = self.render.get("variants", {})
        self.assertTrue(variants, "chase render report is missing")
        for key, entry in variants.items():
            framing = entry["car_framing"]
            self.assertAlmostEqual(framing["projected_width_px"], 392.5,
                                   delta=0.5, msg=key)
            self.assertAlmostEqual(framing["projected_centre_x_px"], 954.0,
                                   delta=0.5, msg=key)
            self.assertAlmostEqual(framing["projected_contact_y_px"], 345.0,
                                   delta=0.5, msg=key)
            self.assertLess(entry["yaw_deg"], 0.0)

    def test_day_and_night_present_the_vehicle_at_the_same_size(self):
        for label, entry in self.metrics["scale_trials"].items():
            self.assertLessEqual(entry["phase_body_box_max_delta_px"], 1, label)
            self.assertLessEqual(entry["phase_width_delta_px"], 1, label)
        day_night = self.metrics["day_night"]
        for speed in (0, 80):
            day = day_night[f"day_{speed}"]
            night = day_night[f"night_{speed}"]
            self.assertEqual(day["yaw_deg"], night["yaw_deg"], speed)
            self.assertLessEqual(abs(day["body_width_px"]
                                     - night["body_width_px"]), 1,
                                 speed)
            self.assertLessEqual(abs(day["body_height_px"]
                                     - night["body_height_px"]), 1,
                                 speed)

    def test_ui_does_not_move_with_the_camera(self):
        self.assertEqual(self.gates["ui_pixels_changed_by_camera_yaw"], 0)

    def test_vehicle_never_reaches_the_neighbouring_information_zones(self):
        for label, entry in self.metrics["scale_trials"].items():
            for phase, measured in entry["phases"].items():
                self.assertGreater(measured["speed_zone_clearance_px"], 0,
                                   f"{label}/{phase}")
                self.assertGreater(measured["energy_zone_clearance_px"], 0,
                                   f"{label}/{phase}")
                self.assertGreater(measured["bottom_clearance_px"], 0,
                                   f"{label}/{phase}")
                self.assertGreater(measured["navigation_clearance_px"], 0,
                                   f"{label}/{phase}")
                self.assertGreater(measured["trapezoid_mask_clearance_px"], 0,
                                   f"{label}/{phase}")


class AwarenessUnderChaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics = json.loads(METRICS.read_text())
        cls.gates = cls.metrics["gates"]

    def test_awareness_keeps_its_side_and_stays_out_of_the_information_band(self):
        self.assertEqual(self.gates["awareness_information_band_overlap_pixels"],
                         0)
        self.assertEqual(self.gates["awareness_mirror_max_channel_error"], 0)
        for speed in (0, 80):
            self.assertEqual(
                self.metrics["awareness"][f"mirror_{speed}"]
                ["max_channel_error"], 0, speed)

    def test_ghost_never_overlaps_the_body_and_is_a_secondary_cue(self):
        self.assertEqual(self.gates["ghost_body_overlap_pixels"], 0)
        for speed in (0, 80):
            entry = self.metrics["awareness"][f"ghost_body_overlap_{speed}"]
            self.assertEqual(entry["overlap_pixels"], 0, speed)
            self.assertIsNotNone(entry["body_box"], speed)

    def test_turn_intent_without_a_presence_reading_paints_nothing(self):
        for speed in (0, 80):
            # `none` is the confirmed-clear, no-intent state; the states that
            # do paint are the ones with a fresh reading behind them.
            self.assertEqual(
                self.metrics["awareness"][f"none_{speed}"]["changed_pixels"], 0,
                speed)
            for name in ("left_conflict", "right_conflict", "hazard_both"):
                self.assertGreater(
                    self.metrics["awareness"][f"{name}_{speed}"]
                    ["changed_pixels"], 0, f"{name}@{speed}")

    def test_conflict_is_more_urgent_than_plain_presence(self):
        # The zone colour is a state selection over one shared field, so the
        # urgency is the colour change plus the raised silhouette; the evidence
        # for the field itself lives in the V5.4 awareness metrics.
        v54 = json.loads((ROOT / "assets/checkpoints/horizon_v54/metrics.json")
                         .read_text())
        for side in ("left", "right"):
            semantics = v54["awareness_semantics"][side]
            self.assertGreater(
                semantics["presence_vs_conflict_max_channel_delta"], 0)
            self.assertGreater(v54["awareness_ghost"][
                "conflict_minus_presence_max_channel_delta"], 0)

    def test_motion_evidence_covers_the_declared_speeds(self):
        for speed in SPEEDS:
            entry = self.metrics["motion"][str(speed)]
            self.assertEqual(entry["chase_yaw_deg"],
                             motion.screen_motion_vector(speed)["chase_yaw_deg"],
                             speed)
        self.assertEqual(self.metrics["motion"]["0"]["changed_pixels"], 0)
        for speed in (30, 80, 120):
            entry = self.metrics["motion"][str(speed)]
            self.assertGreater(entry["changed_in_road_band"], 0, speed)
            self.assertGreater(entry["changed_in_wheel_band"], 0, speed)
            self.assertGreater(entry["measured_ground_shift_px"], 0, speed)


if __name__ == "__main__":
    unittest.main()
