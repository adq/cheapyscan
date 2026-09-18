#!/usr/bin/env bash
#
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
#
# Build and run the host-side parser test. Needs a native gcc, not avr-gcc.

set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
out=$here/../build/test_parser

mkdir -p "$(dirname "$out")"

gcc -std=gnu11 -Wall -Wextra -O1 -g \
    -I"$here/fake" \
    "$here/test_parser.c" -o "$out"

"$out"
