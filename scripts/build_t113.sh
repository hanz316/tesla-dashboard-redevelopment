#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
builder_image="tesla-dashboard-t113-builder"

docker build \
  --platform linux/amd64 \
  --tag "$builder_image" \
  --file "$project_root/docker/t113-build.Dockerfile" \
  "$project_root"

docker run --rm \
  --platform linux/amd64 \
  --volume "$project_root:/workspace" \
  --workdir /workspace \
  "$builder_image" \
  bash -lc '
    cmake -S /workspace -B /workspace/build-t113 \
      -DCMAKE_TOOLCHAIN_FILE=/workspace/cmake/t113-musl-toolchain.cmake \
      -DBUILD_HOST_TOOLS=OFF \
      -DBUILD_FLYTHINGS_DEVICE=ON \
      -DCMAKE_BUILD_TYPE=Release
    cmake --build /workspace/build-t113 --parallel
    file /workspace/build-t113/libzkgui.so
  '
