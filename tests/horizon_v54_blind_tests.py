#!/usr/bin/env python3
"""Regression checks for the semantic blind-zone layer and its evidence."""
import json
from pathlib import Path
import unittest
import tempfile
import sys
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/preview'))
import scene_preview as preview


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
        self.assertEqual(self.metrics['blind_symmetry_max_channel_error'], 0)
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

    def test_live_pixels_unknown_stale_both_and_attention(self):
        scene = dict(self.scene, nodes=[n for n in self.scene['nodes']
                                       if n['id'].startswith('blind.')])
        with tempfile.TemporaryDirectory() as tmp:
            def pixels(state):
                path = str(Path(tmp) / 'frame.png')
                preview.render(scene, None, state, path)
                return np.asarray(Image.open(path)).astype(int)
            neutral = pixels({})
            for value in ({'value': True, 'valid': False},
                          {'value': True, 'valid': True, 'stale': True}, False):
                self.assertTrue(np.array_equal(neutral, pixels({'blind_left': value})))
            left = pixels({'blind_left': True})
            right = pixels({'blind_right': True})
            both = pixels({'blind_left': True, 'blind_right': True})
            self.assertTrue(np.array_equal(both[:, :960], left[:, :960]))
            self.assertTrue(np.array_equal(both[:, 960:], right[:, 960:]))
            attentive = pixels({'blind_left': True, 'indicator_left': True})
            opposite = pixels({'blind_left': True, 'indicator_right': True})
            self.assertGreater(attentive.sum(), left.sum())
            self.assertTrue(np.array_equal(opposite, left))
            self.assertTrue(np.array_equal(pixels({'indicator_left': True}), neutral))


if __name__ == "__main__":
    unittest.main()
