#!/usr/bin/env python3
"""Safety and integrity rules for the DEV deployment tooling.

These are static checks on the scripts and the bundle contract, plus an
end-to-end dry run of the deploy script against a fake git state. They exist
because the failure mode they prevent is expensive: deploying an old prebuilt
library to a real car believing it is the current source, or writing somewhere
that is not reversible.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = ["scripts/deploy_dev_bundle.sh", "scripts/rollback_dev_bundle.sh",
           "scripts/package_dev_bundle.sh"]
FAILURES = []


def check(condition, label):
    if condition:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s" % label)
        FAILURES.append(label)


def read(path):
    with open(os.path.join(REPO, path)) as fh:
        return fh.read()


def main():
    print("scripts parse")
    for script in SCRIPTS:
        proc = subprocess.run(["bash", "-n", os.path.join(REPO, script)],
                              capture_output=True, text=True)
        check(proc.returncode == 0, f"{script} parses")

    print("no hardcoded device address")
    for script in SCRIPTS:
        text = read(script)
        addresses = re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text)
        check(not addresses,
              f"{script} contains no literal IP address ({addresses or 'none'})")
    for script in ("scripts/deploy_dev_bundle.sh",
                   "scripts/rollback_dev_bundle.sh"):
        text = read(script)
        check("ADB_SERIAL" in text or "adb devices" in text,
              f"{script} accepts an explicit target or discovers one")

    print("nothing is written outside /tmp")
    for script in SCRIPTS:
        text = read(script)
        for forbidden in ("/res/", "/late", "mtd", "flash_erase", "nandwrite"):
            writes = re.findall(r"(?:push|>|cp|mkdir|rm|dd)[^\n]*" + forbidden,
                                text)
            check(not writes, f"{script} never writes to {forbidden}")
    deploy = read("scripts/deploy_dev_bundle.sh")
    check("push" in deploy and "/tmp/" in deploy,
          "the deploy script pushes into /tmp")
    check("Refusing: expected a T113" in deploy,
          "the deploy script refuses a non-T113 target")

    print("integrity guard")
    check("source_commit" in read("scripts/package_dev_bundle.sh"),
          "the package records the source commit")
    check("artifact_sha256" in read("scripts/package_dev_bundle.sh"),
          "the package records the artifact hash")
    for phrase in ("SOURCE COMMIT", "ARTIFACT HASH", "BUILD MODE",
                   "ROLLBACK"):
        check(phrase in deploy,
              f"the deploy script prints {phrase} before installing")
    check("local_head" in deploy and "bundle_commit" in deploy,
          "the deploy script compares HEAD with the bundle commit")
    check("recorded_hash" in deploy and "actual_hash" in deploy,
          "the deploy script compares the artifact hash with the manifest")

    print("deploy dry run")
    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(REPO, "dist", "dev-bundle")
        artifact = os.path.join(bundle, "tesla-dashboard-mvp", "lib",
                                "libzkgui.so")
        if os.path.exists(artifact):
            head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
            proc = subprocess.run(
                ["bash", os.path.join(REPO, "scripts/deploy_dev_bundle.sh"),
                 "--serial", "FAKE:5555", "--dry-run"],
                capture_output=True, text=True)
            output = proc.stdout
            same = head in output
            check(proc.returncode == 0 and same,
                  "a dry run against the current bundle reports the local HEAD")
            check("ROLLBACK" in output,
                  "the dry run prints the rollback command")
        else:
            proc = subprocess.run(
                ["bash", os.path.join(REPO, "scripts/deploy_dev_bundle.sh"),
                 "--serial", "FAKE:5555", "--dry-run"],
                capture_output=True, text=True)
            check(proc.returncode != 0 and "No bundle" in (
                proc.stdout + proc.stderr),
                "without a bundle the deploy script refuses and says why")

    print("gear mapping safety")
    source = read("src/core/original_mcu_adapter.cpp")
    check("0x01" in source, "the parser still handles the 0x01 command")
    # The old claim "0x01 gear nibble 0=P/4=D" is REJECTED_MAPPING. Producing a
    # gear from it would put a fabricated gear on a real cluster.
    gear_from_0x01 = re.search(r">>\s*4[^\n]*Gear|Gear[^\n]*>>\s*4", source)
    check(gear_from_0x01 is None,
          "the parser does not derive gear from the rejected 0x01 nibble")
    device_display = read("device/flythings/display_format.cpp")
    check("REJECTED_MAPPING" in device_display,
          "the display layer records that the SOC mapping is rejected")
    check("always unavailable" in read("device/flythings/display_format.h").lower()
          or "always renders as unavailable"
          in read("device/flythings/display_format.h"),
          "the header states the SOC rule")

    print("")
    if FAILURES:
        print("%d FAILED: %s" % (len(FAILURES), "; ".join(FAILURES)))
        return 1
    print("all deploy safety checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
