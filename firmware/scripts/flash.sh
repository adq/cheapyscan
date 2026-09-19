#!/usr/bin/env bash
#
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
#
# Build the firmware and flash it to the board.
#
#   ./scripts/flash.sh                    find the board automatically
#   ./scripts/flash.sh /dev/ttyACM1       use a specific port
#   ./scripts/flash.sh --no-build         flash what is already built
#
# The build runs the host tests and stops on a failure, so a broken parser
# never reaches the board. Pass --no-build to skip that.

set -euo pipefail

say()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
die()  { warn "error: $*"; exit 1; }

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
firmware_dir=$(cd -- "$here/.." && pwd)

build=1
port=""

for arg in "$@"; do
    case "$arg" in
        --no-build) build=0 ;;
        -h|--help)
            # Print the header comment block, stopping at the first line that
            # is not a comment, so this stays right when the header is edited.
            awk 'NR<6 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' \
                "${BASH_SOURCE[0]}"
            exit 0
            ;;
        -*)         die "unknown option: $arg" ;;
        *)          port=$arg ;;
    esac
done

# ------------------------------------------------------------------ build ---

if [ "$build" -eq 1 ]; then
    say "building"
    make -C "$firmware_dir" --no-print-directory
    say ""
fi

hex=$firmware_dir/build/cheapyscan.hex
[ -f "$hex" ] || die "no firmware at $hex. Run without --no-build."

# ------------------------------------------------------------------- port ---

if [ -z "$port" ]; then
    mapfile -t found < <(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || true)

    case "${#found[@]}" in
        0)
            die "no serial device found.
Plug the board in and check it appears:  ls /dev/ttyACM*
If it still does not show up, try a different USB cable. Charge-only
cables carry power but no data."
            ;;
        1)
            port=${found[0]}
            say "found board at $port"
            ;;
        *)
            die "more than one serial device found:
$(printf '  %s\n' "${found[@]}")
Say which one to use:  $0 <port>"
            ;;
    esac
fi

[ -e "$port" ] || die "$port does not exist"

# ------------------------------------------------------- permission check ---

if [ ! -w "$port" ]; then
    owner_group=$(stat -c '%G' "$port")
    warn "error: no write access to $port (owned by group '$owner_group')."
    warn ""
    if id -nG | tr ' ' '\n' | grep -qx "$owner_group"; then
        warn "You are a member of '$owner_group', so this shell predates that"
        warn "change. Log out and back in, then try again."
    else
        warn "Add yourself to that group, then log out and back in:"
        warn "    sudo usermod -aG $owner_group $(id -un)"
    fi
    exit 1
fi

# ------------------------------------------------------------------ flash ---

say "flashing $port"
say ""

# Delegated to the Makefile so the avrdude invocation has one definition.
make -C "$firmware_dir" --no-print-directory flash PORT="$port"

say ""
say "done. Talk to the board with:  ../tools/motor-console.py"
