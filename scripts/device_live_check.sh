#!/usr/bin/env bash
# Read-only live check of the instrument cluster while it is running.
#
# Usage:
#   scripts/device_live_check.sh <serial-host[:port]> [seconds] [adb-binary]
#
# What it does, in order, and nothing else:
#   1. adb connect and report what the device says it is;
#   2. read-only recon: /dev/ttyS5, who is reading it, what tools exist;
#   3. attach strace to the RUNNING app's reads on that tty (observing, not
#      stealing bytes - opening the port would take data away from the live
#      dashboard) and save the trace on the device under /tmp;
#   4. pull it and decode it on the Mac with the documented protocol.
#
# Hard rules: never writes to /res, never touches MTD/flash, never sends any
# vehicle or MCU command, never restarts the running UI.
set -euo pipefail

serial="${1:-}"
seconds="${2:-20}"
adb_bin="${3:-${ADB_BIN:-}}"

if [[ -z "$serial" ]]; then
  echo "usage: $0 <serial-host[:port]> [seconds] [adb-binary]" >&2
  exit 2
fi
if [[ -z "$adb_bin" ]]; then
  if command -v adb >/dev/null 2>&1; then
    adb_bin="$(command -v adb)"
  elif [[ -x "$HOME/Library/Android/sdk/platform-tools/adb" ]]; then
    adb_bin="$HOME/Library/Android/sdk/platform-tools/adb"
  else
    echo "adb not found (set ADB_BIN)" >&2
    exit 1
  fi
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
capture_dir="$repo_root/captures"
mkdir -p "$capture_dir"

echo "[live] adb connect $serial"
"$adb_bin" connect "$serial" | tail -1
"$adb_bin" -s "$serial" wait-for-device

echo "[live] device identity (read-only)"
"$adb_bin" -s "$serial" shell 'getprop ro.product.model; getprop ro.hardware; uname -a' || true

echo "[live] /dev/ttyS5 and its reader"
"$adb_bin" -s "$serial" shell 'ls -l /dev/ttyS5; for p in $(ls /proc | grep -E "^[0-9]+$"); do if ls -l /proc/$p/fd 2>/dev/null | grep -q ttyS5; then echo "reader pid=$p $(cat /proc/$p/comm 2>/dev/null)"; fi; done' || true

echo "[live] available observation tools"
"$adb_bin" -s "$serial" shell 'for t in strace cat busybox; do command -v $t || true; done' || true

reader_pid="$("$adb_bin" -s "$serial" shell 'for p in $(ls /proc | grep -E "^[0-9]+$"); do if ls -l /proc/$p/fd 2>/dev/null | grep -q ttyS5; then echo $p; break; fi; done' | tr -d "\r")"

if [[ -z "$reader_pid" ]]; then
  echo "[live] no process currently holds /dev/ttyS5 - is the dashboard running?"
  exit 1
fi

if ! "$adb_bin" -s "$serial" shell 'command -v strace' | grep -q strace; then
  echo "[live] strace is not on the device. Read-only options left:" >&2
  echo "  - deploy the project app to /tmp and use scripts/uart_record.sh" >&2
  echo "    (that restarts zkswe, so not while driving)" >&2
  exit 3
fi

echo "[live] observing pid $reader_pid for ${seconds}s (no bytes are taken from the app)"
"$adb_bin" -s "$serial" shell "timeout ${seconds} strace -f -e trace=read -s 400 -xx -p ${reader_pid} 2>/tmp/ttyS5.strace; wc -l /tmp/ttyS5.strace"

"$adb_bin" -s "$serial" pull /tmp/ttyS5.strace "$capture_dir/ttyS5-strace-$stamp.txt" >/dev/null
echo "[live] trace -> captures/ttyS5-strace-$stamp.txt"

python3 "$repo_root/tools/device/extract_strace_reads.py" \
  --input "$capture_dir/ttyS5-strace-$stamp.txt" \
  --out "$capture_dir/uart-record-$stamp.bin" || true

if [[ -f "$capture_dir/uart-record-$stamp.bin" ]]; then
  python3 "$repo_root/tools/device/parse_uart_capture.py" \
    --input "$capture_dir/uart-record-$stamp.bin" \
    --out "$capture_dir/uart-decode-$stamp.json"
fi
echo "[live] done (read-only; nothing on the device was modified outside /tmp)"
