#!/usr/bin/env python3
"""Every name a screen binds is a name the runtime produces, and vice versa.

The scenes are generated from one place and the runtime projection is written
in C++, so the two can drift: a renamed binding is not a compile error, it is a
widget that quietly draws its placeholder for the rest of the car's life. This
test closes that gap by comparing the two lists - the names the scenes use and
the names the projection offers - page by page, in both directions.

Usage:
    python3 tests/v6_binding_coverage_tests.py /path/to/dashboard_page_dump
"""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENES = os.path.join(REPO, "scenes")
PAGE_FILES = {
    "Horizon": "v6_horizon",
    "Mono": "v6_mono",
    "Pulse": "v6_pulse",
    "Route": "v6_route",
    "Studio": "v6_studio",
    "Energy": "v6_energy",
    "Nocturne": "v6_nocturne",
    "Settings": "v6_settings",
    "Developer": "v6_developer",
}

FAILURES = []


def check(condition, label):
    if condition:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s" % label)
        FAILURES.append(label)


def names_used_by_scene(path):
    """Every value name a scene reads: binds, conditions and bar fills."""
    with open(path) as fh:
        scene = json.load(fh)
    used = set()
    for node in scene.get("nodes", []):
        if node.get("bind"):
            used.add(node["bind"])
        for rule in node.get("text_when") or []:
            signal = (rule.get("when") or {}).get("signal")
            if signal:
                used.add(signal)
        for rule in node.get("rules") or []:
            signal = (rule.get("when") or {}).get("signal")
            if signal:
                used.add(signal)
        # Conditional alpha and colour also read a signal: a node that shows
        # itself only when navigation is valid is using navigation.
        for key in ("alpha_when", "color_when"):
            for rule in node.get(key) or []:
                signal = (rule.get("when") or {}).get("signal")
                if signal:
                    used.add(signal)
        for value in (node.get("visibility") or {}).values():
            if isinstance(value, str) and value and not value.endswith("_ms"):
                used.add(value)
        progress = node.get("progress")
        if isinstance(progress, dict) and progress.get("signal"):
            used.add(progress["signal"])
        for part in (node.get("parts") or {}).values():
            if part.get("bind"):
                used.add(part["bind"])
        for overlay in node.get("overlays") or []:
            if overlay.get("bind"):
                used.add(overlay["bind"])
        for indicator in (node.get("indicators") or {}).values():
            if indicator.get("bind"):
                used.add(indicator["bind"])
    return used


def main():
    if len(sys.argv) > 1:
        dump = sys.argv[1]
    else:
        dump = os.environ.get("DASHBOARD_PAGE_DUMP", "")
    if not dump or not os.path.exists(dump):
        sys.exit("usage: v6_binding_coverage_tests.py /path/to/dashboard_page_dump "
                 f"(got {dump!r})")

    raw = subprocess.check_output([dump], text=True)
    dump_json = json.loads(raw)
    pages = dump_json["pages"]

    # Horizon V2 is a candidate design for the same page. While it awaits human
    # approval the runtime offers the values both designs need, so the names it
    # adds are not "unused" - they are used by the V2 scene.
    v2_path = os.path.join(SCENES, "horizon_v2.scene")
    v2_names = names_used_by_scene(v2_path) if os.path.exists(v2_path) else set()

    check(set(pages) == set(PAGE_FILES),
          f"the runtime knows the same nine pages ({sorted(pages)})")

    total_names = 0
    for name, scene_id in sorted(PAGE_FILES.items()):
        scene_path = os.path.join(SCENES, scene_id + ".scene")
        used = names_used_by_scene(scene_path)
        offered = set(pages.get(name, {}).get("bindings", []))
        if scene_id == "v6_horizon":
            used_for_coverage = used | v2_names
        else:
            used_for_coverage = used
        total_names += len(used)
        missing = sorted(used - offered)
        unused = sorted(offered - used_for_coverage)
        check(not missing,
              f"{scene_id}: every bound name is produced by the projection "
              f"(missing: {missing or 'none'})")
        check(not unused,
              f"{scene_id}: the projection offers no unused name "
              f"(unused: {unused or 'none'})")

    check(pages["Developer"]["binding_count"] <= 18,
          "the developer page stays inside its larger live-text allowance")

    # The settings hit boxes live in C++ and the labels live in the scene. If
    # they drift, a driver taps "brightness" and changes something else.
    with open(os.path.join(SCENES, "v6_settings.scene")) as fh:
        settings_scene = json.load(fh)
    labels = {node["id"]: node for node in settings_scene["nodes"]
              if node.get("type") == "text" and node["id"].endswith(".label")}
    rows = dump_json["settings_rows"]
    check(len(rows) == 9, f"nine settings rows are declared ({len(rows)})")
    for row in rows:
        node = labels.get(row["label"] + ".label")
        if node is None:
            check(False, f"settings row {row['label']} has a matching scene label")
            continue
        inside = (row["x"] <= node["x"] <= row["x"] + row["width"] and
                  row["y"] <= node["y"] <= row["y"] + row["height"])
        check(inside,
              f"settings row {row['label']} contains its label at "
              f"({node['x']}, {node['y']})")
    print(f"checked {total_names} bound names across {len(PAGE_FILES)} pages")
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED: " + "; ".join(FAILURES))
        return 1
    print("\nall binding coverage checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
