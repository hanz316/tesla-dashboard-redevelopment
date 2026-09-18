#!/usr/bin/env bash
# One controlled-action capture window.
#
# Usage: tools/device/capture_step.sh <serial> <seconds> <step-name> [adb]
#
# Reads /dev/ttyS5 read-only into /tmp on the device, then pulls it to
# captures/step-<name>.bin. The caller must have released the port first (stop
# the UI), otherwise a second reader competes with the running dashboard and
# frames are lost.
#
# Safety: reads only. No writes outside /tmp, no vehicle commands.
set -euo pipefail

serial="${1:?serial required}"
seconds="${2:?seconds required}"
name="${3:?step name required}"
adb_bin="${4:-${ADB_BIN:-$HOME/Library/Android/sdk/platform-tools/adb}}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
device_file="/tmp/step_${name}.bin"
host_file="$repo_root/captures/step-${name}.bin"

"$adb_bin" -s "$serial" shell "rm -f $device_file" >/dev/null 2>&1 || true

# Keep one shell open for the whole window; the device has no sleep/timeout.
"$adb_bin" -s "$serial" shell "cat /dev/ttyS5 > $device_file" >/dev/null 2>&1 &
capture_pid=$!
sleep "$seconds"
kill "$capture_pid" 2>/dev/null || true
wait "$capture_pid" 2>/dev/null || true

size="$("$adb_bin" -s "$serial" shell "ls -l $device_file" 2>/dev/null | tr -d '\r' | awk "{print \$4}")"
"$adb_bin" -s "$serial" pull "$device_file" "$host_file" >/dev/null 2>&1
echo "[step] $name: ${size:-0} bytes -> captures/step-${name}.bin"
