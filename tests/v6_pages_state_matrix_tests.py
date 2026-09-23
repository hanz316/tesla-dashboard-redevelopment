#!/usr/bin/env python3
"""Every screen, in every state that matters.

One render per screen proves the happy path and nothing else. The states that
decide whether an instrument is trustworthy are the adverse ones: a door open,
the vehicle link lost, an SOC that exists but cannot be trusted. This renders
the whole set through all four and checks that each screen still draws
something, still differs from the normal state where it must, and never ends up
blank.

Runs the previewer as a subprocess (the same entry point a human uses) into a
temporary directory; nothing is committed.

Usage:
    python3 tests/v6_pages_state_matrix_tests.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENES = os.path.join(REPO, "scenes")
PAGE_DUMP = os.path.join(REPO, "tools", "preview", "scene_preview.py")

PAGES = ["horizon", "mono", "pulse", "route", "studio", "energy",
         "nocturne", "settings", "developer"]
STATES = ["normal_drive", "door_fl_open", "uart_lost", "soc_untrusted"]

# A screen that lights fewer pixels than this is effectively blank.
MIN_LIT_PIXELS = 300

# Where a state must be visible. The pair is (page, state) and the statement is
# "this render differs from the same page in normal_drive".
MUST_DIFFER = [
    ("studio", "door_fl_open"),   # the car on screen has a door open
    ("horizon", "door_fl_open"),  # the context line appears
    ("horizon", "uart_lost"),     # the link is announced as lost
    ("route", "uart_lost"),
    ("nocturne", "uart_lost"),
]

# Pages with no SOC at all must be identical between a trusted and an
# untrusted SOC: they never draw one.
SOC_FREE_PAGES = ["mono", "nocturne", "settings"]


def main():
    try:
        import numpy as np
        from PIL import Image
    except ImportError as error:
        print(f"SKIPPED: Pillow and numpy are required ({error})")
        return 0

    out = tempfile.mkdtemp(prefix="v6-matrix-")
    try:
        failures = []
        frames = {}
        for page in PAGES:
            for state in STATES:
                name = f"{page}__{state}"
                result = subprocess.run(
                    [sys.executable, PAGE_DUMP,
                     "--scene", os.path.join(SCENES, f"v6_{page}.scene"),
                     "--state", state,
                     "--out", out, "--out-name", name],
                    capture_output=True, text=True)
                path = os.path.join(out, name + ".png")
                if result.returncode != 0 or not os.path.exists(path):
                    failures.append(
                        f"{name}: render failed "
                        f"({result.stderr.strip().splitlines()[-1:] or result.returncode})")
                    continue
                image = np.asarray(Image.open(path).convert("RGB"),
                                   dtype=np.uint8)
                if image.shape[:2] != (480, 1920):
                    failures.append(f"{name}: {image.shape[:2]} is not 1920x480")
                lit = int((image.max(axis=2) > 24).sum())
                if lit < MIN_LIT_PIXELS:
                    failures.append(f"{name}: only {lit} lit pixels")
                frames[(page, state)] = image

        for page, state in MUST_DIFFER:
            base = frames.get((page, "normal_drive"))
            other = frames.get((page, state))
            if base is None or other is None:
                continue
            changed = int((np.abs(base.astype(np.int16) -
                                  other.astype(np.int16)).max(axis=2) > 8).sum())
            if changed < 50:
                failures.append(
                    f"{page}/{state}: only {changed} pixels differ from "
                    f"normal_drive")
            else:
                print(f"  ok   {page}: {state} changes {changed} pixels")

        for page in SOC_FREE_PAGES:
            trusted = frames.get((page, "normal_drive"))
            untrusted = frames.get((page, "soc_untrusted"))
            if trusted is None or untrusted is None:
                continue
            changed = int((np.abs(trusted.astype(np.int16) -
                                  untrusted.astype(np.int16)).max(axis=2) > 8).sum())
            # The mock states differ in more than SOC, so this is a low bar; the
            # real rule (a page with no SOC binding never draws 97 %) is checked
            # against the scenes in v6_pages_tests.py.
            if changed > 0:
                print(f"  note {page}: {changed} pixels differ between SOC "
                      f"states (page has no SOC binding)")

        renders = len(PAGES) * len(STATES)

        # Text-level pass: the states that matter are about what a value says,
        # not only about whether pixels moved. An SOC that exists but cannot be
        # trusted may not appear as a number on any screen.
        sys.path.insert(0, os.path.join(REPO, "tools", "preview"))
        try:
            import scene_preview
        except ImportError as error:  # pragma: no cover
            failures.append(f"the previewer is importable ({error})")
        else:
            import json
            untrusted_soc = int(scene_preview.MOCK_STATES["soc_untrusted"]["soc"])
            printed = []
            resolved_counts = 0
            for state_name, raw in sorted(scene_preview.MOCK_STATES.items()):
                state = scene_preview.State(raw)
                for page in PAGES:
                    with open(os.path.join(SCENES, f"v6_{page}.scene")) as fh:
                        scene = json.load(fh)
                    for node in scene["nodes"]:
                        if node.get("type") != "text":
                            continue
                        bind = node.get("bind") or ""
                        if "soc" not in bind:
                            continue
                        text, valid = scene_preview.resolve_value(node, state)
                        if not valid:
                            continue
                        resolved_counts += 1
                        if (not raw.get("soc_trusted", False) and
                                str(untrusted_soc) in text and
                                "rejected" not in text.lower()):
                            # The diagnostic screen is allowed to name the
                            # rejected value, but only while labelling it as
                            # rejected. Anywhere else it is a fabricated state.
                            printed.append(f"{page}/{state_name}:{node['id']}={text!r}")
            if printed:
                failures.append(
                    "an untrusted SOC was drawn: " + "; ".join(printed))
            else:
                print(f"  ok   no screen draws the untrusted {untrusted_soc} % "
                      f"({resolved_counts} live SOC texts checked)")

        if failures:
            print(f"\n{len(failures)} FAILED out of {renders} renders:")
            for failure in failures:
                print(f"  {failure}")
            return 1
        print(f"\nall {renders} page/state renders passed")
        return 0
    finally:
        shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
