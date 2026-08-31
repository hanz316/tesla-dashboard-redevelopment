#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target_dir="$project_root/dist/temporary-adb"
library_source="$project_root/build-t113/libzkgui.so"

if [[ ! -f "$library_source" ]]; then
  echo "Missing T113 build: $library_source" >&2
  echo "Run scripts/build_t113.sh first." >&2
  exit 1
fi

mkdir -p "$target_dir/tesla-dashboard-mvp/lib"
cp "$library_source" "$target_dir/tesla-dashboard-mvp/lib/libzkgui.so"
cp "$project_root/deploy/temporary-adb/EasyUI.cfg" "$target_dir/EasyUI.cfg"

shasum -a 256 \
  "$target_dir/EasyUI.cfg" \
  "$target_dir/tesla-dashboard-mvp/lib/libzkgui.so"
