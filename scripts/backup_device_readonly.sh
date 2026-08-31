#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
adb_bin="${ADB_BIN:-$(command -v adb 2>/dev/null || true)}"
if [[ -z "$adb_bin" && -x "$project_root/toolchains/platform-tools/adb" ]]; then
  adb_bin="$project_root/toolchains/platform-tools/adb"
fi
if [[ -z "$adb_bin" ]]; then
  echo "adb is not installed and no local Platform Tools were found." >&2
  exit 1
fi

device_serial="${1:-}"
if [[ -z "$device_serial" ]]; then
  echo "Usage: $0 DEVICE_SERIAL" >&2
  exit 1
fi
if [[ "$("$adb_bin" -s "$device_serial" get-state 2>/dev/null)" != "device" ]]; then
  echo "ADB device is not authorized/online: $device_serial" >&2
  exit 1
fi

backup_stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
backup_dir="$project_root/captures/backup-$device_serial-$backup_stamp"
mkdir -p "$backup_dir"

# adb pull reads the device and writes only to the Mac.  No adb root, remount,
# dd-to-device, setprop, or flash command is used here.
for remote_path in /res /etc; do
  "$adb_bin" -s "$device_serial" pull "$remote_path" "$backup_dir" \
    > "$backup_dir/pull-$(basename "$remote_path").log" 2>&1 || true
done
"$adb_bin" -s "$device_serial" exec-out 'cat /proc/mtd' > "$backup_dir/proc-mtd.txt" || true
"$adb_bin" -s "$device_serial" exec-out 'cat /proc/partitions' > "$backup_dir/proc-partitions.txt" || true
"$adb_bin" -s "$device_serial" exec-out 'mount' > "$backup_dir/mounts.txt" || true

echo "Read-only accessible-files backup saved to: $backup_dir"
