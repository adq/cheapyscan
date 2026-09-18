#!/usr/bin/env bash
#
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
#
# Build and run the host-side parser test. Needs a native gcc, not avr-gcc.
#
# A convenience wrapper so the test can be run from anywhere. The compiler
# flags live in the Makefile, so there is only one definition of how the test
# is built.

set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

exec make -C "$here/.." --no-print-directory test
