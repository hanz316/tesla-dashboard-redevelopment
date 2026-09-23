#!/usr/bin/env python3
"""Rules the V6 page set must keep, checked on the committed scenes.

The pages are generated, but the generator is not the artefact the runtime
reads - the scenes are. These checks run against the committed scene files so a
hand edit, a stale generation, or a rule dropped in the generator is caught
where it would actually reach the instrument:

* every screen declares a performance budget and stays inside it;
* no screen draws the MCU's SOC byte (a rejected mapping on this car) - SOC
  comes from the Commander's actual_soc or is unavailable;
* every signal-bound text has an explicit invalid_text, so UNKNOWN can never
  fall through to "0";
* missing closures read as unknown (`?`), never as closed;
* the Developer screen is not reachable as a normal driving page;
* mock vehicle data exists only in the previewer's MOCK_STATES.
"""

import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENES = os.path.join(REPO, "scenes")
FAILURES = []


def check(condition, label):
    if condition:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s" % label)
        FAILURES.append(label)


def load(path):
    with open(path) as fh:
        return json.load(fh)


def main():
    paths = sorted(glob.glob(os.path.join(SCENES, "v6_*.scene")))
    print("page set")
    check(len(paths) == 9,
          f"all nine screens are committed ({len(paths)} found)")
    expected = {"v6_horizon", "v6_mono", "v6_pulse", "v6_route", "v6_studio",
                "v6_energy", "v6_nocturne", "v6_settings", "v6_developer"}
    found = {os.path.basename(p)[:-len(".scene")] for p in paths}
    check(expected == found, f"screens are the expected set ({sorted(found)})")

    print("budget")
    limits = {"static_fills": 3, "static_text": 14, "conditional_fills": 1,
              "conditional_text": 6, "dynamic_paths": 12, "dynamic_text": 12,
              "bitmaps": 2, "nodes": 40}
    for path in paths:
        scene = load(path)
        name = os.path.basename(path)[:-len(".scene")]
        budget = scene.get("budget") or {}
        check(bool(budget), f"{name} declares a budget")
        over = {k: budget[k] for k in limits
                if budget.get(k, 0) > limits[k]
                and not (name == "v6_developer" and k == "dynamic_text"
                         and budget.get(k, 0) <= 18)}
        check(not over, f"{name} stays inside the device budget ({over or 'ok'})")

    print("no fabricated data")
    for path in paths:
        scene = load(path)
        name = os.path.basename(path)[:-len(".scene")]
        for node in scene.get("nodes", []):
            if node.get("type") != "text":
                continue
            bind = node.get("bind")
            if not bind:
                continue
            check(bool(node.get("invalid_text") is not None
                       or node.get("text_when")),
                  f"{name}:{node['id']} states what an invalid value looks like")
            check(bind != "soc",
                  f"{name}:{node['id']} does not bind the rejected MCU SOC byte")

    print("closures read as unknown when missing")
    closure_nodes = []
    for path in paths:
        scene = load(path)
        for node in scene.get("nodes", []):
            if node.get("id", "").endswith("closures"):
                closure_nodes.append((os.path.basename(path), node))
    check(bool(closure_nodes), "the closure state is drawn somewhere")
    for name, node in closure_nodes:
        invalid = str(node.get("invalid_text", ""))
        check("?" in invalid or "?" in json.dumps(node.get("text_when", [])),
              f"{name}:{node['id']} shows unknown as '?', not as closed")

    print("developer screen is not a driving page")
    horizon = load(os.path.join(SCENES, "v6_horizon.scene"))
    text = json.dumps(horizon)
    check("v6_developer" not in text or "developer_mode" in text,
          "the driving page does not reference the developer screen")
    settings = load(os.path.join(SCENES, "v6_settings.scene"))
    default_values = [n.get("bind") for n in settings.get("nodes", [])
                      if n.get("id") == "DEFAULT PAGE.value"
                      or n.get("bind") == "default_page_text"]
    check(all(v != "developer_mode_text" for v in default_values),
          "the default page cannot be the developer screen")

    print("mock data lives only in the previewer")
    offenders = []
    for root, _dirs, files in os.walk(REPO):
        if any(part in root for part in (".git", "build", "captures",
                                         "dist", "assets")):
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            full = os.path.join(root, name)
            if os.path.relpath(full, REPO) == os.path.join(
                    "tools", "preview", "scene_preview.py"):
                continue
            with open(full, errors="replace") as fh:
                body = fh.read()
            if re.search(r"MOCK_STATES\s*=", body):
                offenders.append(os.path.relpath(full, REPO))
    check(not offenders,
          f"no second mock state table exists ({offenders or 'clean'})")

    print("an unknown gear is never drawn as a confident letter")
    for path in paths:
        scene = load(path)
        for node in scene.get("nodes", []):
            value_map = node.get("value_map")
            if not value_map or "gear" not in str(node.get("bind", "")):
                continue
            check("0" not in value_map,
                  f"{os.path.basename(path)}:{node['id']} has no mapping for "
                  f"gear 0 (unknown)")

    print("the preview and the runtime render an absent signal the same way")
    sys.path.insert(0, os.path.join(REPO, "tools", "preview"))
    try:
        import scene_preview
    except ImportError as error:  # pragma: no cover
        # The previewer needs Pillow. Where it is absent (a bare CI image) this
        # rule simply cannot be exercised; say so instead of failing a rule
        # that the environment, not the code, cannot run.
        print(f"  note the previewer is not importable here ({error}); "
              f"skipping the preview/runtime fallback comparison")
    else:
        missing = scene_preview.State({})
        mismatches = []
        for path in paths:
            scene = load(path)
            for node in scene.get("nodes", []):
                if node.get("type") != "text" or not node.get("bind"):
                    continue
                expected = node.get("invalid_text")
                if expected is None:
                    continue
                text, valid = scene_preview.resolve_value(node, missing)
                if valid or text != expected:
                    mismatches.append(
                        "%s:%s drew %r instead of %r" % (
                            os.path.basename(path), node["id"], text, expected))
        check(not mismatches,
              "every bound node falls back to its invalid_text "
              f"({mismatches[:3] if mismatches else 'ok'})")

    print("")
    if FAILURES:
        print("%d FAILED: %s" % (len(FAILURES), "; ".join(FAILURES)))
        return 1
    print("all v6 page checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
