#!/usr/bin/env bash
set -euo pipefail

device_serial="${1:-}"
if [[ -z "$device_serial" ]]; then
  echo "Usage: $0 DEVICE_SERIAL" >&2
  exit 1
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
adb_bin="${ADB_BIN:-$(command -v adb 2>/dev/null || true)}"
if [[ -z "$adb_bin" && -x "$project_root/toolchains/platform-tools/adb" ]]; then
  adb_bin="$project_root/toolchains/platform-tools/adb"
fi
if [[ -z "$adb_bin" ]]; then
  echo "adb is not installed and no local Platform Tools were found." >&2
  exit 1
fi

backup_stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
backup_dir="$project_root/captures/raw-mtd-$device_serial-$backup_stamp"
mkdir -p "$backup_dir"

# ADB's sync/pull protocol transfers block-device bytes without a PTY.  It was
# cross-checked byte-for-byte against the verified Base64 helper on mtdblock0.
pull_partition() {
  remote_path="$1"
  output_name="$2"
  expected_size="$3"
  output_file="$backup_dir/$output_name.img"

  echo "Reading $remote_path ($expected_size bytes)"
  if ! "$adb_bin" -s "$device_serial" pull "$remote_path" "$output_file"; then
    "$adb_bin" kill-server
    "$adb_bin" start-server
    "$adb_bin" connect "$device_serial"
    "$adb_bin" -s "$device_serial" pull "$remote_path" "$output_file"
  fi

  actual_size="$(stat -f '%z' "$output_file")"
  if [[ "$actual_size" -ne "$expected_size" ]]; then
    echo "Size mismatch for $remote_path: expected $expected_size, got $actual_size" >&2
    exit 1
  fi
}

pull_partition /dev/block/mtdblock0 mtd0-uboot 393216
pull_partition /dev/block/mtdblock1 mtd1-boot 6291456
pull_partition /dev/block/mtdblock2 mtd2-res 22413312
pull_partition /dev/block/mtdblock3 mtd3-config 3145728
pull_partition /dev/block/mtdblock4 mtd4-boot_logo 262144
pull_partition /dev/block/mtdblock5 mtd5-data 1048576

shasum -a 256 "$backup_dir"/*.img > "$backup_dir/SHA256SUMS"
echo "Raw read-only MTD backup saved to: $backup_dir"
