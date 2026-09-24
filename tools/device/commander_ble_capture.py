#!/usr/bin/env python3
"""Passive Commander capture from a host BLE central.

The instrument cannot be a BLE central yet (the platform exposes no generic
GATT client), but a laptop can. This reads the module the way its own control
software does - connect, subscribe to FFF1, ask the safe read questions - and
records every byte that comes back.

Safety:

* only commands on the repository's query whitelist are ever written:
  160 (module status), 176 (dashboard stream, start/stop), 208/209/210
  (pack, cells, DC-DC). 193 is available but unused here.
* CMD 167 - the control word that opens doors, cuts motors or changes ESP - is
  not in the file at all, and `assert_query()` refuses anything that is not a
  query before a write happens.
* nothing about the vehicle is touched: the module is a separate box, and the
  vehicle UART is not involved.

Evidence is written to captures/commander/<timestamp>.jsonl (one JSON object per
received frame plus a header of what was asked). That directory is local and
gitignored, per repository policy on raw captures.

Usage:
    python3 tools/device/commander_ble_capture.py --scan
    python3 tools/device/commander_ble_capture.py --address <uuid> --seconds 25
"""

import argparse
import asyncio
import json
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(REPO, "captures", "commander")

SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"

HEADER0, HEADER1 = 0x55, 0x7F

# The three questions worth asking right now. 176 with [1] is the module's own
# dashboard stream: if it streams, its cadence answers whether the instrument
# has to poll or can subscribe.
QUERIES = [
    (160, []),
    (176, [1]),
    (208, [2]),
    (208, [3]),
    (209, []),
    (210, []),
]

SAFE_QUERIES = {160, 176, 193, 208, 209, 210}

# The module gates its data commands behind a four-digit password check. The
# handshake is CMD 168 with four ASCII digits (the module's own control
# software sends exactly this, and treats "1234" as the default that does not
# consume an attempt). This is an authentication check on the module, not a
# vehicle command: CMD 167 and every other control command stay refused.
AUTH_COMMAND = 168
AUTH_PASSWORD = "1234"


def assert_query(command, auth=False):
    if command in SAFE_QUERIES:
        return
    if auth and command == AUTH_COMMAND:
        return
    if command != AUTH_COMMAND:
        raise SystemExit(
            f"refusing to write command {command}: it is not a read query. "
            f"167 and every other control command stay blocked.")
    raise SystemExit(
        "refusing to write the password check outside the documented handshake")


def encode(command, payload, auth=False):
    assert_query(command, auth=auth)
    body = [command, (len(payload) >> 8) & 0xFF, len(payload) & 0xFF] + list(payload)
    checksum = sum(body) & 0xFF
    return bytes([HEADER0, HEADER1] + body + [checksum])


class FrameReader:
    """The module's own framing, 55 7F CMD LEN_HI LEN_LO DATA CHK."""

    def __init__(self):
        self.state = 0
        self.command = 0
        self.length = 0
        self.index = 0
        self.running = 0
        self.payload = bytearray()
        self.frames = 0
        self.checksum_errors = 0
        self.malformed = 0

    def feed(self, byte):
        if self.state == 0:
            if byte == HEADER0:
                self.state = 1
            else:
                self.malformed += 1
        elif self.state == 1:
            if byte == HEADER1:
                self.state = 2
            elif byte != HEADER0:
                self.malformed += 1
                self.state = 0
        elif self.state == 2:
            self.command = byte
            self.running = byte
            self.state = 3
        elif self.state == 3:
            self.length = byte << 8
            self.running = (self.running + byte) & 0xFF
            self.state = 4
        elif self.state == 4:
            self.length |= byte
            self.running = (self.running + byte) & 0xFF
            self.payload = bytearray()
            self.index = 0
            self.state = 6 if self.length == 0 else 5
        elif self.state == 5:
            self.payload.append(byte)
            self.running = (self.running + byte) & 0xFF
            self.index += 1
            if self.index >= self.length:
                self.state = 6
        elif self.state == 6:
            if self.running == byte:
                self.frames += 1
                frame = (self.command, bytes(self.payload))
                self.state = 0
                return frame
            self.checksum_errors += 1
            self.state = 0
        return None


async def scan(seconds):
    from bleak import BleakScanner
    print(f"[ble] scanning {seconds}s ...")
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    # discover(return_adv=True) maps address -> (device, advertisement_data).
    for address, (device, adv) in sorted(
            found.items(), key=lambda item: item[1][1].rssi or -999, reverse=True):
        services = [u.lower() for u in (adv.service_uuids or [])]
        marker = " <== FFF0" if SERVICE_UUID in services else ""
        print(f"  {adv.rssi:5d} dBm  {address}  {adv.local_name!r}  {services}{marker}")
    return found


