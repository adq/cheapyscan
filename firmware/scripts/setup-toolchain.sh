#!/usr/bin/env bash
#
# Install the AVR toolchain needed to build and flash this firmware, and add
# the current user to the group that owns USB serial devices.
#
# Safe to run more than once. Uses sudo only for the package install and the
# group change. Never touches AVR fuses, so the board keeps its stock
# bootloader.

set -euo pipefail

say()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
die()  { warn "error: $*"; exit 1; }

# ------------------------------------------------------------ distribution ---

if command -v pacman >/dev/null 2>&1; then
    PKG_MANAGER=pacman
    PACKAGES=(avr-gcc avr-libc avrdude)
    SERIAL_GROUP=uucp
elif command -v apt-get >/dev/null 2>&1; then
    PKG_MANAGER=apt-get
    PACKAGES=(gcc-avr avr-libc avrdude)
    SERIAL_GROUP=dialout
elif command -v dnf >/dev/null 2>&1; then
    PKG_MANAGER=dnf
    PACKAGES=(avr-gcc avr-libc avrdude)
    SERIAL_GROUP=dialout
else
    die "no supported package manager found (looked for pacman, apt-get, dnf).
Install an AVR toolchain by hand: avr-gcc, avr-libc and avrdude."
fi

say "package manager: $PKG_MANAGER"

# ----------------------------------------------------------------- install ---

if command -v avr-gcc >/dev/null 2>&1 && command -v avrdude >/dev/null 2>&1; then
    say "toolchain already present, skipping install"
else
    say "installing: ${PACKAGES[*]}"
    case "$PKG_MANAGER" in
        pacman)
            sudo pacman -S --needed --noconfirm "${PACKAGES[@]}"
            ;;
        apt-get)
            sudo apt-get update
            sudo apt-get install -y "${PACKAGES[@]}"
            ;;
        dnf)
            sudo dnf install -y "${PACKAGES[@]}"
            ;;
    esac
fi

# ------------------------------------------------------------ serial group ---

USER_NAME=${SUDO_USER:-$(id -un)}
GROUP_ADDED=0

if ! getent group "$SERIAL_GROUP" >/dev/null 2>&1; then
    warn "note: group '$SERIAL_GROUP' does not exist on this system."
    warn "      check which group owns /dev/ttyACM* and add yourself to it."
elif id -nG "$USER_NAME" | tr ' ' '\n' | grep -qx "$SERIAL_GROUP"; then
    say "user '$USER_NAME' is already in group '$SERIAL_GROUP'"
else
    say "adding user '$USER_NAME' to group '$SERIAL_GROUP'"
    sudo usermod -aG "$SERIAL_GROUP" "$USER_NAME"
    GROUP_ADDED=1
fi

# ------------------------------------------------------------ verification ---

say ""
say "verification"
say "------------"

if command -v avr-gcc >/dev/null 2>&1; then
    say "avr-gcc:  $(avr-gcc --version | head -n1)"
else
    die "avr-gcc still not on PATH after install"
fi

if command -v avrdude >/dev/null 2>&1; then
    say "avrdude:  $(avrdude -v 2>&1 | grep -i -m1 'version' | sed 's/^ *//')"
else
    die "avrdude still not on PATH after install"
fi

SERIAL_DEVICES=$(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || true)
if [ -n "$SERIAL_DEVICES" ]; then
    say "serial:   $(printf '%s ' $SERIAL_DEVICES)"
else
    say "serial:   no /dev/ttyACM* or /dev/ttyUSB* device found."
    say "          plug the board in, then run: ls /dev/ttyACM*"
fi

say ""
if [ "$GROUP_ADDED" -eq 1 ]; then
    say "You were added to group '$SERIAL_GROUP'. Group membership does not apply"
    say "to the session you are in now, so log out and back in before flashing."
fi
say "Build with: make"
say "Flash with: make flash PORT=/dev/ttyACM0"
