#!/usr/bin/env python3
"""Download one versioned package from the public FlyThings repository."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath


BASE_URL = "https://package.flythings.cn"


def request_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def endpoint(platform: str, package: str, version: str, relative: str = "") -> str:
    components = [
        "api",
        "platforms",
        platform,
        "packages",
        package,
        "versions",
        version,
        "files",
    ]
    if relative:
        components.extend(PurePosixPath(relative).parts)
    return BASE_URL + "/" + "/".join(urllib.parse.quote(part) for part in components)


def list_directory(
    platform: str, package: str, version: str, relative: str
) -> list[dict[str, object]]:
    payload = json.loads(request_bytes(endpoint(platform, package, version, relative)))
    return payload["data"]["items"]


def download_tree(
    platform: str,
    package: str,
    version: str,
    destination: Path,
) -> list[dict[str, object]]:
    manifest: list[dict[str, object]] = []

    def walk(relative: str) -> None:
        for item in list_directory(platform, package, version, relative):
            name = str(item["name"])
            child = str(PurePosixPath(relative) / name) if relative else name
            if ".." in PurePosixPath(child).parts:
                raise ValueError(f"unsafe repository path: {child}")
            if bool(item.get("dir", False)):
                walk(child)
                continue
            data = request_bytes(endpoint(platform, package, version, child))
            target = destination / PurePosixPath(child)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest.append(
                {
                    "path": child,
                    "size": len(data),
                    "repository_size": item.get("size"),
                    "modified": item.get("modTime"),
                }
            )
            print(f"{child}\t{len(data)}")

    walk("")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform")
    parser.add_argument("package")
    parser.add_argument("version")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    args.destination.mkdir(parents=True, exist_ok=True)
    manifest = download_tree(
        args.platform, args.package, args.version, args.destination
    )
    metadata = {
        "source": BASE_URL,
        "platform": args.platform,
        "package": args.package,
        "version": args.version,
        "files": manifest,
    }
    (args.destination / "download-manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
