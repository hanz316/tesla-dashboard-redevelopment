#!/usr/bin/env python3
"""Report the part structure of a vehicle model WITHOUT Blender.

Answers the pipeline's first question: "are the doors / frunk / trunk /
wheels already separate objects?" — by reading the file's own hierarchy.

Supported without Blender:
    .glb  (binary glTF container)
    .gltf (JSON glTF, with .bin sibling)
    .obj  (o / g / usemtl groups)

For .fbx / .blend, run inside Blender:
    blender -b -P tools/blender/part_report.py -- --input <file>

Usage:
    python3 tools/assets/inspect_model.py <model.glb>
    python3 tools/assets/inspect_model.py <model.glb> --json report.json
"""

import argparse
import json
import os
import struct
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAPPING_PATH = os.path.join(REPO_ROOT, "tools", "assets", "part_mapping.json")


def load_mapping():
    with open(MAPPING_PATH) as fh:
        return json.load(fh)


def classify(name, mapping):
    """Return (canonical, confidence) for a node/mesh name."""
    low = name.lower()
    for canonical, tokens in mapping["mappings"].items():
        for token in tokens:
            if token in low:
                return canonical, "high" if len(token) >= 6 else "medium"
    if "door" in low:
        return None, "ambiguous-door"
    if "wheel" in low or "tyre" in low or "tire" in low:
        return None, "ambiguous-wheel"
    if "light" in low or "lamp" in low:
        return None, "ambiguous-light"
    return None, "unmapped"


# ------------------------------------------------------------------ formats

def names_from_glb(path):
    with open(path, "rb") as fh:
        magic, version, _length = struct.unpack("<III", fh.read(12))
        if magic != 0x46546C67:
            raise ValueError("not a GLB file")
        while True:
            header = fh.read(8)
            if len(header) < 8:
                break
            chunk_len, chunk_type = struct.unpack("<II", header)
            data = fh.read(chunk_len)
            if chunk_type == 0x4E4F534A:  # JSON
                return json.loads(data.decode("utf-8"))
    raise ValueError("no JSON chunk in GLB")


def names_from_gltf(path):
    with open(path) as fh:
        return json.load(fh)


def names_from_gltf_doc(doc):
    nodes = [n.get("name", f"node_{i}") for i, n in enumerate(doc.get("nodes", []))]
    meshes = [m.get("name", f"mesh_{i}") for i, m in enumerate(doc.get("meshes", []))]
    materials = [m.get("name", f"mat_{i}") for i, m in enumerate(doc.get("materials", []))]
    return nodes, meshes, materials


def names_from_obj(path):
    objects, groups, materials = [], [], []
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("o "):
                objects.append(line[2:].strip())
            elif line.startswith("g "):
                groups.append(line[2:].strip())
            elif line.startswith("usemtl "):
                materials.append(line[7:].strip())
    return objects or groups, groups, sorted(set(materials))


# ------------------------------------------------------------------- report

def build_report(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".glb":
        nodes, meshes, materials = names_from_gltf_doc(names_from_glb(path))
        fmt = "glb"
    elif ext == ".gltf":
        nodes, meshes, materials = names_from_gltf_doc(names_from_gltf(path))
        fmt = "gltf"
    elif ext == ".obj":
        nodes, meshes, materials = names_from_obj(path)
        fmt = "obj"
    else:
        sys.exit(f"unsupported format '{ext}' here — for .fbx/.blend run:\n"
                 f"  blender -b -P tools/blender/part_report.py -- --input {path}")

    mapping = load_mapping()
    canonical = mapping["canonical_parts"]

    found = {}
    ambiguous = []
    unmapped = []
    for name in nodes:
        canonical_name, confidence = classify(name, mapping)
        if canonical_name:
            found.setdefault(canonical_name, []).append(name)
        elif confidence.startswith("ambiguous"):
            ambiguous.append((name, confidence))
        else:
            unmapped.append(name)

    missing = [c for c in canonical if c not in found]
    coverable = [c for c in missing if c in ("Frunk", "Trunk")]

    report = {
        "file": os.path.relpath(path, REPO_ROOT),
        "format": fmt,
        "node_count": len(nodes),
        "mesh_count": len(meshes),
        "material_count": len(materials),
        "materials": materials[:40],
        "parts_found": {k: v for k, v in sorted(found.items())},
        "missing_parts": missing,
        "ambiguous": [{"name": n, "reason": r} for n, r in ambiguous],
        "unmapped": unmapped[:60],
        "readiness": {
            "doors_separated": all(
                c in found for c in ("Door_FL", "Door_FR", "Door_RL", "Door_RR")),
            "frunk_separated": "Frunk" in found,
            "trunk_separated": "Trunk" in found,
            "wheels_separated": all(
                c in found for c in ("Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR")),
            "glass_separated": "Glass" in found,
            "interior_present": "Interior" in found,
        },
    }
    return report, coverable


def print_report(report, coverable):
    print(f"file          : {report['file']} ({report['format']})")
    print(f"nodes/meshes  : {report['node_count']} / {report['mesh_count']}")
    print(f"materials     : {report['material_count']}")
    print()
    print("parts already separated:")
    if report["parts_found"]:
        for k, v in report["parts_found"].items():
            print(f"  ✓ {k:14} <- {', '.join(v[:3])}")
    else:
        print("  (none matched)")
    print()
    print("missing: " + (", ".join(report["missing_parts"]) or "none"))
    if coverable:
        print(f"  note: {', '.join(coverable)} often is not a separate mesh on "
              f"aftermarket scans and needs manual split")
    if report["ambiguous"]:
        print("\nambiguous (need manual review, never auto-split):")
        for a in report["ambiguous"][:12]:
            print(f"  ? {a['name']}  ({a['reason']})")
    if report["unmapped"]:
        print(f"\nunmapped nodes: {len(report['unmapped'])} "
              f"(e.g. {', '.join(report['unmapped'][:6])})")
    print()
    r = report["readiness"]
    print("animation readiness:")
    for k, v in r.items():
        print(f"  {'PASS' if v else 'NEEDS WORK':11} {k}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json", help="also write the report as JSON")
    args = ap.parse_args()
    report, coverable = build_report(args.path)
    print_report(report, coverable)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"\nwrote {args.json}")
    return 0 if report["readiness"]["doors_separated"] else 1


if __name__ == "__main__":
    sys.exit(main())
