#!/usr/bin/env bash

# Copyright (c) 2026 Alex313031 and gz83.

set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="$HERE/.config/thorium-shell"
CACHE="$HERE/.config/cache-shell"

mkdir -p -- "$PROFILE" "$CACHE"
export LD_LIBRARY_PATH="$HERE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

exec -a "$0" "$HERE/thorium_shell" \
  "--disable-machine-id" \
  "--disable-encryption" \
  "--user-data-dir=$PROFILE" \
  "--disk-cache-dir=$CACHE" \
  "--enable-experimental-web-platform-features" \
  "--enable-clear-hevc-for-testing" \
  "$@"
