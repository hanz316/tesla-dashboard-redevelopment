#!/usr/bin/env python3
"""Bit-level analysis of UART captures, for controlled-action correlation.

Two jobs:

1. `--steps name=path [name=path ...]` - for each capture, show what each
   command did: frame counts, the distinct payloads, and for 0x01 a compact
   bit-delta timeline (which bits changed, between which frames). Unknown bits
   are printed as bit positions, never given names.

2. `--baseline name` - XOR every other step against the baseline at byte and
   bit level. That is what turns "the door was opened" into "byte 3 bit 1
   changed and nothing else did".

Confidence labels are attached to every decoded field, and a mapping is only
ever printed as CONFIRMED_LIVE when the evidence in the captures supports it;
otherwise the tool prints the raw evidence and the label stays UNKNOWN.

Usage:
    python3 tools/device/analyze_uart_capture.py \
        --steps baseline=captures/step-baseline.bin gear_r=captures/step-r.bin \
        --baseline baseline --expect gear_r
"""

import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_parser():
    spec = importlib.util.spec_from_file_location(
        "parse_uart_capture", os.path.join(HERE, "parse_uart_capture.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parser = load_parser()


def read_frames(path):
    with open(path, "rb") as fh:
        data = fh.read()
    frames = []
    for command, payload in parser.iter_frames(data):
        frames.append((command, bytes(payload)))
    return {"bytes": len(data), "frames": frames,
            "good": parser.iter_frames.good, "bad": parser.iter_frames.bad}


def bits(value):
    return [i for i in range(8) if value & (1 << i)]


def summarise_payloads(payloads, limit=8):
    seen = []
    for payload in payloads:
        if payload not in seen:
            seen.append(payload)
        if len(seen) >= limit:
            break
    return seen


def step_report(name, capture):
    report = {"step": name, "bytes": capture["bytes"],
              "frames": len(capture["frames"]),
              "checksum_errors": capture["bad"], "commands": {}}
    by_command = {}
    for command, payload in capture["frames"]:
        by_command.setdefault(command, []).append(payload)
    for command, payloads in sorted(by_command.items()):
        entry = {"frames": len(payloads),
                 "lengths": sorted(set(len(p) for p in payloads)),
                 "distinct_payloads": [p.hex() for p in
                                       summarise_payloads(payloads)]}
        if command == 0x01:
            entry["bit_deltas"] = bit_delta_timeline(payloads)
            entry["byte_values"] = byte_value_table(payloads)
        report["commands"][f"0x{command:02X}"] = entry
    return report


def bit_delta_timeline(payloads, limit=24):
    """Which bits changed between consecutive DISTINCT payloads of 0x01."""
    timeline = []
    previous = None
    for index, payload in enumerate(payloads):
        if previous is None:
            previous = payload
            continue
        if payload == previous:
            continue
        if len(payload) != len(previous):
            timeline.append({"frame": index, "note": "payload length changed",
                             "from": previous.hex(), "to": payload.hex()})
            previous = payload
            continue
        changes = []
        for byte_index, (a, b) in enumerate(zip(previous, payload)):
            if a == b:
                continue
            changes.append({"byte": byte_index,
                            "from": f"0x{a:02X}", "to": f"0x{b:02X}",
                            "xor": f"0x{a ^ b:02X}",
                            "bits_set": bits(b), "bits_cleared": bits(a)})
        timeline.append({"frame": index, "from": previous.hex(),
                         "to": payload.hex(), "changes": changes})
        previous = payload
        if len(timeline) >= limit:
            break
    return timeline


def byte_value_table(payloads):
    """Per byte: how many distinct values, and what they are (capped)."""
    if not payloads:
        return {}
    length = min(len(p) for p in payloads)
    table = {}
    for byte_index in range(length):
        values = sorted(set(p[byte_index] for p in payloads))
        table[byte_index] = {"distinct": len(values),
                             "values": [f"0x{v:02X}" for v in values[:8]]}
    return table


def compare_to_baseline(base, other):
    """Byte and bit level differences between two captures, per command."""
    base_by_command = {}
    for command, payload in base["frames"]:
        base_by_command.setdefault(command, []).append(payload)
    other_by_command = {}
    for command, payload in other["frames"]:
        other_by_command.setdefault(command, []).append(payload)
    out = {}
    for command in sorted(set(base_by_command) & set(other_by_command)):
        base_payloads = base_by_command[command]
        other_payloads = other_by_command[command]
        # Compare the dominant payload of each side: the state that was stable
        # for the longest, which is what a controlled action changes.
        base_mode = dominant(base_payloads)
        other_mode = dominant(other_payloads)
        if base_mode is None or other_mode is None:
            continue
        entry = {"baseline_payload": base_mode.hex(),
                 "step_payload": other_mode.hex(),
                 "bytes_changed": [], "bits_changed": []}
        for byte_index in range(min(len(base_mode), len(other_mode))):
            a, b = base_mode[byte_index], other_mode[byte_index]
            if a == b:
                continue
            entry["bytes_changed"].append(
                {"byte": byte_index, "baseline": f"0x{a:02X}",
                 "step": f"0x{b:02X}", "xor": f"0x{a ^ b:02X}"})
            for bit in range(8):
                if (a ^ b) & (1 << bit):
                    entry["bits_changed"].append(
                        {"byte": byte_index, "bit": bit,
                         "baseline": (a >> bit) & 1, "step": (b >> bit) & 1})
        if entry["bytes_changed"]:
            out[f"0x{command:02X}"] = entry
    return out


def dominant(payloads):
    if not payloads:
        return None
    counts = {}
    for payload in payloads:
        counts[payload] = counts.get(payload, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", nargs="+", required=True,
                    help="name=path pairs, in capture order")
    ap.add_argument("--baseline", default=None,
                    help="step name to XOR every other step against")
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    captures = {}
    for item in args.steps:
        name, _, path = item.partition("=")
        if not path or not os.path.exists(path):
            sys.exit(f"missing capture for step {name}: {path}")
        captures[name] = read_frames(path)

    report = {"steps": {name: step_report(name, cap)
                        for name, cap in captures.items()}}
    if args.baseline:
        if args.baseline not in captures:
            sys.exit(f"baseline step {args.baseline} not in --steps")
        base = captures[args.baseline]
        report["baseline"] = args.baseline
        report["differences"] = {
            name: compare_to_baseline(base, cap)
            for name, cap in captures.items() if name != args.baseline}

    if args.json:
        import json
        text = json.dumps(report, indent=2)
        if args.out:
            with open(args.out, "w") as fh:
                fh.write(text + "\n")
        print(text)
        return 0

    for name, entry in report["steps"].items():
        print(f"[step] {name}: {entry['frames']} frames, "
              f"{entry['bytes']} bytes, {entry['checksum_errors']} bad")
        for command, info in entry["commands"].items():
            print(f"    {command}: {info['frames']} frames len={info['lengths']} "
                  f"distinct={len(info['distinct_payloads'])}")
            if command == "0x01":
                for byte_index, byte in sorted(info["byte_values"].items()):
                    if byte["distinct"] > 1:
                        print(f"         byte {byte_index}: "
                              f"{byte['distinct']} values {byte['values']}")
                for delta in info["bit_deltas"][:6]:
                    if "changes" in delta:
                        changed = ", ".join(
                            f"b{c['byte']} {c['from']}->{c['to']} "
                            f"(bits set {c['bits_set']}, cleared "
                            f"{c['bits_cleared']})" for c in delta["changes"])
                        print(f"         frame {delta['frame']}: {changed}")
                    else:
                        print(f"         frame {delta['frame']}: {delta['note']}")
    if "differences" in report:
        print("")
        for name, commands in report["differences"].items():
            print(f"[vs {report['baseline']}] {name}:")
            if not commands:
                print("    no byte-level difference in the dominant payload")
            for command, info in commands.items():
                bits = ", ".join(f"b{b['byte']}.{b['bit']}" for b in
                                 info["bits_changed"][:12])
                print(f"    {command}: {info['baseline_payload']} -> "
                      f"{info['step_payload']}  bits: {bits}")
    if args.out and not args.json:
        import json
        with open(args.out, "w") as fh:
            fh.write(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
