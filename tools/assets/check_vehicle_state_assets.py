#!/usr/bin/env python3
"""Check the vehicle state asset set against the manifest and Horizon.

This is the gate that stops the runtime from referencing an asset that does not
exist, and the place where the composed Horizon path is costed. It reads the
same manifest and the same scene file the runtime and the previewer read.

Checks
------
* every id in assets/manifest.json resolves to a real file under the ACTIVE
  source root (and the active root is the production one, not the placeholder);
* every frame has the declared canvas;
* the Horizon scene only references ids the manifest provides;
* the composed path is costed: simultaneously decoded assets, peak RGBA,
  compositing operations per frame, and the 30/60 fps share of the frame budget.

Usage:
    python3 tools/assets/check_vehicle_state_assets.py \
        --out assets/checkpoints/vehicle_state_assets/vehicle_state_manifest_check.json
"""

import argparse
import json
import os
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "preview"))
from vehicle_asset_provider import VehicleAssetProvider  # noqa: E402

DEFAULT_MANIFEST = "assets/manifest.json"
HORIZON_SCENES = ["scenes/horizon_redesign_a.scene",
                  "scenes/horizon_redesign_b.scene",
                  "scenes/horizon_redesign_c.scene"]
# Framebuffer accounting: decoded RGBA is the runtime memory metric.
FRAME_BUDGET_MS = {30: 1000.0 / 30.0, 60: 1000.0 / 60.0}
DECODE_MS_356x236 = 6.9


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-placeholder-fallback", action="store_true",
                    help="in a checkout without the generated production "
                         "assets, verify the contract against the committed "
                         "placeholder tree and say so explicitly")
    return ap.parse_args()


def scene_asset_ids(path):
    with open(path) as fh:
        scene = json.load(fh)
    ids, sequences = set(), set()
    for node in scene.get("nodes", []):
        if node.get("type") != "vehicle_visual":
            continue
        if node.get("asset"):
            ids.add(node["asset"])
        for key in ("overlays", "states", "panels"):
            for entry in node.get(key, []) or []:
                if isinstance(entry, dict):
                    if entry.get("asset"):
                        ids.add(entry["asset"])
                    if entry.get("sequence"):
                        sequences.add(entry["sequence"])
                elif isinstance(entry, str):
                    ids.add(entry)
        for key in ("sequences", "animations"):
            for entry in node.get(key, []) or []:
                if isinstance(entry, dict) and entry.get("sequence"):
                    sequences.add(entry["sequence"])
    return sorted(ids), sorted(sequences)


