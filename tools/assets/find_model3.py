#!/usr/bin/env python3
"""Re-run the Tesla Model 3 asset search and flag licence/duplication risks.

Makes docs/MODEL3_ASSET_CANDIDATES.md reproducible instead of trusting a
pasted table. Queries the public Sketchfab v3 search API (no account
needed for metadata) and reports:

* each candidate with author, face count and licence URL
* duplicate meshes (same face/vertex count across accounts), which is the
  signature of a re-upload chain with unverifiable provenance
* red flags in descriptions (game rips, photogrammetry scans)

Downloading a model requires an authenticated Sketchfab account and is
deliberately NOT done here.

Usage:
    python3 tools/assets/find_model3.py
    python3 tools/assets/find_model3.py --json /tmp/candidates.json
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request

API = "https://api.sketchfab.com/v3/search"

# Phrases that disqualify a candidate regardless of the declared licence.
RED_FLAGS = {
    "game rip / mod extraction": ["beamng", "modland", "from a game", "assetto", "forza"],
    "photogrammetry scan": ["sitescape", "scan", "photogrammetry", "captured with"],
}


def search(query="tesla model 3", downloadable=True, count=24):
    params = {"type": "models", "q": query, "count": str(count)}
    if downloadable:
        params["downloadable"] = "true"
    url = f"{API}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def detail(uid):
    with urllib.request.urlopen(f"https://api.sketchfab.com/v3/models/{uid}",
                                timeout=20) as response:
        return json.load(response)


def flags_for(text):
    low = (text or "").lower()
    hits = []
    for label, needles in RED_FLAGS.items():
        if any(n in low for n in needles):
            hits.append(label)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="tesla model 3")
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--json")
    args = ap.parse_args()

    data = search(args.query, count=args.count)
    results = data.get("results", [])
    print(f"query={args.query!r} downloadable results={len(results)}")

    by_mesh = {}
    rows = []
    for m in results:
        uid = m["uid"]
        try:
            det = detail(uid)
        except Exception:
            det = m
        lic = det.get("license") or {}
        row = {
            "name": det.get("name"),
            "uid": uid,
            "creator": (det.get("user") or {}).get("displayName"),
            "faces": det.get("faceCount"),
            "verts": det.get("vertexCount"),
            "license": lic.get("label"),
            "license_url": lic.get("url"),
            "url": f"https://sketchfab.com/3d-models/{uid}",
            "red_flags": flags_for(det.get("description")),
        }
        rows.append(row)
        key = (row["faces"], row["verts"])
        if key[0]:
            by_mesh.setdefault(key, []).append(row["creator"])

    print("\n--- candidates ---")
    for r in rows:
        verdict = "OK"
        if r["red_flags"]:
            verdict = "EXCLUDE (" + ", ".join(r["red_flags"]) + ")"
        dup = by_mesh.get((r["faces"], r["verts"]), [])
        if len(dup) > 1:
            verdict = f"EXCLUDE (duplicate mesh on {len(dup)} accounts)"
        print(f"  {(r['name'] or '')[:30]:30} {(r['creator'] or '')[:16]:16} "
              f"faces={r['faces']:>8} lic={(r['license'] or '?')[:18]:18} {verdict}")

    dupes = {k: v for k, v in by_mesh.items() if len(v) > 1}
    if dupes:
        print("\n--- duplicate meshes (unverifiable provenance) ---")
        for (f, v), who in dupes.items():
            print(f"  faces={f} verts={v}: {len(who)} accounts -> "
                  f"{', '.join(w[:18] for w in who)}")

    usable = [r for r in rows
              if not r["red_flags"]
              and len(by_mesh.get((r["faces"], r["verts"]), [])) == 1
              and (r["license"] or "").startswith("CC")]
    print(f"\nusable CC-licensed, non-duplicate candidates: {len(usable)}")
    for r in usable:
        print(f"  - {r['name']} / {r['creator']} ({r['license']}) {r['url']}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"candidates": rows, "duplicates": {
                f"{k[0]}x{k[1]}": v for k, v in dupes.items()}}, fh, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
