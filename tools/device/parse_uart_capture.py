#!/usr/bin/env python3
"""Decode a raw /dev/ttyS5 capture with the documented MCU protocol.

Frame: 0x2E | CMD | LEN | PAYLOAD[LEN] | CHECKSUM
Checksum: ~(CMD + LEN + sum(PAYLOAD)) & 0xFF

Only the CONFIRMED and LIKELY decodings from docs/protocol-table.md are
reported, and every field carries its evidence level so a LIKELY bit can never
be read as a confirmed vehicle state. The parser resynchronises on the header
and counts checksum failures rather than silently trusting bytes.

Self-test:
    python3 tools/device/parse_uart_capture.py --self-test

Real capture:
    python3 tools/device/parse_uart_capture.py --input captures/uart-record-*.bin \
        --out captures/uart-decode.json
"""

import argparse
import json
import os
import struct
import sys

HEADER = 0x2E


def checksum(command, payload):
    return (~(command + len(payload) + sum(payload))) & 0xFF


def build_frame(command, payload):
    return bytes([HEADER, command, len(payload)]) + bytes(payload) + \
        bytes([checksum(command, payload)])


def iter_frames(data):
    """Yield (command, payload) for every checksum-valid frame.

    Resynchronises byte by byte after a failure: a UART capture starts
    mid-stream, so the first partial frame must be skipped rather than treated
    as corruption.
    """
    index = 0
    good = bad = 0
    while index < len(data):
        if data[index] != HEADER:
            index += 1
            continue
        if index + 3 > len(data):
            break
        command = data[index + 1]
        length = data[index + 2]
        end = index + 3 + length
        if end >= len(data):
            # Either a torn frame at the end of the capture, or a false header
            # inside a payload. Advancing one byte and resyncing is what makes
            # the parser survive the latter; stopping here would abandon the
            # rest of the stream after a single mis-sync.
            if index + 4 > len(data):
                break
            index += 1
            continue
        payload = data[index + 3:end]
        expected = data[end]
        if checksum(command, payload) == expected:
            good += 1
            yield command, payload
            index = end + 1
        else:
            bad += 1
            index += 1
    iter_frames.good = good
    iter_frames.bad = bad


def le16(payload, offset):
    if len(payload) < offset + 2:
        return None
    return struct.unpack_from("<H", bytes(payload), offset)[0]


def decode(state, command, payload):
    entry = state.setdefault(command, {"frames": 0, "samples": {}})
    entry["frames"] += 1
    samples = entry["samples"]

    def record(field, value, evidence):
        slot = samples.setdefault(field, {"evidence": evidence, "values": []})
        slot["values"].append(value)
        if len(slot["values"]) > 512:
            del slot["values"][0]

    if command == 0x04:
        speed = le16(payload, 0)
        if speed is not None:
            record("speed_raw", speed, "CONFIRMED")
        rng = le16(payload, 6)
        if rng is not None:
            record("range_raw", rng, "CONFIRMED")
        if len(payload) > 8:
            record("soc_percent", payload[8], "CONFIRMED (known-bad on this car)")
    elif command == 0x12:
        if len(payload) >= 5:
            for i in range(4):
                record(f"tire_{i}_bar", round(payload[1 + i] * 0.025, 4),
                       "CONFIRMED value, NEEDS REAL CAR TEST for wheel order")
    elif command == 0x01:
        if len(payload) > 4:
            gear_nibble = payload[4] >> 4
            record("gear_nibble", gear_nibble,
                   "CONFIRMED (0=P, 4=D)")
        if len(payload) > 3:
            bits = payload[3]
            record("payload3_bits", bits, "LIKELY")
    elif command == 0x07:
        if len(payload) > 0:
            record("temperature_primary_c", (payload[0] >> 1) - 40, "LIKELY")
        if len(payload) > 1:
            record("temperature_secondary_c", payload[1] - 25, "LIKELY")
    else:
        record("payload_length", len(payload), "UNKNOWN mapping")
    return entry


def summarise(state):
    out = {}
    for command, entry in sorted(state.items()):
        fields = {}
        for field, slot in sorted(entry["samples"].items()):
            values = slot["values"]
            if not values:
                continue
            fields[field] = {
                "evidence": slot["evidence"],
                "samples": len(values),
                "first": values[0],
                "last": values[-1],
                "min": min(values),
                "max": max(values),
                "distinct": len(set(values)),
            }
        out[f"0x{command:02X}"] = {"frames": entry["frames"], "fields": fields}
    return out


def self_test():
    frames = b"".join([
        build_frame(0x04, [10, 0, 0, 0, 0, 0, 253, 0, 63, 0, 1, 2, 3]),
        build_frame(0x12, [0, 200, 198, 205, 202]),
        build_frame(0x01, [0, 0, 0, 0x01, 0x40, 0]),
        b"\x00\x01\x02",                        # garbage before a resync
        build_frame(0x07, [128, 45]),
        build_frame(0x04, [10, 0])[:-1],        # torn frame
    ])
    state = {}
    for command, payload in iter_frames(frames):
        decode(state, command, payload)
    summary = summarise(state)
    assert iter_frames.good == 4, iter_frames.good
    assert iter_frames.bad == 0, iter_frames.bad
    assert summary["0x04"]["fields"]["speed_raw"]["last"] == 10
    assert summary["0x04"]["fields"]["range_raw"]["last"] == 253
    assert summary["0x04"]["fields"]["soc_percent"]["last"] == 63
    assert abs(summary["0x12"]["fields"]["tire_0_bar"]["last"] - 5.0) < 1e-6
    assert summary["0x01"]["fields"]["gear_nibble"]["last"] == 4
    assert summary["0x07"]["fields"]["temperature_primary_c"]["last"] == 24
    # A corrupted checksum must be rejected, not decoded.
    broken = bytearray(build_frame(0x04, [99, 0]))
    broken[-1] ^= 0xFF
    list(iter_frames(bytes(broken)))
    assert iter_frames.good == 0 and iter_frames.bad >= 1
    print("uart parser self-test passed")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.input:
        ap.error("--input or --self-test is required")
    with open(args.input, "rb") as fh:
        data = fh.read()
    state = {}
    for command, payload in iter_frames(data):
        decode(state, command, payload)
    report = {
        "input": os.path.basename(args.input),
        "bytes": len(data),
        "frames_valid": getattr(iter_frames, "good", 0),
        "frames_rejected_checksum": getattr(iter_frames, "bad", 0),
        "commands": summarise(state),
        "evidence_policy": "CONFIRMED fields are trusted; LIKELY fields are "
                           "reported with their evidence level and are not "
                           "presented as confirmed vehicle state",
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as fh:
            fh.write(text)
    print(f"[uart] {report['frames_valid']} valid frames, "
          f"{report['frames_rejected_checksum']} rejected")
    for command, entry in report["commands"].items():
        fields = ", ".join(f"{name}={slot['last']}"
                           for name, slot in entry["fields"].items())
        print(f"[uart] {command}: {entry['frames']} frames | {fields}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
