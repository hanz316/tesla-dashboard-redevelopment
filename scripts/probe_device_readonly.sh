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

device_list="$("$adb_bin" devices | awk 'NR > 1 && $2 == "device" {print $1}')"
device_count="$(printf '%s\n' "$device_list" | awk 'NF {count++} END {print count+0}')"
if [[ "$device_count" -ne 1 ]]; then
  echo "Expected exactly one authorized ADB device; found $device_count." >&2
  "$adb_bin" devices -l >&2
  exit 1
fi

device_serial="$(printf '%s\n' "$device_list" | awk 'NF {print; exit}')"
capture_stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
capture_dir="$project_root/captures/device-$capture_stamp"
mkdir -p "$capture_dir"

"$adb_bin" devices -l > "$capture_dir/adb-device.txt"

capture_shell() {
  output_name="$1"
  remote_command="$2"
  if ! "$adb_bin" -s "$device_serial" shell "$remote_command" \
      > "$capture_dir/$output_name" 2>&1; then
    printf 'command failed: %s\n' "$remote_command" \
      >> "$capture_dir/$output_name"
  fi
}

capture_shell getprop.txt 'getprop'
capture_shell uname.txt 'uname -a'
capture_shell cpuinfo.txt 'cat /proc/cpuinfo'
capture_shell meminfo.txt 'cat /proc/meminfo'
capture_shell cmdline.txt 'cat /proc/cmdline'
capture_shell partitions.txt 'cat /proc/partitions'
capture_shell mtd.txt 'cat /proc/mtd'
capture_shell mounts.txt 'mount'
capture_shell df.txt 'df -h'
capture_shell processes.txt 'ps'
capture_shell modules.txt 'cat /proc/modules'
capture_shell network.txt 'ip addr 2>/dev/null || ifconfig -a'
capture_shell routes.txt 'ip route 2>/dev/null || route -n'
capture_shell dev-serial.txt 'ls -la /dev/tty*'
capture_shell dev-video.txt 'ls -la /dev/video* 2>/dev/null'
capture_shell dev-input.txt 'ls -la /dev/input 2>/dev/null; ls -la /dev/input/* 2>/dev/null'
capture_shell usb.txt 'ls -la /sys/class/udc 2>/dev/null; ls -la /sys/kernel/config/usb_gadget 2>/dev/null'
capture_shell filesystems.txt 'ls -la / /res /etc /data /tmp /mnt 2>/dev/null'
capture_shell services.txt 'getprop | grep init.svc'
capture_shell kernel-log.txt 'dmesg'

echo "Read-only device capture saved to: $capture_dir"
