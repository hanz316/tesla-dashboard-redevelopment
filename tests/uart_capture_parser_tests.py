#!/usr/bin/env python3
"""The live-capture parser must be provably correct before it is trusted.

The parser is the only thing standing between a raw byte stream and a claim
about what the car is doing, so its frame sync, checksum rule and CONFIRMED
decodings are tested here against frames built by the same definition in
docs/protocol-table.md.
"""

import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILURES = []


def check(condition, label):
    if condition:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s" % label)
        FAILURES.append(label)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = load(os.path.join(REPO, "tools", "device",
                               "parse_uart_capture.py"), "parse_uart_capture")
    extractor = load(os.path.join(REPO, "tools", "device",
                                  "extract_strace_reads.py"),
                     "extract_strace_reads")
    print("frame definition")
    frame = parser.build_frame(0x04, [10, 0, 0, 0, 0, 0, 253, 0, 63])
    check(frame[0] == 0x2E, "the header is 0x2E")
    check(frame[1] == 0x04 and frame[2] == 9, "command and length follow")
    check(frame[-1] == parser.checksum(0x04, [10, 0, 0, 0, 0, 0, 253, 0, 63]),
          "the checksum is ~(cmd + len + sum(payload)) & 0xFF")

    print("resynchronisation and checksum rejection")
    stream = (b"\xff\x00\x2e\x04"                    # garbage, then a short frame
              + frame
              + bytes([0x2E, 0x04, 0x02, 0x0A, 0x00, 0x1F]))   # torn tail
    frames = list(parser.iter_frames(stream))
    check(len(frames) == 1, "only the complete, valid frame is yielded")
    broken = bytearray(frame)
    broken[-1] ^= 0xFF
    list(parser.iter_frames(bytes(broken)))
    check(parser.iter_frames.good == 0 and parser.iter_frames.bad >= 1,
          "a corrupted checksum is rejected")

    print("decoded fields carry their evidence level")
    state = {}
    for command, payload in parser.iter_frames(
            parser.build_frame(0x04, [10, 0, 0, 0, 0, 0, 253, 0, 63])
            + parser.build_frame(0x12, [0, 200, 200, 200, 200])
            + parser.build_frame(0x01, [0, 0, 0, 0x01, 0x40])):
        parser.decode(state, command, payload)
    summary = parser.summarise(state)
    check(summary["0x04"]["fields"]["speed_raw"]["evidence"] == "CONFIRMED",
          "speed is marked CONFIRMED")
    check(summary["0x04"]["fields"]["speed_raw"]["last"] == 10,
          "speed decodes from LE16 payload[0..1]")
    check(summary["0x04"]["fields"]["range_raw"]["last"] == 253,
          "range decodes from LE16 payload[6..7]")
    check(summary["0x04"]["fields"]["soc_percent"]["last"] == 63,
          "SOC decodes from payload[8]")
    check("known-bad" in summary["0x04"]["fields"]["soc_percent"]["evidence"],
          "the known-bad SOC is labelled rather than trusted")
    check(abs(summary["0x12"]["fields"]["tire_0_bar"]["last"] - 5.0) < 1e-9,
          "tire pressure decodes as payload * 0.025 bar")
    check("NEEDS REAL CAR TEST" in
          summary["0x12"]["fields"]["tire_0_bar"]["evidence"],
          "the wheel-order caveat travels with the value")
    check(summary["0x01"]["fields"]["gear_nibble"]["last"] == 4,
          "gear nibble decodes (4 = D)")
    check(summary["0x01"]["fields"]["payload3_bits"]["evidence"] == "LIKELY",
          "a LIKELY bit field is not presented as confirmed")

    print("strace extraction")
    sample = 'read(12, "\\x2e\\x04\\x02\\x0a\\x00\\x1f", 6) = 6\n'
    data = b"".join(extractor.unescape(m)
                    for m in extractor.READ_RE.findall(sample))
    check(data == bytes([0x2E, 0x04, 0x02, 0x0A, 0x00, 0x1F]),
          "hex-escaped read buffers round-trip to the raw byte stream")

    print("")
    if FAILURES:
        print("%d FAILED: %s" % (len(FAILURES), "; ".join(FAILURES)))
        return 1
    print("all uart capture parser checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