def main():
    args = parse_args()
    manifest_path = os.path.join(REPO_ROOT, args.manifest)
    with open(manifest_path) as fh:
        manifest = json.load(fh)
    provider = VehicleAssetProvider(REPO_ROOT, manifest)
    production_present = provider.rendered_model3_available()
    verified_against = "RENDERED_MODEL3"
    try:
        provider.resolve(allow_placeholder=False)
    except RuntimeError:
        if not args.allow_placeholder_fallback:
            raise
        # A fresh checkout (CI) has no generated vehicle tree: it is
        # gitignored and rebuilt locally. The contract can still be verified
        # against the committed placeholder art, but the production assertions
        # must then be reported as skipped rather than passed.
        provider.resolve(allow_placeholder=True)
        verified_against = provider.selected
    width, height = manifest["canvas"]["width"], manifest["canvas"]["height"]
    report = {"manifest": args.manifest, "canvas": [width, height],
              "production_assets_present": production_present,
              "verified_against": verified_against,
              "source": {"selected": provider.selected,
                         "mode": provider.mode,
                         "rendered_available":
                             provider.rendered_model3_available(),
                         "placeholder_available":
                             provider.placeholder_available()},
              "missing": [], "canvas_mismatch": [], "horizon": {},
              "composed_path": {}}

    checked = 0
    for asset_id, relative in sorted(manifest.get("images", {}).items()):
        path = provider.path_for(relative)
        if not path or not os.path.exists(path):
            report["missing"].append({"id": asset_id, "path": relative})
            continue
        with Image.open(path) as im:
            if im.size != (width, height):
                report["canvas_mismatch"].append(
                    {"id": asset_id, "size": list(im.size)})
        checked += 1
    for asset_id, relative in sorted(manifest.get("overlays", {}).items()):
        path = provider.path_for(relative)
        if not path or not os.path.exists(path):
            report["missing"].append({"id": asset_id, "path": relative})
            continue
        with Image.open(path) as im:
            if im.size != (width, height):
                report["canvas_mismatch"].append(
                    {"id": asset_id, "size": list(im.size)})
        checked += 1
    sequence_frames = {}
    for asset_id, spec in sorted(manifest.get("sequences", {}).items()):
        directory = provider.path_for(spec["dir"])
        if not directory or not os.path.isdir(directory):
            report["missing"].append({"id": asset_id, "path": spec["dir"]})
            continue
        frames = sorted(f for f in os.listdir(directory) if f.endswith(".png"))
        if len(frames) != spec["frames"]:
            report["missing"].append(
                {"id": asset_id, "path": spec["dir"],
                 "detail": f"{len(frames)} frames on disk, manifest says "
                           f"{spec['frames']}"})
            continue
        sequence_frames[asset_id] = len(frames)
        with Image.open(os.path.join(directory, frames[0])) as im:
            if im.size != (width, height):
                report["canvas_mismatch"].append(
                    {"id": asset_id, "size": list(im.size)})
        checked += 1
    report["assets_checked"] = checked
    report["sequence_frames"] = sequence_frames

    for scene_path in HORIZON_SCENES:
        full = os.path.join(REPO_ROOT, scene_path)
        if not os.path.exists(full):
            continue
        ids, sequences = scene_asset_ids(full)
        unresolved = [i for i in ids
                      if i not in manifest.get("images", {})
                      and i not in manifest.get("overlays", {})]
        unresolved_seq = [s for s in sequences
                          if s not in manifest.get("sequences", {})]
        report["horizon"][os.path.basename(scene_path)] = {
            "asset_ids": ids, "sequences": sequences,
            "unresolved_assets": unresolved,
            "unresolved_sequences": unresolved_seq,
            "pass": not unresolved and not unresolved_seq}

    base_bytes = width * height * 4
    # Worst realistic frame: the base, one moving layer at a terminal state, and
    # up to three lighting overlays (brake + an indicator, or hazard).
    overlays_max = 3
    simultaneously = 1 + 1 + overlays_max
    report["composed_path"] = {
        "simultaneously_decoded_assets": simultaneously,
        "decoded_rgba_bytes_per_asset": base_bytes,
        "peak_decoded_rgba_bytes": base_bytes * simultaneously,
        "compositing_operations_per_frame": 1 + 1 + overlays_max,
        "motion_policy": "at most one moving layer sequence is decoded at a "
                         "time; terminal states keep one frame resident",
        "decode_ms_per_asset_t113_estimated":
            round(DECODE_MS_356x236, 3),
        "frame_budget_share_30fps":
            round((DECODE_MS_356x236 * simultaneously) / FRAME_BUDGET_MS[30], 4),
        "frame_budget_share_60fps":
            round((DECODE_MS_356x236 * simultaneously) / FRAME_BUDGET_MS[60], 4),
        "labels": ["mac_measured: canvas and file sizes",
                   "t113_estimated: decode ms from the capability audit",
                   "unknown_until_device_test: achieved fps, variable-frame "
                   "support, simultaneous decode cost"],
    }
    report["production_mode_ok"] = (
        report["source"]["selected"] == "RENDERED_MODEL3"
        and not manifest.get("vehicle_source", {}).get(
            "production_allows_placeholder", False))
    if not production_present:
        report["production_assertions_skipped"] = (
            "the generated production vehicle tree is not in this checkout "
            "(assets/rendered/vehicle is gitignored and rebuilt by "
            "tools/blender/build_vehicle_state_assets.py); the contract was "
            "verified against the committed placeholder art instead")
    report["pass"] = (not report["missing"] and not report["canvas_mismatch"]
                      and all(h["pass"] for h in report["horizon"].values())
                      and (report["production_mode_ok"] or not production_present))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"[check] assets={checked} missing={len(report['missing'])} "
          f"canvas_mismatch={len(report['canvas_mismatch'])}")
    print(f"[check] horizon: "
          f"{ {k: v['pass'] for k, v in report['horizon'].items()} }")
    print(f"[check] production_mode_ok={report['production_mode_ok']} "
          f"pass={report['pass']}")
    if not production_present:
        print("[check] NOTICE: production assets absent; verified against "
              f"{verified_against}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
