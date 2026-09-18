#!/usr/bin/env bash
# Assemble the DEV deployment bundle from the CURRENT build of CURRENT HEAD.
#
# Usage: scripts/package_dev_bundle.sh [artifact-path]
#
# The bundle is what gets pushed to /tmp on the instrument. It carries the
# library, the EasyUI config and a BUILD_INFO.json that records exactly which
# commit the artifact came from, so a later deploy cannot mistake an old
# prebuilt library for the current source.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
artifact="${1:-$repo_root/build-t113/libzkgui.so}"
bundle="$repo_root/dist/dev-bundle"

if [[ ! -f "$artifact" ]]; then
  echo "No artifact at $artifact." >&2
  echo "Build one first (needs the containerised toolchain):" >&2
  echo "  scripts/build_t113.sh" >&2
  exit 1
fi

commit="$(git -C "$repo_root" rev-parse HEAD)"
dirty="no"
if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  dirty="yes"
fi
mode="${BUILD_MODE:-Release}"
stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
hash="$(shasum -a 256 "$artifact" | awk '{print $1}')"

mkdir -p "$bundle/tesla-dashboard-mvp/lib"
cp "$artifact" "$bundle/tesla-dashboard-mvp/lib/libzkgui.so"
cp "$repo_root/deploy/temporary-adb/EasyUI.cfg" "$bundle/EasyUI.cfg"

cat > "$bundle/BUILD_INFO.json" <<EOF
{
  "source_commit": "$commit",
  "source_dirty": "$dirty",
  "build_mode": "$mode",
  "build_timestamp_utc": "$stamp",
  "target": "allwinner-t113 / armv7 / musl / hard-float",
  "artifact": "tesla-dashboard-mvp/lib/libzkgui.so",
  "artifact_sha256": "$hash",
  "builder": "scripts/build_t113.sh (docker, linux/amd64)",
  "assets_owned_by_app": [],
  "notes": [
    "The activity reuses the stock main.ftu page; it copies no stock artwork.",
    "Deployment writes to /tmp only. Rollback is 'rm /tmp/EasyUI.cfg' plus a restart."
  ]
}
EOF

echo "[bundle] $bundle"
echo "[bundle] artifact $artifact"
echo "[bundle] sha256   $hash"
echo "[bundle] commit   $commit (dirty: $dirty)"
