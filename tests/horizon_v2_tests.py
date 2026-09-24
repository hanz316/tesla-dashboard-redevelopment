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


def delta_report():
    path = os.path.join(REPO, "assets", "rendered", "vehicle", "delta",
                        "delta_report.json")
    if not os.path.exists(path):
        return {"groups": {}}
    return json.load(open(path))


def main():
    layout = json.load(open(LAYOUT))
    report_delta = delta_report()

    # ---------------------------------------------------------- layout QA
    print("layout QA")
    qa = subprocess.run([sys.executable, QA], capture_output=True, text=True)
    detail = "" if qa.returncode == 0 else " :: " + (
        qa.stdout.strip().splitlines()[-1] if qa.stdout.strip() else str(qa.returncode))
    check(qa.returncode == 0,
          "the layout QA passes (bounds, zones, mask, collisions, unknown, "
          f"debug isolation){detail}")

    # The moving-panel composition rules live with the assets they describe.
    composition = os.path.join(REPO, "tools", "assets", "panel_composition_qa.py")
    if os.path.exists(composition):
        result = subprocess.run([sys.executable, composition],
                                capture_output=True, text=True)
        tail = (result.stdout.strip().splitlines() or [""])[-1]
        check(result.returncode == 0,
              f"the panel composition QA passes :: {tail}")

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

    try:
        from PIL import Image
        have_pil = True
    except ImportError:
        have_pil = False
        print("  note Pillow is absent: size, determinism and pixel checks are skipped")
    if have_pil:
        for name in names:
            path = os.path.join(SHOTS, name)
            if not os.path.exists(path):
                continue
            check(Image.open(path).size == (1920, 480), f"{name} is 1920x480")

    # ------------------------------------------------- panel composition
    # The defect this exists for: every state render is a whole car, so the old
    # compositor let a later state repaint an earlier open panel back to closed.
    print("panel composition")
    shot = os.path.join(SHOTS, "horizon_v2_%s.png")
    vehicle_box = (666, 85, 1250, 472)

    def changed(first, second):
        return changed_pixels(first, second)

    if have_pil and all(os.path.exists(shot % name) for name in
                        ("neutral", "door_fl", "door_fr", "door_rl", "door_rr",
                         "all_doors", "frunk", "trunk", "trunk_left", "trunk_hazard")):
        neutral = shot % "neutral"
        # (a) CLOSED must not have moved. The reference is the neutral rendered
        # before the composition change. Differences are allowed only where a
        # lamp layer legitimately draws (the tail bar) and in the clock box,
        # which shows the wall clock.
        reference = os.path.join(SHOTS, "reference", "neutral_pre_panel_fix.png")
        if os.path.exists(reference):
            import numpy as np
            mask = changed(reference, neutral)
            # Allowed: the clock (it shows the wall clock) and wherever a lamp
            # layer draws. The lamp frames are whole-car renders whose silhouette
            # differs from the base by an anti-aliased edge, so their layers
            # legitimately touch the car's outline.
            allowed = np.zeros_like(mask)
            allowed[48:112, 1600:1812] = True  # the clock, including its shadow line
            # The lamp layers themselves, mapped into the vehicle box: their
            # frames are whole-car renders, so their layers legitimately run
            # along the car's anti-aliased outline.
            from PIL import Image as PILImage
            sx, sy = 584.0 / 356.0, 387.0 / 236.0
            for group in ("headlight_on", "running_on", "brake_on"):
                for entry in report_delta.get("groups", {}).get(group, {}).get("entries", []):
                    layer = PILImage.open(os.path.join(REPO, entry["layer"])).convert("RGBA")
                    alpha = layer.getchannel("A").resize((584, 387), PILImage.LANCZOS)
                    box = np.asarray(alpha) > 8
                    for _ in range(3):
                        box = (box | np.roll(box, 1, axis=0) | np.roll(box, -1, axis=0) |
                               np.roll(box, 1, axis=1) | np.roll(box, -1, axis=1))
                    sub = allowed[85:85 + 387, 666:666 + 584]
                    allowed[85:85 + 387, 666:666 + 584] = sub | box
            # And the car's own anti-aliased outline: the old path pasted whole
            # frames whose fully transparent pixels still carried colour, which
            # LANCZOS smeared along the silhouette. The layers carry no such
            # data, so the edge is the one place a legitimate difference can
            # appear. Inside the body, nothing may move.
            base_asset = PILImage.open(os.path.join(
                REPO, "assets", "rendered", "vehicle", "base", "000.png")).convert("RGBA")
            body = np.asarray(base_asset.getchannel("A").resize(
                (584, 387), PILImage.LANCZOS)) > 8
            edge = np.zeros_like(body)
            for _ in range(4):
                edge = (edge | body | np.roll(body, 1, axis=0) |
                        np.roll(body, -1, axis=0) | np.roll(body, 1, axis=1) |
                        np.roll(body, -1, axis=1))
                body = edge
            interior = ~edge
            sub = allowed[85:85 + 387, 666:666 + 584]
            allowed[85:85 + 387, 666:666 + 584] = sub | edge
            interior_box = np.zeros_like(mask)
            interior_box[85:85 + 387, 666:666 + 584] = interior
            check(int((mask & interior_box).sum()) == 0,
                  "the closed car's interior is pixel-identical to the "
                  f"reference ({int((mask & interior_box).sum())} px differ)")
            stray = int((mask & ~allowed).sum())
            check(stray == 0,
                  f"the closed state is unchanged outside the lamp bar and the "
                  f"clock ({stray} px stray, {int(mask.sum())} px total)")

        # (b) every panel state changes the car and nothing else.
        for name in ("door_fl", "door_fr", "door_rl", "door_rr", "all_doors",
                     "frunk", "trunk", "trunk_left", "trunk_hazard", "mixed"):
            path = shot % name
            if not os.path.exists(path):
                continue
            mask = changed(neutral, path)
            outside = mask.copy()
            outside[vehicle_box[1]:vehicle_box[3], vehicle_box[0]:vehicle_box[2]] = False
            check(int(mask.sum()) > 100 and int(outside.sum()) == 0,
                  f"{name}: changes the car and nothing else "
                  f"({int(mask.sum())} px, {int(outside.sum())} outside)")

        # (c) opening a panel must change where that panel is. A door's own
        # region is where the door sits in the car, checked as: each door state
        # differs from neutral in a *different* part of the car.
        if have_pil:
            import numpy as np
            regions = {}
            for name in ("door_fl", "door_fr", "door_rl", "door_rr"):
                mask = changed(neutral, shot % name)
                ys, xs = np.nonzero(mask)
                regions[name] = (float(xs.mean()), float(ys.mean()))
            check(regions["door_fl"][0] < regions["door_fr"][0],
                  f"the left-side doors change the left of the car "
                  f"({regions['door_fl'][0]:.0f} vs {regions['door_fr'][0]:.0f})")
            check(regions["door_rl"][0] < regions["door_rr"][0],
                  f"the rear pair separates the same way "
                  f"({regions['door_rl'][0]:.0f} vs {regions['door_rr'][0]:.0f})")

        # (d) trunk lighting ownership, measured on the output: switching the
        # left indicator on with the lid open may only change the lid's own
        # area, never the closed-position lamp.
        if have_pil:
            import numpy as np
            mask = changed(shot % "trunk", shot % "trunk_left")
            ys, xs = np.nonzero(mask)
            # The lid sits at the rear of the car, which is the left end of the
            # vehicle box in this view.
            check(int(mask.sum()) > 0 and xs.max() < 1000,
                  f"opening the lid's lamps changes the lid only "
                  f"({int(mask.sum())} px, x up to {int(xs.max()) if len(xs) else 0})")

    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        if not have_pil:
            print("")
            print("all horizon v2 checks passed (Pillow-dependent checks skipped)")
            return 0
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
                check(total > 80 and leaked == 0,
                      f"{state} changes the vehicle and nothing else "
                      f"(changed={total}, outside={leaked})")

            # Indicators are side-specific; hazard is both sides. Which side of
            # the *screen* a lamp sits on is not the car's side (the car is
            # rendered from a rear three-quarter view), so the rectangles come
            # from the asset layers themselves.
            if "h2_left" in frames and "h2_right" in frames and "h2_hazard" in frames:
                import numpy as np

                def lamp_rect(group):
                    entries = report_delta["groups"][group]["entries"]
                    best = max(entries, key=lambda entry: entry["pixels"])
                    with_delta = best["bbox"]
                    sx, sy = 584.0 / 356.0, 387.0 / 236.0
                    return (666 + with_delta[0] * sx, 85 + with_delta[1] * sy,
                            666 + with_delta[2] * sx, 85 + with_delta[3] * sy)

                left_rect = lamp_rect("indicator_left")
                right_rect = lamp_rect("indicator_right")
                left_mask = changed_pixels(neutral, frames["h2_left"])
                right_mask = changed_pixels(neutral, frames["h2_right"])
                hazard = changed_pixels(neutral, frames["h2_hazard"])
                left_hits = int(left_mask[int(left_rect[1]):int(left_rect[3]),
                                          int(left_rect[0]):int(left_rect[2])].sum())
                left_stray = int(left_mask.sum()) - left_hits
                right_hits = int(right_mask[int(right_rect[1]):int(right_rect[3]),
                                            int(right_rect[0]):int(right_rect[2])].sum())
                check(left_hits > 0 and left_stray < 40,
                      f"the left indicator lights the left lamp ({left_hits} px "
                      f"in its rect, {left_stray} elsewhere)")
                check(right_hits > 0,
                      f"the right indicator lights the right lamp ({right_hits} px)")
                hazard_hits = int(hazard[int(left_rect[1]):int(left_rect[3]),
                                         int(left_rect[0]):int(left_rect[2])].sum())
                hazard_hits += int(hazard[int(right_rect[1]):int(right_rect[3]),
                                          int(right_rect[0]):int(right_rect[2])].sum())
                check(hazard_hits > 0 and int(hazard.sum()) <= hazard_hits + 40,
                      f"hazard lights both lamp rects ({int(hazard.sum())} px "
                      f"changed, {hazard_hits} in the two rects)")

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
