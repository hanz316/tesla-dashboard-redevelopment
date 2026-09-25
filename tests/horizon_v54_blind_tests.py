#!/usr/bin/env python3
"""Regression checks for the peripheral Side Awareness Zone and its evidence.

The zone replaced a rejected car-shaped outline. Each side now carries one
semantic field whose colour is selected by state - green TURN ONLY, amber BLIND
PRESENCE ONLY, red SIDE CONFLICT - plus a soft secondary silhouette. These
checks hold the layer to what the evidence claims: the colour is a state
selection over one shared field, nothing the layer draws reaches the
information band, the two sides mirror exactly, and unknown, stale or invented
presence never paints anything.
"""
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


def signals(condition):
    """Every signal a nested alpha_when condition reads."""
    for key in ('all', 'any'):
        if key in condition:
            found = set()
            for part in condition[key]:
                found |= signals(part)
            return found
    return {condition['signal']} if condition.get('signal') else set()


class AwarenessZoneEvidenceTests(unittest.TestCase):
    # A fresh confirmed reading for every signal the layer reads, which is what
    # the fixtures in the evidence tool carry.
    KNOWN = {'blind_left': False, 'blind_right': False,
             'indicator_left': False, 'indicator_right': False,
             'hazards': False}

    @classmethod
    def setUpClass(cls):
        cls.metrics = json.loads(
            (ROOT / "assets/checkpoints/horizon_v54/metrics.json").read_text())
        cls.scene = json.loads((ROOT / "scenes/horizon_v5.scene").read_text())
        cls.nodes = {node["id"]: node for node in cls.scene["nodes"]}
        cls.zone = cls.metrics["awareness_zone"]
        cls.layout = json.loads(
            (ROOT / "assets/ui/horizon_v5_layout.json").read_text())

    def test_matrix_covers_presence_turn_conflict_and_hazards(self):
        self.assertEqual(set(self.zone), {
            "none", "left_presence", "right_presence", "both_presence",
            "left_turn", "right_turn", "left_conflict", "right_conflict",
            "hazards_clear", "hazards_conflict", "left_turn_unconfirmed"})
        self.assertEqual(self.zone["none"]["changed_pixels"], 0)
        for name, semantic in (("left_presence", "left/amber"),
                               ("right_presence", "right/amber"),
                               ("both_presence", "both/amber"),
                               ("left_turn", "left/green"),
                               ("right_turn", "right/green"),
                               ("left_conflict", "left/red"),
                               ("right_conflict", "right/red"),
                               ("hazards_clear", "both/green"),
                               ("hazards_conflict", "both/red")):
            self.assertEqual(self.zone[name]["semantic"], semantic, name)
            self.assertGreater(self.zone[name]["changed_pixels"], 0, name)
        # A one-sided state may only paint its own side.
        for name in ("left_presence", "left_turn", "left_conflict",
                     "right_presence", "right_turn", "right_conflict"):
            entry = self.zone[name]
            self.assertEqual(entry["opposite_side_zone_leak_pixels"], 0, name)
            self.assertEqual(entry["own_side_zone_pixels"],
                             entry["changed_pixels"], name)

    def test_no_state_reaches_the_information_band(self):
        for name, entry in self.zone.items():
            self.assertEqual(entry["information_band_overlap_pixels"], 0, name)
        # Turn intent with no presence reading does not claim a clear side.
        unconfirmed = self.zone["left_turn_unconfirmed"]
        self.assertEqual(unconfirmed["semantic"], "suppressed")
        self.assertEqual(unconfirmed["changed_pixels"], 0)
        band_left, band_right = self.metrics["information_band_px"]
        declared = [zone["x"] for zone in self.layout["zones"].values()]
        right_edges = [zone["right"] for zone in self.layout["zones"].values()]
        self.assertEqual(band_left, min(declared))
        self.assertEqual(band_right, max(right_edges))
        columns = self.metrics["awareness_zone_columns"]
        self.assertLessEqual(columns["left"][1], band_left)
        self.assertGreaterEqual(columns["right"][0], band_right)

    def test_symmetry_suppression_and_asset_semantics(self):
        self.assertEqual(self.metrics["awareness_symmetry_max_channel_error"], 0)
        for label, delta in self.metrics[
                "awareness_suppression_max_channel_delta"].items():
            self.assertEqual(delta, 0, label)
        for side in ("left", "right"):
            asset = self.metrics["awareness_assets"][side]
            # One field, three colours: the geometry is shared, the meaning is
            # not, and the two sides are exact mirrors.
            self.assertTrue(asset["alpha_equal_across_colours"], side)
            self.assertGreater(asset["colour_min_channel_separation"], 0, side)
            self.assertEqual(asset["mirror_max_channel_error"], 0, side)
        ghost = self.metrics["awareness_assets"]["ghost"]
        self.assertEqual(ghost["mirror_max_channel_error"], 0)
        # A silhouette with no traceable outline: no hard alpha step anywhere.
        self.assertLessEqual(ghost["max_alpha_gradient"], 12)
        for side in ("left", "right"):
            semantics = self.metrics["awareness_semantics"][side]
            self.assertGreater(semantics["presence_vs_conflict_max_channel_delta"], 0)
            self.assertGreater(semantics["presence_vs_turn_max_channel_delta"], 0)
            self.assertEqual(
                semantics["opposite_turn_repaints_present_side_pixels"], 0, side)
            self.assertGreater(
                semantics["opposite_turn_paints_other_side_pixels"], 0, side)
            # Presence and conflict share one field, so their supports may only
            # differ where the faint fringe falls under the measurement
            # threshold - never as a different shape.
            self.assertGreaterEqual(
                semantics["presence_vs_conflict_support_overlap_ratio"],
                0.9, side)

    def test_ghost_stays_a_soft_secondary_cue(self):
        ghost = self.metrics["awareness_ghost"]
        self.assertGreater(ghost["presence"]["changed_pixels"], 0)
        self.assertEqual(ghost["presence"]["other_side_changed_pixels"], 0)
        self.assertEqual(ghost["conflict"]["other_side_changed_pixels"], 0)
        self.assertGreater(ghost["conflict_minus_presence_max_channel_delta"], 0)
        for side in ("left", "right"):
            self.assertNotIn("blur", self.nodes[f"awareness.{side}.ghost"])

    def test_scene_uses_baked_zone_assets_and_semantic_bindings(self):
        roles = {component["id"]: component.get("role")
                 for component in self.layout["components"]}
        for side in ("left", "right"):
            other = "right" if side == "left" else "left"
            for role in ("green", "amber", "red"):
                node = self.nodes[f"awareness.{side}.{role}"]
                self.assertEqual(roles[f"awareness.{side}.{role}"], "awareness")
                self.assertTrue((ROOT / node["src"]).is_file(), node["src"])
                with Image.open(ROOT / node["src"]) as bitmap:
                    self.assertEqual([bitmap.width, bitmap.height],
                                     [node["width"], node["height"]])
                found = set()
                for rule in node["alpha_when"]:
                    found |= signals(rule["when"])
                if role == "green":
                    self.assertIn(f"indicator_{side}", found, role)
                    self.assertIn(f"blind_{side}", found, role)
                else:
                    self.assertIn(f"blind_{side}", found, role)
                if role == "red":
                    self.assertIn(f"indicator_{side}", found, role)
                if role == "amber":
                    # Blind presence alone must not be read from the other side.
                    self.assertNotIn(f"blind_{other}", found, role)

    def test_live_pixels_suppression_semantics_and_sides(self):
        awareness = [node for node in self.scene['nodes']
                     if node['id'].startswith('awareness.')]
        scene = dict(self.scene, nodes=awareness)
        # The colour-vs-geometry claim belongs to the zone field, so it is
        # measured without the secondary silhouette.
        zones = dict(self.scene, nodes=[node for node in awareness
                                        if not node['id'].endswith('.ghost')])
        with tempfile.TemporaryDirectory() as tmp:
            def pixels(state, target=None):
                path = str(Path(tmp) / 'frame.png')
                preview.render(target or scene, None, state, path)
                return np.asarray(Image.open(path)).astype(int)

            def known(**extra):
                return dict(self.KNOWN, **extra)

            def without(*keys):
                state = dict(self.KNOWN)
                for key in keys:
                    state.pop(key)
                return state

            neutral = pixels(known())
            zone_neutral = pixels(known(), zones)
            for value in ({'value': True, 'valid': False},
                          {'value': True, 'valid': True, 'stale': True}, False):
                self.assertTrue(np.array_equal(
                    neutral, pixels(known(blind_left=value))))
            # Same rule for turn intent: with no presence reading at all there
            # is no clear side to claim, so nothing is painted.
            self.assertTrue(np.array_equal(neutral, pixels(
                dict(without('blind_left'), indicator_left=True))))
            self.assertTrue(np.array_equal(neutral, pixels(
                dict(without('blind_left', 'blind_right'), hazards=True))))
            presence = pixels(known(blind_left=True))
            turn = pixels(known(indicator_left=True, blind_left=False))
            conflict = pixels(known(blind_left=True, indicator_left=True))
            together = pixels(known(blind_left=True, blind_right=True))
            right = pixels(known(blind_right=True))
            self.assertFalse(np.array_equal(neutral, presence))
            self.assertFalse(np.array_equal(presence, turn))
            self.assertFalse(np.array_equal(presence, conflict))
            # Presence and conflict share the field; the pixels change anyway.
            zone_presence = pixels(known(blind_left=True), zones)
            zone_conflict = pixels(known(blind_left=True, indicator_left=True),
                                   zones)
            support = (np.max(np.abs(zone_presence - zone_neutral), axis=2) > 5)
            other = (np.max(np.abs(zone_conflict - zone_neutral), axis=2) > 5)
            overlap = int((support & other).sum()) / max(
                1, int((support | other).sum()))
            self.assertGreaterEqual(overlap, 0.9)
            # Both sides at once is each side's own field.
            self.assertTrue(np.array_equal(together[:, :960], presence[:, :960]))
            self.assertTrue(np.array_equal(together[:, 960:], right[:, 960:]))
            # An opposite-side indicator lights the opposite side only.
            opposite = pixels(known(blind_left=True, indicator_right=True))
            self.assertTrue(np.array_equal(opposite[:, :960], presence[:, :960]))
            self.assertFalse(np.array_equal(opposite[:, 960:], neutral[:, 960:]))
            # The two sides are mirrors of each other in the renderer, not just
            # in the artwork.
            left_delta = presence - neutral
            right_delta = (right - neutral)[:, ::-1]
            self.assertEqual(int(np.abs(left_delta - right_delta).max()), 0)


if __name__ == "__main__":
    unittest.main()
