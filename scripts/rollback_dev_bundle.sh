#!/usr/bin/env bash
# Restore the stock instrument UI. Writes nothing to flash and nothing to /res.
#
# Usage: scripts/rollback_dev_bundle.sh [--serial <target>]
set -euo pipefail

serial="${ADB_SERIAL:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial) serial="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

adb_bin="${ADB_BIN:-$HOME/Library/Android/sdk/platform-tools/adb}"
[[ -x "$adb_bin" ]] || adb_bin="$(command -v adb)"

if [[ -z "$serial" ]]; then
  mapfile -t targets < <("$adb_bin" devices | awk 'NR>1 && $2=="device" {print $1}')
  case "${#targets[@]}" in
    0) echo "No ADB device connected." >&2; exit 1 ;;
    1) serial="${targets[0]}" ;;
    *) echo "Multiple devices; pass --serial." >&2; printf '  %s\n' "${targets[@]}" >&2; exit 1 ;;
  esac
fi

# Removing the /tmp config makes the stock launcher fall back to /res, and the
# restart picks it up. Nothing outside /tmp is touched.
"$adb_bin" -s "$serial" shell 'rm -f /tmp/EasyUI.cfg; sync; setprop ctl.restart zkswe'
echo "[rollback] stock UI restored on $serial (nothing outside /tmp was written)"
