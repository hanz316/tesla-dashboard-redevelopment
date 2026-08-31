#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--temporary" || -z "${2:-}" ]]; then
  echo "Usage: $0 --temporary DEVICE_SERIAL" >&2
  echo "This writes only to /tmp and restarts zkswe; it does not flash firmware." >&2
  exit 1
fi

device_serial="$2"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
adb_bin="${ADB_BIN:-$(command -v adb 2>/dev/null || true)}"
if [[ -z "$adb_bin" && -x "$project_root/toolchains/platform-tools/adb" ]]; then
  adb_bin="$project_root/toolchains/platform-tools/adb"
fi
if [[ -z "$adb_bin" ]]; then
  echo "adb is not installed and no local Platform Tools were found." >&2
  exit 1
fi
if [[ "$("$adb_bin" -s "$device_serial" get-state 2>/dev/null)" != "device" ]]; then
  echo "ADB device is not authorized/online: $device_serial" >&2
  exit 1
fi

bundle_dir="$project_root/dist/temporary-adb"
capture_stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
predeploy_dir="$project_root/captures/predeploy-$device_serial-$capture_stamp"
mkdir -p "$predeploy_dir"

if [[ ! -f "$bundle_dir/EasyUI.cfg" \
   || ! -f "$bundle_dir/tesla-dashboard-mvp/lib/libzkgui.so" ]]; then
  echo "Temporary bundle is missing. Run scripts/package_temporary_bundle.sh." >&2
  exit 1
fi

device_model="$("$adb_bin" -s "$device_serial" shell 'getprop ro.product.model' | tr -d '\r')"
case "$device_model" in
  *T113*|*t113*) ;;
  *)
    echo "Refusing deployment: expected T113 device, got '$device_model'." >&2
    exit 1
    ;;
esac

"$adb_bin" -s "$device_serial" shell 'cat /tmp/EasyUI.cfg 2>/dev/null' \
  > "$predeploy_dir/EasyUI.cfg" || true
"$adb_bin" -s "$device_serial" shell 'getprop' > "$predeploy_dir/getprop.txt"
"$adb_bin" -s "$device_serial" shell 'mount' > "$predeploy_dir/mounts.txt"

"$adb_bin" -s "$device_serial" shell 'mkdir -p /tmp/tesla-dashboard-mvp/lib'
"$adb_bin" -s "$device_serial" push \
  "$bundle_dir/tesla-dashboard-mvp/lib/libzkgui.so" \
  '/tmp/tesla-dashboard-mvp/lib/libzkgui.so'
"$adb_bin" -s "$device_serial" push "$bundle_dir/EasyUI.cfg" '/tmp/EasyUI.cfg'
"$adb_bin" -s "$device_serial" shell 'sync'
"$adb_bin" -s "$device_serial" shell 'setprop ctl.restart zkswe'

echo "Temporary MVP started. Power-cycle the dashboard to restore stock." 
echo "Pre-deployment metadata: $predeploy_dir"
