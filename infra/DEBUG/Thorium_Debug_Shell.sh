#!/bin/sh

# Copyright (c) 2026 Alex313031 and gz83.

set -eu

HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export LD_LIBRARY_PATH="${HERE}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
exec "${HERE}/thorium_ui_debug_shell" --debug "$@"
