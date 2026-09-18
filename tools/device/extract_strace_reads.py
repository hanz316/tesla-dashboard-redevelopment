#!/usr/bin/env python3
"""Turn a strace log of read() calls into the raw byte stream they carried.

`strace -xx -s 400 -e trace=read` prints the buffer of each read as hex
escapes, so the live UART stream can be reconstructed on the Mac without ever
opening the port on the device - opening it would take bytes away from the
running dashboard.

Usage:
    python3 tools/device/extract_strace_reads.py --input ttyS5.strace \
        --out captures/uart-record.bin
"""

import argparse
import re
import sys

READ_RE = re.compile(r'read\(\d+,\s*("(?:[^"\\]|\\.)*")', re.S)


def unescape(chunk):
    out = bytearray()
    i = 0
    body = chunk[1:-1]
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt == "x" and i + 3 < len(body):
                try:
                    out.append(int(body[i + 2:i + 4], 16))
                except ValueError:
                    pass
                i += 4
                continue
            mapping = {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, '"': 34}
            if nxt in mapping:
                out.append(mapping[nxt])
                i += 2
                continue
            i += 2
            continue
        out.extend(c.encode("latin-1", "ignore"))
        i += 1
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        sample = 'read(12, "\\x2e\\x04\\x02\\x0a\\x00\\x1f", 6) = 6\n'
        data = b"".join(unescape(m) for m in READ_RE.findall(sample))
        assert data == bytes([0x2E, 0x04, 0x02, 0x0A, 0x00, 0x1F]), data
        print("strace extractor self-test passed")
        return 0
    if not args.input or not args.out:
        ap.error("--input and --out are required (or use --self-test)")
    with open(args.input, "r", errors="replace") as fh:
        text = fh.read()
    data = b"".join(unescape(m) for m in READ_RE.findall(text))
    with open(args.out, "wb") as fh:
        fh.write(data)
    print(f"[strace] {len(data)} bytes from {len(READ_RE.findall(text))} reads "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
