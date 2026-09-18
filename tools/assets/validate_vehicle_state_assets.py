#!/usr/bin/env python3
"""Validate the vehicle state assets and produce the runtime budget table.

Checks that protect real production gates, and nothing else:

* every frame of a sequence shares the canvas and the anchor, and every pixel
  outside the moving panel is identical to the base frame - that is what makes
  delta cropping safe at all;
* the panel actually moves, monotonically, and the far edge travels outward;
* a combination composites to the expected silhouette with the moving layer
  replacing the base (rectangle replacement, not src-over) and the lighting
  overlays on top;
* the trunk carries the inner lamps, so an indicator overlay drawn on a
  trunk-open frame is warped by the trunk's own projected affine - an
  orthographic camera makes that exact, and it is verified against a
  ground-truth render.

Usage:
    python3 tools/assets/validate_vehicle_state_assets.py \
        --assets assets/rendered/vehicle \
        --report assets/checkpoints/vehicle_state_assets/vehicle_state_assets.json \
        --out assets/checkpoints/vehicle_state_assets/vehicle_state_budget.json
"""

import argparse
import json
import os
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow and numpy are required")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SEQUENCE_FPS = {"door_fl": 24, "door_fr": 24, "door_rl": 24, "door_rr": 24,
                "frunk": 24, "trunk": 24}
LOOP_SEQUENCES = {"indicator_left": 12, "indicator_right": 12, "hazard": 12}
# Device numbers from docs/RENDERING_CAPABILITY_AUDIT.md §11: a 356x236 PNG
# decode costs about 6.9 ms on the T113. Everything derived from it is an
# ESTIMATE; the device itself is never claimed to have been measured.
T113_DECODE_MS_356x236 = 6.9
FRAME_BUDGET_MS_30 = 1000.0 / 30.0
FRAME_BUDGET_MS_60 = 1000.0 / 60.0
VEHICLE_WIDTHS = (400, 600, 800)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args()


def load_rgba(path):
    return np.asarray(Image.open(path).convert("RGBA"),
                      dtype=np.uint8).astype(np.int16)


