#!/usr/bin/env python3
"""Horizon V2: the design, the scene and the screenshots have to agree.

Three things are checked, none of which needs an eye:

* the layout QA (bounds, zones, panel mask, collisions, unknown behaviour,
  debug isolation) passes on the committed layout and scene;
* regenerating the scene from the layout is idempotent, so a hand edit to
  scenes/horizon_v2.scene is caught;
* the twelve screenshots exist at exactly 1920x480, are deterministic, and the
  state changes land where they should - and nowhere else.

Usage:
    python3 tests/horizon_v2_tests.py
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")
GEN = os.path.join(REPO, "tools", "preview", "build_horizon_v2.py")
QA = os.path.join(REPO, "tools", "preview", "horizon_v2_layout_qa.py")
SCENE = os.path.join(REPO, "scenes", "horizon_v2.scene")
LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v2_layout.json")
SHOTS = os.path.join(REPO, "assets", "checkpoints", "horizon_v2")

FAILURES = []


def check(condition, label):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILURES.append(label)
    return condition


def digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def render(state, out_dir, name):
    result = subprocess.run(
        [sys.executable, PREVIEW, "--scene", SCENE, "--state", state,
         "--out", out_dir, "--out-name", name],
        capture_output=True, text=True)
    path = os.path.join(out_dir, name + ".png")
    return path if result.returncode == 0 and os.path.exists(path) else None


def changed_pixels(first, second):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(first).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(second).convert("RGB"), dtype=np.int16)
    return np.abs(a - b).max(axis=2) > 8


def main():
    layout = json.load(open(LAYOUT))

    # ---------------------------------------------------------- layout QA
    print("layout QA")
    qa = subprocess.run([sys.executable, QA], capture_output=True, text=True)
    detail = "" if qa.returncode == 0 else " :: " + (
        qa.stdout.strip().splitlines()[-1] if qa.stdout.strip() else str(qa.returncode))
    check(qa.returncode == 0,
          "the layout QA passes (bounds, zones, mask, collisions, unknown, "
          f"debug isolation){detail}")

    # ------------------------------------------------- scene is generated
    print("golden scene")
    before = digest(SCENE)
    subprocess.run([sys.executable, GEN], check=True, capture_output=True)
    check(digest(SCENE) == before,
          "regenerating the scene from the layout reproduces it byte for byte")
    scene = json.load(open(SCENE))
    check(scene["status"] == "AWAITING_HUMAN_VISUAL_APPROVAL",
          "the scene still says it is awaiting human approval")

    # ------------------------------------------------------- screenshots
    print("screenshots")
    states = layout["screenshot_states"]
    names = layout["screenshot_names"]
    missing = [n for n in names if not os.path.exists(os.path.join(SHOTS, n))]
    check(not missing, f"the twelve screenshots are committed ({missing})")

    from PIL import Image
    for name in names:
        path = os.path.join(SHOTS, name)
        if not os.path.exists(path):
            continue
        check(Image.open(path).size == (1920, 480), f"{name} is 1920x480")

    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        deterministic = True
        for state, name in zip(states, names):
            stem = name[:-4]
            a = render(state, first, stem)
            b = render(state, second, stem)
            if not a or not b or digest(a) != digest(b):
                deterministic = False
        check(deterministic, "two renders of every state are identical")

        # -------------------------------------------------- state changes
        print("state changes")
        frames = {}
        for state, name in zip(states, names):
            path = os.path.join(SHOTS, name)
            if os.path.exists(path):
                frames[state] = path
        if "h2_neutral" in frames:
            neutral = frames["h2_neutral"]
            # The vehicle's permitted region plus the warning strip: a state
            # change belongs there and nowhere else.
            import numpy as np
            vehicle = {"x": 560, "y": 100, "w": 800, "h": 356}
            warn = {"x": 660, "y": 400, "w": 600, "h": 60}

            def outside_allowed(mask):
                allowed = np.zeros_like(mask)
                for region in (vehicle, warn):
                    allowed[region["y"]:region["y"] + region["h"],
                            region["x"]:region["x"] + region["w"]] = True
                return int((mask & ~allowed).sum())

            for state in ("h2_brake", "h2_left", "h2_right", "h2_hazard",
                          "h2_door_fl", "h2_all_doors", "h2_frunk", "h2_trunk"):
                if state not in frames:
                    continue
                mask = changed_pixels(neutral, frames[state])
                total = int(mask.sum())
                leaked = outside_allowed(mask)
                check(total > 200 and leaked == 0,
                      f"{state} changes the vehicle and nothing else "
                      f"(changed={total}, outside={leaked})")

            # Indicators are side-specific; hazard is both sides.
            if "h2_left" in frames and "h2_right" in frames and "h2_hazard" in frames:
                left_mask = changed_pixels(neutral, frames["h2_left"])
                right_mask = changed_pixels(neutral, frames["h2_right"])
                left_half = left_mask[:, :960].sum()
                right_half = left_mask[:, 960:].sum()
                check(left_half > right_half,
                      f"the left indicator is left-heavy ({left_half} vs {right_half})")
                hazard = changed_pixels(neutral, frames["h2_hazard"])
                check(hazard[:, :960].sum() > 0 and hazard[:, 960:].sum() > 0,
                      "hazard lights both sides")

            # Low SOC is an energy-column change, and it must recolour the bar.
            if "h2_low_soc" in frames:
                mask = changed_pixels(neutral, frames["h2_low_soc"])
                energy = mask[:, 1490:]
                check(int(energy.sum()) > 100,
                      f"low SOC changes the energy column ({int(energy.sum())} px)")

            # Unknown is not silence: it replaces values in every column.
            if "h2_unknown" in frames:
                mask = changed_pixels(neutral, frames["h2_unknown"])
                zones = {"driver": mask[:, 60:430].sum(),
                         "energy": mask[:, 1490:1860].sum(),
                         "top": mask[0:100, 400:1500].sum()}
                check(all(value > 20 for value in zones.values()),
                      f"the unknown screen replaces values in every column {zones}")

            # Navigation adds a pill at the top and touches nothing else.
            if "h2_navigation" in frames:
                mask = changed_pixels(neutral, frames["h2_navigation"])
                pill = mask[18:80, 650:1270].sum()
                check(int(pill) > 500,
                      f"the navigation state draws the pill ({int(pill)} px)")

    print("")
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for failure in FAILURES:
            print(f"  {failure}")
        return 1
    print("all horizon v2 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
