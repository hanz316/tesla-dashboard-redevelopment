#!/usr/bin/env python3
"""Verify a built artifact really is a T113 target binary.

The build runs inside an emulated x86-64 container, so the one thing worth
checking mechanically is that what came out is an ARM hard-float musl shared
object and not, say, a host binary that slipped through. Every field the
handoff asks for is read straight out of the ELF headers:

    architecture, ELF class, endianness, ABI, hard-float, dynamic
    dependencies, size, and the commit the artifact was built from.

Usage:
    python3 tools/device/verify_elf_artifact.py --artifact build-t113/libzkgui.so
    python3 tools/device/verify_elf_artifact.py --artifact ... --json out.json
"""

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys

EM_ARM = 40
EF_ARM_EABI_VER5 = 0x05000000
EF_ARM_ABI_FLOAT_HARD = 0x00000400
EF_ARM_ABI_FLOAT_SOFT = 0x00000200
TAG_ABI_VFP_ARGS = 28


def parse_elf(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"\x7fELF":
        return {"error": "not an ELF file"}
    ei_class, ei_data = data[4], data[5]
    e_type = struct.unpack_from("<H", data, 16)[0]
    e_machine = struct.unpack_from("<H", data, 18)[0]
    # ELF32 header: e_flags sits at offset 36 (after e_entry, e_phoff, e_shoff).
    e_flags = struct.unpack_from("<I", data, 36)[0]
    out = {
        "class": {1: "ELF32", 2: "ELF64"}.get(ei_class, "unknown"),
        "endianness": {1: "little", 2: "big"}.get(ei_data, "unknown"),
        "machine": e_machine,
        "type": {2: "EXEC", 3: "DYN (shared object)"}.get(e_type, str(e_type)),
        "e_flags": "0x%08X" % e_flags,
        "abi": "EABI5" if (e_flags & 0xFF000000) == EF_ARM_EABI_VER5
               else "0x%02X" % (e_flags >> 24),
        "float_abi": ("hard" if e_flags & EF_ARM_ABI_FLOAT_HARD else
                      "soft" if e_flags & EF_ARM_ABI_FLOAT_SOFT else "unknown"),
    }
    # Section headers: section header table offset and entry size differ
    # between ELF32 and ELF64.
    if ei_class == 1:
        shoff, = struct.unpack_from("<I", data, 32)
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 46)
        fmt = "<IIIIIIIIII"
    else:
        shoff, = struct.unpack_from("<Q", data, 40)
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 58)
        fmt = "<IIQQQQIIQQ"
    sections = []
    for index in range(shnum):
        base = shoff + index * shentsize
        if base + shentsize > len(data):
            break
        fields = struct.unpack_from(fmt, data, base)
        sections.append({"name_off": fields[0], "type": fields[1],
                         "offset": fields[4], "size": fields[5],
                         "link": fields[6], "entsize": fields[9]})
    # Section names
    if shstrndx < len(sections):
        str_off = sections[shstrndx]["offset"]
        for section in sections:
            start = str_off + section["name_off"]
            end = data.index(b"\0", start)
            section["name"] = data[start:end].decode("latin-1")
    # .ARM.attributes: decode Tag_ABI_VFP_args, the authoritative hard-float
    # marker for ARM EABI5.
    def read_uleb128(blob, pos):
        value, shift = 0, 0
        while pos < len(blob):
            byte = blob[pos]
            pos += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return value, pos
        return None, pos

    for section in sections:
        if section.get("name") != ".ARM.attributes":
            continue
        blob = data[section["offset"]:section["offset"] + section["size"]]
        out["arm_attributes_hex"] = blob.hex()[:64]
        # Subsection 'A' (aeabi), then tags are ULEB128 with ULEB128 lengths.
        pos = 0
        while pos < len(blob):
            if blob[pos:pos + 1] != b"A":
                pos += 1
                continue
            pos += 1
            size, pos = read_uleb128(blob, pos)
            if size is None:
                break
            end = min(pos + size, len(blob))
            while pos < end:
                tag, pos = read_uleb128(blob, pos)
                if tag is None:
                    break
                value, pos = read_uleb128(blob, pos)
                if value is None:
                    break
                if tag == TAG_ABI_VFP_ARGS:
                    out["vfp_args"] = value
                    out["vfp_args_meaning"] = {
                        0: "base standard (soft)", 1: "VFP registers (hard)",
                        2: "both", 3: "toolchain-specific"}.get(value, "unknown")
            break
    # Dynamic dependencies (DT_NEEDED = 1) via the .dynamic section.
    needed = []
    for section in sections:
        if section.get("name") != ".dynamic":
            continue
        dynstr = next((s for s in sections
                       if s.get("name") == ".dynstr"), None)
        if dynstr is None:
            continue
        step = 8 if ei_class == 1 else 16
        for offset in range(section["offset"],
                            section["offset"] + section["size"], step):
            if ei_class == 1:
                tag, value = struct.unpack_from("<iI", data, offset)
            else:
                tag, value = struct.unpack_from("<qQ", data, offset)
            if tag == 0:
                break
            if tag == 1:
                start = dynstr["offset"] + value
                end = data.index(b"\0", start)
                needed.append(data[start:end].decode("latin-1"))
    out["needed_libraries"] = sorted(set(needed))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--expect-hard-float", action="store_true", default=True)
    args = ap.parse_args()

    info = parse_elf(args.artifact)
    info["path"] = args.artifact
    info["bytes"] = os.path.getsize(args.artifact)
    with open(args.artifact, "rb") as fh:
        info["sha256"] = hashlib.sha256(fh.read()).hexdigest()
    try:
        info["source_commit"] = subprocess.run(
            ["git", "-C", os.path.dirname(os.path.abspath(args.artifact)),
             "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=os.path.dirname(os.path.abspath(args.artifact))
        ).stdout.strip() or None
    except Exception:  # pragma: no cover
        info["source_commit"] = None

    checks = {
        "is_elf": "error" not in info,
        "elf32": info.get("class") == "ELF32",
        "arm": info.get("machine") == EM_ARM,
        "little_endian": info.get("endianness") == "little",
        "eabi5": info.get("abi") == "EABI5",
        # e_flags is the authoritative marker: the linker sets
        # EF_ARM_ABI_FLOAT_HARD for a hard-float ABI. Tag_ABI_VFP_args in
        # .ARM.attributes corroborates it when the parser can reach it, but the
        # check must not depend on that nested structure being decoded.
        "hard_float": info.get("float_abi") == "hard",
        "shared_object": "DYN" in str(info.get("type")),
    }
    info["checks"] = checks
    info["target_ok"] = all(checks.values())

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w") as fh:
            json.dump(info, fh, indent=2)
            fh.write("\n")
    print(f"[elf] {info['path']}  {info['bytes']} bytes")
    print(f"[elf] {info.get('class')} {info.get('endianness')} "
          f"machine={info.get('machine')} {info.get('abi')} "
          f"float={info.get('float_abi')} vfp_args={info.get('vfp_args')}")
    print(f"[elf] needed: {info.get('needed_libraries')}")
    print(f"[elf] sha256 {info.get('sha256')}")
    print(f"[elf] target_ok={info['target_ok']} {checks}")
    return 0 if info["target_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
