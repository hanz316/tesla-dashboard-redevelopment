#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/uart_record.sh start [DEVICE_SERIAL]
#   bash scripts/uart_record.sh stop [DEVICE_SERIAL]
#   bash scripts/uart_record.sh pull [DEVICE_SERIAL]
#
# Records raw /dev/ttyS5 bytes to /tmp/uart_recording.bin on the device
# (only while the flag file exists). Pull copies it to captures/.

adb_bin="${ADB_BIN:-$(command -v adb 2>/dev/null || true)}"
if [[ -z "$adb_bin" && -x "$(dirname "${BASH_SOURCE[0]}")/../toolchains/platform-tools/adb" ]]; then
  adb_bin="$(dirname "${BASH_SOURCE[0]}")/../toolchains/platform-tools/adb"
fi
if [[ -z "$adb_bin" ]]; then
  echo "adb not found" >&2
  exit 1
fi

serial="${2:-10.0.0.216:5555}"
target="$adb_bin -s $serial"

case "${1:-}" in
  start)
    "$adb_bin" -s "$serial" shell 'echo 1 > /tmp/uart_record'
    echo "recording started (flag /tmp/uart_record set)"
    ;;
  stop)
    "$adb_bin" -s "$serial" shell 'rm -f /tmp/uart_record'
    echo "recording stopped (flag removed)"
    ;;
  pull)
    stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
    "$adb_bin" -s "$serial" shell 'cat /tmp/uart_recording.bin > /tmp/uart_recording_copy.bin 2>/dev/null; ls -l /tmp/uart_recording.bin 2>/dev/null'
    mkdir -p "$(dirname "${BASH_SOURCE[0]}")/../captures"
    "$adb_bin" -s "$serial" pull /tmp/uart_recording.bin \
      "$(dirname "${BASH_SOURCE[0]}")/../captures/uart-record-$stamp.bin"
    ;;
  *)
    echo "usage: $0 {start|stop|pull} [serial]" >&2
    exit 1
    ;;
esac
