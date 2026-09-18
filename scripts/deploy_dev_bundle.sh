#!/usr/bin/env bash
# Deploy the DEV bundle to a T113 instrument, safely and reversibly.
#
# Usage: ADB_SERIAL=<host:port|serial> scripts/deploy_dev_bundle.sh
#        scripts/deploy_dev_bundle.sh --serial <host:port|serial> [--dry-run]
#
# Rules this script enforces, in order:
#   * a target must be explicit or uniquely discoverable - no historical IP is
#     ever baked in;
#   * the local HEAD, the bundle's recorded commit and the artifact hash must
#     agree, so an old prebuilt library cannot be deployed as if it were
#     current;
#   * the device must identify itself as a T113;
#   * only /tmp is written; /res, /late and every flash partition are refused;
#   * the rollback path is printed before anything is pushed.
#
# It never opens /dev/ttyS5 and never sends a vehicle command.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bundle="$repo_root/dist/dev-bundle"
serial="${ADB_SERIAL:-}"
dry_run="no"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial) serial="${2:-}"; shift 2 ;;
    --dry-run) dry_run="yes"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

adb_bin="${ADB_BIN:-$HOME/Library/Android/sdk/platform-tools/adb}"
if [[ ! -x "$adb_bin" ]]; then
  adb_bin="$(command -v adb || true)"
fi
[[ -n "$adb_bin" ]] || { echo "adb not found (set ADB_BIN)" >&2; exit 1; }

# ---- target selection: explicit, or exactly one connected device ----------
if [[ -z "$serial" ]]; then
  mapfile -t targets < <("$adb_bin" devices | awk 'NR>1 && $2=="device" {print $1}')
  case "${#targets[@]}" in
    0) echo "No ADB device connected. Connect the instrument, then pass --serial." >&2; exit 1 ;;
    1) serial="${targets[0]}" ;;
    *) echo "Multiple ADB devices; pick one with --serial:" >&2
       printf '  %s\n' "${targets[@]}" >&2
       exit 1 ;;
  esac
fi
echo "[deploy] target $serial"

[[ -f "$bundle/BUILD_INFO.json" ]] || {
  echo "No bundle at $bundle. Run scripts/package_dev_bundle.sh first." >&2; exit 1; }

# ---- integrity: HEAD == bundle commit == artifact hash -------------------
local_head="$(git -C "$repo_root" rev-parse HEAD)"
bundle_commit="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_commit"])' "$bundle/BUILD_INFO.json")"
recorded_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["artifact_sha256"])' "$bundle/BUILD_INFO.json")"
actual_hash="$(shasum -a 256 "$bundle/tesla-dashboard-mvp/lib/libzkgui.so" | awk '{print $1}')"
mode="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["build_mode"])' "$bundle/BUILD_INFO.json")"

if [[ "$local_head" != "$bundle_commit" ]]; then
  echo "Refusing: bundle was built from $bundle_commit but HEAD is $local_head." >&2
  echo "Rebuild (scripts/build_t113.sh) and re-package." >&2
  exit 1
fi
if [[ "$recorded_hash" != "$actual_hash" ]]; then
  echo "Refusing: artifact hash does not match BUILD_INFO.json." >&2
  exit 1
fi

echo "[deploy] SOURCE COMMIT $local_head"
echo "[deploy] TARGET        $serial (must report a T113)"
echo "[deploy] ARTIFACT HASH $actual_hash"
echo "[deploy] BUILD MODE    $mode"
echo "[deploy] ROLLBACK      rm -f /tmp/EasyUI.cfg && setprop ctl.restart zkswe"

if [[ "$dry_run" == "yes" ]]; then
  echo "[deploy] dry run: nothing pushed"
  exit 0
fi

device_model="$("$adb_bin" -s "$serial" shell 'getprop ro.product.model' | tr -d '\r')"
case "$device_model" in
  *T113*|*t113*) ;;
  *) echo "Refusing: expected a T113 instrument, got '$device_model'." >&2; exit 1 ;;
esac

# ---- push: /tmp only -----------------------------------------------------
stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
evidence="$repo_root/captures/predeploy-$stamp"
mkdir -p "$evidence"
"$adb_bin" -s "$serial" shell 'cat /tmp/EasyUI.cfg 2>/dev/null' > "$evidence/EasyUI.cfg" || true
"$adb_bin" -s "$serial" shell 'getprop' > "$evidence/getprop.txt"

"$adb_bin" -s "$serial" shell 'mkdir -p /tmp/tesla-dashboard-mvp/lib'
"$adb_bin" -s "$serial" push "$bundle/tesla-dashboard-mvp/lib/libzkgui.so" \
  '/tmp/tesla-dashboard-mvp/lib/libzkgui.so' >/dev/null
"$adb_bin" -s "$serial" push "$bundle/EasyUI.cfg" '/tmp/EasyUI.cfg' >/dev/null
"$adb_bin" -s "$serial" shell 'sync; setprop ctl.restart zkswe'

echo "[deploy] installed from $local_head; evidence in $evidence"
echo "[deploy] rollback: scripts/rollback_dev_bundle.sh --serial $serial"
