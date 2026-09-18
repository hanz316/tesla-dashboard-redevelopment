#!/usr/bin/env python3
"""Cross-check the runtime's asset ids against the asset manifest.

The controller decides which layers to draw; the manifest decides where those
layers live. Nothing in either file forces them to agree, so this test does:
every asset id the C++ controller can emit must exist in assets/manifest.json,
every id in the manifest must resolve to a real file under the production
source root, and every id the Horizon scenes reference must resolve too.

Runs on the host, no Blender required.
"""

import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools", "preview"))

FAILURES = []


def check(condition, label):
    if condition:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s" % label)
        FAILURES.append(label)


def controller_layer_ids():
    path = os.path.join(REPO, "src", "core", "vehicle_visual_controller.cpp")
    with open(path) as fh:
        text = fh.read()
    return sorted(set(re.findall(r'"(vehicle\.[a-z.]+)"', text)))


def main():
    manifest_path = os.path.join(REPO, "assets", "manifest.json")
    with open(manifest_path) as fh:
        manifest = json.load(fh)
    known = set(manifest.get("images", {}))
    known |= set(manifest.get("overlays", {}))
    known |= set(manifest.get("sequences", {}))
    print("asset manifest")
    check(bool(known), "the manifest declares assets (%d ids)" % len(known))
    layers = controller_layer_ids()
    check(bool(layers), "the controller names its layers (%d ids)" % len(layers))
    missing = [layer for layer in layers if layer not in known]
    check(not missing,
          "every layer the controller can draw exists in the manifest (%s)"
          % (missing or "all resolve"))
    print("  controller layers:", ", ".join(layers))

    print("production source")
    from vehicle_asset_provider import VehicleAssetProvider
    provider = VehicleAssetProvider(REPO, manifest)
    provider.resolve(allow_placeholder=False)
    check(provider.selected == "RENDERED_MODEL3",
          "the production source is the rendered Model A set, not placeholder")

    print("asset and Horizon reference checks")
    script = os.path.join(REPO, "tools", "assets",
                          "check_vehicle_state_assets.py")
    out = os.path.join(REPO, "assets", "checkpoints", "vehicle_state_assets",
                       "vehicle_state_manifest_check.json")
    proc = subprocess.run([sys.executable, script, "--out", out],
                          capture_output=True, text=True)
    check(proc.returncode == 0,
          "the manifest/Horizon check passes (%s)"
          % (proc.stdout.strip().splitlines()[-1] if proc.stdout else "no output"))
    if os.path.exists(out):
        with open(out) as fh:
            report = json.load(fh)
        check(not report["missing"], "no manifest entry is a missing file")
        check(not report["canvas_mismatch"],
              "every frame has the declared canvas")
        check(all(h["pass"] for h in report["horizon"].values()),
              "every Horizon scene asset reference resolves")
        check(report["production_mode_ok"],
              "production mode refuses placeholder vehicle art")
        peak = report["composed_path"]["peak_decoded_rgba_bytes"]
        full = 1920 * 480 * 4
        check(peak < full * 2,
              "peak decoded RGBA stays under two full-screen frames "
              "(%.2f MB vs %.2f MB)" % (peak / 1048576.0, full / 1048576.0))

    print("")
    if FAILURES:
        print("%d FAILED: %s" % (len(FAILURES), "; ".join(FAILURES)))
        return 1
    print("all vehicle asset manifest checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