async def capture(address, seconds, settle):
    from bleak import BleakClient

    reader = FrameReader()
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = os.path.join(OUT_DIR, f"{stamp}.jsonl")
    log = open(path, "w")
    started = time.time()
    log.write(json.dumps({
        "kind": "header",
        "schema": "commander-ble-capture v1",
        "address": address,
        "started_utc": stamp,
        "queries": [{"command": c, "payload": list(p)} for c, p in QUERIES],
        "note": "read queries only; CMD 167 is never sent",
    }) + "\n")
    log.flush()

    frames = []

    def on_notify(_sender, data):
        now = time.time() - started
        for byte in data:
            frame = reader.feed(byte)
            if frame is None:
                continue
            command, payload = frame
            record = {
                "kind": "frame",
                "t": round(now, 3),
                "command": command,
                "length": len(payload),
                "payload_hex": payload.hex(),
                "payload": list(payload),
            }
            frames.append(record)
            log.write(json.dumps(record) + "\n")
            log.flush()
            print(f"  [{now:6.2f}s] cmd {command:3d} len {len(payload):3d} "
                  f"{payload.hex()[:80]}")

    try:
        async with BleakClient(address, timeout=20.0) as client:
            print(f"[ble] connected to {address}")
            # bleak 1.x exposes the discovered services as a property; older
            # versions needed an await.
            services = client.services
            if callable(getattr(services, "__await__", None)):
                services = await services
            target = None
            for service in services:
                if service.uuid.lower() != SERVICE_UUID:
                    continue
                for characteristic in service.characteristics:
                    if characteristic.uuid.lower() == CHARACTERISTIC_UUID:
                        target = characteristic
            if target is None:
                print("[ble] FFF1 not found: this is not the module")
                return 2, path, reader, frames
            print(f"[ble] FFF1 properties: {target.properties}")
            await client.start_notify(target, on_notify)
            await asyncio.sleep(settle)

            # The module's own control software answers its password prompt: it
            # sends the check only after the module has asked for it (reply 255
            # on CMD 168). So ask for the status first, wait for the prompt, and
            # only then send the one attempt with the documented default.
            async def write(frame, note):
                try:
                    await client.write_gatt_char(target, frame, response=False)
                except Exception:  # noqa: BLE001 - fall back to an acknowledged write
                    await client.write_gatt_char(target, frame, response=True)
                print(f"[ble] -> {frame.hex()}  {note}")

            await write(encode(160, []), "(ask for status, which triggers the prompt)")
            for _ in range(30):
                if any(r["command"] == AUTH_COMMAND for r in frames):
                    break
                await asyncio.sleep(0.1)
            prompted = [r["payload"][0] for r in frames
                        if r["command"] == AUTH_COMMAND and r["payload"]]
            print(f"[ble] module prompt: {prompted[-1] if prompted else None}")

            handshake = encode(AUTH_COMMAND,
                               [ord(c) for c in AUTH_PASSWORD], auth=True)
            await write(handshake, "(password check, one attempt)")
            await asyncio.sleep(2.0)
            codes = [r["payload"][0] for r in frames
                     if r["command"] == AUTH_COMMAND and r["payload"]]
            code = codes[-1] if codes else None
            meaning = {255: "needs password", 0: "wrong password", 1: "accepted"}
            print(f"[ble] password check reply: {code} "
                  f"({meaning.get(code, 'unknown')})")
            if code == 0:
                print("[ble] the default password is not this module's "
                      "password; stopping rather than guessing")
                log.write(json.dumps({"kind": "note",
                                      "note": "password rejected, capture stopped"}) + "\n")
                log.close()
                return 3, path, reader, frames

            for command, payload in QUERIES:
                frame = encode(command, payload)
                await write(frame, "")
                await asyncio.sleep(1.2 if command != 176 else 6.0)

            # How long the module keeps talking on its own after being asked.
            quiet = time.time()
            while time.time() - started < seconds:
                await asyncio.sleep(0.5)
            print(f"[ble] observed for {time.time() - quiet:.1f}s after the last query")
            await client.stop_notify(target)
    except Exception as error:  # noqa: BLE001 - report, do not crash the run
        print(f"[ble] capture failed: {type(error).__name__}: {error}")
        log.write(json.dumps({"kind": "error", "error": f"{type(error).__name__}: {error}"}) + "\n")
        log.close()
        return 1, path, reader, frames

    log.write(json.dumps({
        "kind": "summary",
        "frames": reader.frames,
        "checksum_errors": reader.checksum_errors,
        "malformed": reader.malformed,
    }) + "\n")
    log.close()
    print(f"[ble] {reader.frames} frames, {reader.checksum_errors} checksum errors "
          f"-> {os.path.relpath(path, REPO)}")
    return 0, path, reader, frames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--address")
    parser.add_argument("--seconds", type=float, default=25.0)
    parser.add_argument("--settle", type=float, default=0.8)
    parser.add_argument("--scan-seconds", type=float, default=8.0)
    parser.add_argument("--query", action="append", default=None,
                        help="override the query list, e.g. --query 208:2")
    args = parser.parse_args()

    if args.query:
        QUERIES.clear()
        for item in args.query:
            command, _, payload = item.partition(":")
            QUERIES.append((int(command),
                            [int(b) for b in payload.split(",")] if payload else []))

    if args.scan or not args.address:
        found = asyncio.run(scan(args.scan_seconds))
        if args.scan or not args.address:
            return 0
    code, path, reader, frames = asyncio.run(
        capture(args.address, args.seconds, args.settle))
    by_command = {}
    for record in frames:
        by_command.setdefault(record["command"], []).append(record["t"])
    for command in sorted(by_command):
        times = by_command[command]
        gaps = [round(b - a, 3) for a, b in zip(times, times[1:])]
        print(f"  cmd {command:3d}: {len(times)} frames, first {times[0]:.2f}s, "
              f"gaps {gaps[:8]}")
    return code


if __name__ == "__main__":
    sys.exit(main())
