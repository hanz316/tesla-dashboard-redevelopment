#!/usr/bin/env python3
"""Build reproducible manifests and compare two extracted firmware trees."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def manifest(root: Path) -> dict[str, dict[str, int | str]]:
    result: dict[str, dict[str, int | str]] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        result[relative] = {"size": path.stat().st_size, "sha256": digest(path)}
    return result


def compare(
    left_root: Path, right_root: Path
) -> dict[str, object]:
    left = manifest(left_root)
    right = manifest(right_root)
    left_names = set(left)
    right_names = set(right)
    shared = sorted(left_names & right_names)
    identical = [name for name in shared if left[name]["sha256"] == right[name]["sha256"]]
    changed = [name for name in shared if left[name]["sha256"] != right[name]["sha256"]]

    changed_details = {
        name: {"left": left[name], "right": right[name]} for name in changed
    }
    return {
        "left_root": str(left_root),
        "right_root": str(right_root),
        "summary": {
            "left_files": len(left),
            "right_files": len(right),
            "shared_files": len(shared),
            "identical_files": len(identical),
            "changed_files": len(changed),
            "left_only_files": len(left_names - right_names),
            "right_only_files": len(right_names - left_names),
        },
        "changed_by_top_directory": dict(
            sorted(Counter(name.split("/", 1)[0] for name in changed).items())
        ),
        "left_only": sorted(left_names - right_names),
        "right_only": sorted(right_names - left_names),
        "changed": changed_details,
        "left_manifest": left,
        "right_manifest": right,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    report = compare(args.left, args.right)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["changed_by_top_directory"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
