#!/usr/bin/env bash

# Copyright 2026 The Chromium Authors, the AUR, Alex313031, and gz83.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="$HERE/.config/thorium"
CACHE="$HERE/.config/cache"
FLAGS_FILE="$HERE/.config/thorium-flags.conf"

export CHROME_WRAPPER="$HERE/THORIUM-PORTABLE"
export CHROME_VERSION_EXTRA="stable, (Portable)"
export GNOME_DISABLE_CRASH_DIALOG=SET_BY_THORIUM
export LD_LIBRARY_PATH="$HERE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

usage() {
  cat <<'EOF'
Usage: THORIUM-PORTABLE [--temp-profile] [--safe-mode] [options] [URL]

  --temp-profile  Use a new profile and remove it after Thorium exits.
  --safe-mode     Disable chrome://flags experiments for this launch.
  -h, --help      Show this help.

Additional options are passed directly to Thorium.
EOF
}

temporary_profile=""
safe_mode=false
while (($#)); do
  case "$1" in
    -h | -help | --help)
      usage
      exit 0
      ;;
    --temp-profile)
      temporary_profile="$(mktemp -d -t thorium-portable.XXXXXXXX)"
      PROFILE="$temporary_profile"
      CACHE="$temporary_profile/cache"
      shift
      ;;
    --safe-mode)
      safe_mode=true
      shift
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

mkdir -p -- "$PROFILE" "$CACHE"
pending_crashes="$PROFILE/Crash Reports/pending"
if [[ -d "$pending_crashes" ]]; then
  find "$pending_crashes" -type f -mtime +30 \
    \( -name '*.meta' -o -name '*.dmp' \) -delete
fi

declare -a user_flags=()
if [[ -f "$FLAGS_FILE" ]]; then
  while IFS= read -r flag || [[ -n "$flag" ]]; do
    flag="${flag%$'\r'}"
    [[ -z "$flag" || "$flag" == \#* ]] || user_flags+=("$flag")
  done < "$FLAGS_FILE"
fi
if $safe_mode; then
  user_flags+=("--no-experiments")
fi

command=(
  "$HERE/thorium"
  "--disable-machine-id"
  "--disable-encryption"
  "--user-data-dir=$PROFILE"
  "--disk-cache-dir=$CACHE"
  "${user_flags[@]}"
  "$@"
)

if [[ -n "$temporary_profile" ]]; then
  trap 'rm -rf -- "$temporary_profile"' EXIT
  echo "Using temporary profile: $temporary_profile"
  "${command[@]}"
else
  exec -a "$0" "${command[@]}"
fi