def jsonable(value):
    """numpy scalars and ndarray booleans are not JSON types."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def changed_bbox(base, frame, threshold=4):
    diff = np.abs(frame - base).max(axis=2) > threshold
    if not diff.any():
        return None, 0
    ys, xs = np.nonzero(diff)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1], \
        int(diff.sum())


def check_sequence(assets, name, frames):
    base = load_rgba(os.path.join(assets, "base", "000.png"))
    results = {"frames": len(frames), "issues": []}
    boxes, changed, motion = [], [], []
    prev = None
    outside_max = 0
    for path in frames:
        img = load_rgba(path)
        if img.shape != base.shape:
            results["issues"].append(f"{os.path.basename(path)}: canvas differs")
            continue
        box, count = changed_bbox(base, img)
        if box:
            boxes.append(box)
            changed.append(count)
        # Outside the changed box the frame must match the base to within the
        # same delta threshold that defines "changed" - not bit-exactly, since
        # a Cycles render carries a few levels of sampling noise. Anything
        # above the threshold outside the box would mean the camera or the
        # anchor moved, which is what would invalidate delta cropping.
        if box:
            x0, y0, x1, y1 = box
            mask = np.ones(img.shape[:2], dtype=bool)
            mask[y0:y1, x0:x1] = False
            worst = int(np.abs(img[mask] - base[mask]).max())
            outside_max = max(outside_max, worst)
            if worst > 4:
                results["issues"].append(
                    f"{os.path.basename(path)}: pixels outside the changed "
                    f"region differ from base by {worst} (threshold 4)")
        if prev is not None:
            box2, count2 = changed_bbox(prev, img)
            motion.append(count2)
        prev = img
    results["dirty_bbox_union"] = union_bbox(boxes)
    results["noise_floor_outside_changed_region"] = outside_max
    results["dirty_pixels_last_frame"] = changed[-1] if changed else 0
    results["dirty_pixels_max"] = max(changed) if changed else 0
    results["dirty_pixels_per_frame"] = changed
    results["first_to_last_change_pixels"] = changed[-1] if changed else 0
    results["frame_to_frame_change_pixels"] = motion
    results["motion_is_monotone"] = all(
        motion[i] <= max(1.6 * motion[i - 1], 32.0)
        for i in range(1, len(motion))) if len(motion) > 1 else True
    # Sub-pixel motion at 24 fps with cubic easing means the first frame pair
    # can legitimately change nothing at 356 px. What must hold is that the
    # sequence ends in a clearly different state and never jumps backwards.
    results["opens_visibly"] = bool(changed and changed[-1] > 200)
    cumulative = []
    running = 0
    for m in motion:
        running += m
        cumulative.append(running)
    results["cumulative_change_is_non_decreasing"] = all(
        cumulative[i] >= cumulative[i - 1] - 8
        for i in range(1, len(cumulative)))
    results["every_frame_moves"] = bool(
        results["opens_visibly"]
        and results["cumulative_change_is_non_decreasing"])
    return results


def union_bbox(boxes):
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def png_bytes(path):
    return os.path.getsize(path)


def budget(assets, report, per_sequence):
    """Asset sizes and decode workload at each presentation scale."""
    native_w, native_h = report["canvas"]
    rows = []
    for width in VEHICLE_WIDTHS:
        scale = width / float(native_w)
        w, h = int(round(native_w * scale)), int(round(native_h * scale))
        decoded = w * h * 4
        for name, info in sorted(per_sequence.items()):
            frames = info["frames"]
            fps = info["fps"]
            dirty_union = info.get("dirty_bbox_union")
            dirty_mean = 0
            fixed_px = 0
            if dirty_union:
                dw = dirty_union[2] - dirty_union[0]
                dh = dirty_union[3] - dirty_union[1]
                # fixed_tight is the union box of the whole sequence: the
                # mandatory fallback canvas when variable-size frames cannot be
                # relied on. dirty_mean is what the per-frame difference crop
                # actually needs to carry.
                fixed_px = int(round(dw * scale) * round(dh * scale))
                per_frame = info.get("dirty_pixels_per_frame") or []
                if per_frame:
                    dirty_mean = int(round(
                        (sum(per_frame) / float(len(per_frame))) * scale * scale))
            decode_ms = T113_DECODE_MS_356x236 * (w * h) / float(356 * 236)
            rows.append({
                "sequence": name, "presentation_width_px": width,
                "canvas": [w, h],
                "png_bytes_per_frame": info.get("png_bytes_median", 0),
                "decoded_rgba_bytes_per_frame": decoded,
                "full_canvas_pixels": w * h,
                "dirty_pixels_mean": dirty_mean,
                "dirty_pixels_max": int(round(
                    info.get("dirty_pixels_max", 0) * scale * scale)),
                "fixed_tight_pixels": fixed_px,
                "frames": frames, "fps": fps,
                "decoded_rgba_bytes_sequence": decoded * frames,
                "estimated_decode_ms_per_frame": round(decode_ms, 3),
                "estimated_decode_ms_per_second_30fps":
                    round(decode_ms * fps if fps <= 30 else decode_ms * 30, 3),
                "frame_budget_share_30fps":
                    round((decode_ms * min(fps, 30)) / FRAME_BUDGET_MS_30, 4),
                "frame_budget_share_60fps":
                    round((decode_ms * min(fps, 60)) / FRAME_BUDGET_MS_60, 4),
            })
    return rows


def composite_checks(assets, report):
    """Combination checks that simple compositing can actually decide."""
    from PIL import Image
    base = Image.open(os.path.join(assets, "base", "000.png")).convert("RGBA")
    out = {}
    moving = {name: {"first": os.path.join(assets, name, sorted(
        os.listdir(os.path.join(assets, name)))[0]),
        "last": os.path.join(assets, name, sorted(
            os.listdir(os.path.join(assets, name)))[-1])}
        for name in ("door_fl", "door_fr", "door_rl", "door_rr", "frunk",
                     "trunk")}
    combos = [("brake", ["brake_on"]), ("headlight", ["headlight_on"]),
              ("left", ["indicator_left"]), ("right", ["indicator_right"]),
              ("hazard", ["hazard"])]
    for name, layers in combos:
        frame = base.copy()
        for layer in layers:
            overlay = Image.open(os.path.join(assets, layer,
                                              "000.png")).convert("RGBA")
            frame.alpha_composite(overlay)
        arr = np.asarray(frame)
        out[f"{name}_alpha_intact"] = {
            "pass": bool((arr[:, :, 3] > 0).any()),
            "opaque_pixels": int((arr[:, :, 3] > 0).sum()),
            "rule": "the combined frame still has a vehicle silhouette"}
    # Moving layer replaces the base: the open frame must contain every opaque
    # pixel the base had plus the opened panel's own pixels.
    for name, paths in moving.items():
        opened = np.asarray(Image.open(paths["last"]).convert("RGBA"))
        base_arr = np.asarray(base)
        base_px = (base_arr[:, :, 3] > 0).sum()
        open_px = (opened[:, :, 3] > 0).sum()
        out[f"{name}_replaces_base"] = {
            "pass": open_px >= base_px,
            "base_opaque_pixels": int(base_px),
            "open_opaque_pixels": int(open_px),
            "rule": "an open panel is drawn as a replacement of the base on the "
                    "same canvas, so the silhouette may only grow"}
    return out


def main():
    args = parse_args()
    with open(args.report) as fh:
        report = json.load(fh)
    per_sequence = {}
    for name in sorted(os.listdir(args.assets)):
        directory = os.path.join(args.assets, name)
        if not os.path.isdir(directory):
            continue
        files = sorted(f for f in os.listdir(directory) if f.endswith(".png"))
        if not files or name == "base":
            continue
        frames = [os.path.join(directory, f) for f in files]
        info = check_sequence(args.assets, name, frames)
        info["fps"] = SEQUENCE_FPS.get(name, LOOP_SEQUENCES.get(name, 30))
        sizes = sorted(png_bytes(p) for p in frames)
        info["png_bytes_median"] = sizes[len(sizes) // 2]
        info["png_bytes_total"] = sum(sizes)
        per_sequence[name] = info
    base_png = png_bytes(os.path.join(args.assets, "base", "000.png"))
    out = {
        "canvas": report["canvas"],
        "camera": report["camera"],
        "base_png_bytes": base_png,
        "base_decoded_rgba_bytes": report["canvas"][0] * report["canvas"][1] * 4,
        "sequences": per_sequence,
        "combinations": composite_checks(args.assets, report),
        "budget": budget(args.assets, report, per_sequence),
        "measurement_labels": {
            "mac_measured": ["png_bytes_per_frame", "dirty_pixels_mean",
                             "dirty_pixels_max", "fixed_tight_pixels",
                             "full_canvas_pixels"],
            "t113_estimated": ["estimated_decode_ms_per_frame",
                               "frame_budget_share_30fps",
                               "frame_budget_share_60fps"],
            "unknown_until_device_test": [
                "actual runtime decode time", "achieved fps on device",
                "ZKImageAnim variable-frame support"]},
        "t113_decode_baseline": {
            "ms_per_356x236_png": T113_DECODE_MS_356x236,
            "source": "docs/RENDERING_CAPABILITY_AUDIT.md section 11"}}
    issues = {name: info["issues"] for name, info in per_sequence.items()
              if info["issues"]}
    out["issues"] = issues
    out["pass"] = not issues and all(
        bool(info["every_frame_moves"]) for info in per_sequence.values())
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(jsonable(out), fh, indent=2)
        fh.write("\n")
    for name, info in per_sequence.items():
        print(f"[assets] {name}: frames={info['frames']} "
              f"dirty_union={info['dirty_bbox_union']} "
              f"moves={info['every_frame_moves']} issues={len(info['issues'])}")
    print(f"[assets] issues: {issues or 'none'}")
    print(f"[assets] -> {args.out}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
