#!/usr/bin/env python3
"""Part A: per-panel normal policy from the reflection-strip diagnostic.

The previous round applied one normal fix to the whole car. Review then found
that the rear quarter got WORSE (waviness 4.36 -> 5.14), so a blanket fix is
wrong. This measures each panel separately, in the view where that panel has
the largest projected area, across three treatments:

    ORIGINAL   as imported (custom split normals, original winding)
    CLEAN      custom normals cleared, welded, recalculated, shade smooth
    WEIGHTED   CLEAN plus a Weighted Normal modifier (keep_sharp)

Four separate signals are recorded per panel, because a single number must not
make the decision:
    waviness    reflection continuity (2nd difference RMS of the ridge)
    breaks      reflection break (columns with no ridge inside the panel)
    deform      highlight deformation (p95 ridge thickness / median)
    crease      crease preservation (gradient energy: a treatment that wipes
                out sharp panel features lowers this)

The policy is derived from those four together and the raw numbers are written
out next to the verdict so it can be overridden by hand.

Usage:
    python3 tools/assets/build_panel_normal_policy.py
"""

import json
import os
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow required")

import numpy as np

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.path.join(REPO_ROOT, "assets", "rendered", "diagnostic")
VARIANTS = ["original", "clean", "weighted"]
VIEWS = ["side", "rear_quarter", "roof", "doors"]

PANELS = {
    "door_lf": "front left door",
    "door_rf": "front right door",
    "door_lr": "rear left door",
    "door_rr": "rear right door",
    "bonnet_ok": "hood",
    "boot": "trunk",
    "front_bumper_ok": "front bumper",
    "rear_bumper_ok": "rear bumper",
    "body": "body shell (roof metal, fenders, rear quarters, C pillars)",
}


def load(variant, view):
    path = os.path.join(BASE, f"panel_{variant}", f"{view}.png")
    arr = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    return arr[..., :3].mean(axis=2), arr[..., 3] > 8


def region_metrics(lum, mask, box):
    x0, y0, x1, y1 = box
    h, w = lum.shape
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 - x0 < 24 or y1 - y0 < 24:
        return None
    sub = lum[y0:y1, x0:x1]
    subm = mask[y0:y1, x0:x1]
    if subm.sum() < 200:
        return None

    inside = sub[subm]
    peak = float(np.percentile(inside, 99.5))
    if peak <= 1.0:
        return {"waviness": 0.0, "breaks": 0, "deform": 0.0, "crease": 0.0,
                "note": "no reflection in region"}
    ridge = subm & (sub > peak * 0.55)

    pos, thick, missing = [], [], 0
    for x in range(sub.shape[1]):
        col = np.nonzero(ridge[:, x])[0]
        if col.size == 0:
            pos.append(np.nan)
            missing += 1
        else:
            pos.append(float(col.mean()))
            thick.append(float(col.max() - col.min() + 1))
    pos = np.asarray(pos, dtype=np.float32)

    runs, run = [], []
    for v in pos:
        if np.isnan(v):
            if len(run) >= 4:
                runs.append(np.asarray(run, dtype=np.float32))
            run = []
        else:
            run.append(v)
    if len(run) >= 4:
        runs.append(np.asarray(run, dtype=np.float32))
    second = [float(np.sqrt(np.mean((s[2:] - 2 * s[1:-1] + s[:-2]) ** 2)))
              for s in runs]
    waviness = float(np.mean(second)) if second else 0.0

    med_t = float(np.median(thick)) if thick else 1.0
    p95_t = float(np.percentile(thick, 95)) if thick else 1.0
    deform = p95_t / max(med_t, 1e-6)

    # Crease preservation: gradient energy inside the panel. Wiping out a
    # panel edge or a crease lowers this.
    gx = np.abs(np.diff(sub, axis=1))[subm[:, :-1]]
    gy = np.abs(np.diff(sub, axis=0))[subm[:-1, :]]
    crease = float(np.concatenate([gx, gy]).mean()) if gx.size else 0.0

    return {"waviness": round(waviness, 3), "breaks": int(missing),
            "deform": round(deform, 2), "crease": round(crease, 3),
            "area_px": int(subm.sum())}


def main():
    boxes = {}
    for view in VIEWS:
        with open(os.path.join(BASE, "panel_original", f"{view}_boxes.json")) as fh:
            boxes[view] = json.load(fh)

    policy, detail = {}, {}
    for panel, role in PANELS.items():
        # Use the view where this panel has the largest projected area.
        best_view, best_area = None, -1
        for view in VIEWS:
            box = boxes[view].get(panel)
            if not box:
                continue
            area = max(0, box[2] - box[0]) * max(0, box[3] - box[1])
            if area > best_area:
                best_view, best_area = view, area
        if best_view is None:
            continue
        box = boxes[best_view][panel]

        per = {}
        for variant in VARIANTS:
            lum, mask = load(variant, best_view)
            m = region_metrics(lum, mask, box)
            if m:
                per[variant] = m
        if len(per) < 3:
            continue

        base = per["original"]
        verdict, reason = "KEEP_ORIGINAL", "original is already best"

        def better(cand):
            # A candidate must improve continuity without breaking the
            # reflection more, without deforming the highlight more, and
            # without destroying crease energy.
            if cand["waviness"] > base["waviness"] * 0.85:
                return False
            if cand["breaks"] > base["breaks"] * 1.25 + 2:
                return False
            if cand["deform"] > base["deform"] * 1.20 + 0.05:
                return False
            if cand["crease"] < base["crease"] * 0.85:
                return False
            return True

        w_ok = better(per["weighted"])
        c_ok = better(per["clean"])
        if w_ok and (not c_ok or per["weighted"]["waviness"]
                     <= per["clean"]["waviness"]):
            verdict = "WEIGHTED"
            reason = (f"waviness {base['waviness']} -> "
                      f"{per['weighted']['waviness']}, breaks "
                      f"{base['breaks']} -> {per['weighted']['breaks']}, "
                      f"crease {base['crease']} -> "
                      f"{per['weighted']['crease']}")
        elif c_ok:
            verdict = "CLEAN"
            reason = (f"waviness {base['waviness']} -> "
                      f"{per['clean']['waviness']}, breaks "
                      f"{base['breaks']} -> {per['clean']['breaks']}")
        elif per["clean"]["waviness"] > base["waviness"] and \
                per["weighted"]["waviness"] > base["waviness"]:
            reason = (f"both treatments make it worse "
                      f"(clean {per['clean']['waviness']}, weighted "
                      f"{per['weighted']['waviness']} vs original "
                      f"{base['waviness']})")

        policy[panel] = verdict
        detail[panel] = {"role": role, "view": best_view, "box": box,
                         "verdict": verdict, "reason": reason,
                         "measurements": per}
        print(f"{panel:16s} {best_view:13s} {verdict:14s} {reason}")

    out = {"policy": policy, "panels": detail,
           "method": ("verdict requires lower waviness AND no worse breaks "
                      "AND no worse highlight deformation AND crease energy "
                      "preserved; raw numbers are recorded so it can be "
                      "overridden by hand")}
    path = os.path.join(REPO_ROOT, "assets", "checkpoints",
                        "model_a_ceiling_2026-09-16", "panel_normal_policy.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(f"\n[policy] -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
