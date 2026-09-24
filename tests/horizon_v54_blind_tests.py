#!/usr/bin/env python3
"""Regression checks for the semantic blind-zone layer and its evidence."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BlindZoneEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics = json.loads((ROOT / "assets/checkpoints/horizon_v54/metrics.json").read_text())
        cls.scene = json.loads((ROOT / "scenes/horizon_v5.scene").read_text())

    def test_matrix_has_none_left_right_both_and_attention_combinations(self):
        matrix = self.metrics["blind_zone"]
        self.assertEqual(set(matrix), {"none", "left", "right", "both", "left_indicator", "right_indicator"})
        self.assertEqual(matrix["none"]["changed_pixels"], 0)
        self.assertTrue(matrix["left_indicator"]["indicator_attention"])
        self.assertTrue(matrix["right_indicator"]["indicator_attention"])

    def test_left_right_are_symmetric_and_bounded(self):
        matrix = self.metrics["blind_zone"]
        self.assertLessEqual(abs(matrix["left"]["changed_pixels"] - matrix["right"]["changed_pixels"]), 100)
        for name in ("left", "right", "both", "left_indicator", "right_indicator"):
            self.assertEqual(matrix[name]["left_safe_zone_overlap_pixels"], 0)
            self.assertEqual(matrix[name]["right_safe_zone_overlap_pixels"], 0)

    def test_scene_uses_baked_assets_and_semantic_bindings(self):
        nodes = {node["id"]: node for node in self.scene["nodes"]}
        for side in ("left", "right"):
            for role in ("ghost", "peripheral"):
                rules = nodes[f"blind.{side}.{role}"]["alpha_when"]
                bindings = {rule["when"].get("signal") for rule in rules}
                self.assertIn(f"blind_{side}", bindings)
            self.assertNotIn("blur", nodes[f"blind.{side}.ghost"])


if __name__ == "__main__":
    unittest.main()
