#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyserial>=3.5"]
# ///
#
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
#
"""Manual test console for the cheapyscan firmware.

Opens the board, prints everything it sends, and passes typed lines straight
through to it, so this exercises the real serial protocol rather than wrapping
it in something friendlier.

    ./motor-console.py                      find the board, open a prompt
    ./motor-console.py --port /dev/ttyACM1
    ./motor-console.py -c "M X 1600 400"    send one command and exit
    ./motor-console.py --list               list serial ports and exit

uv installs pyserial on first run, so there is no environment to set up.
"""

import argparse
import queue
import sys
import threading
import time

import serial
from serial.tools import list_ports

BAUD = 115200

# USB identifiers seen on genuine Arduino boards and the common clones. Used
# only to pick the likeliest port when several are present, never to reject
# one, because plenty of working boards are not on this list.
LIKELY_VIDS = {
    0x2341,  # Arduino
    0x2A03,  # Arduino (arduino.org era)
    0x1A86,  # CH340, most clones
    0x0403,  # FTDI
    0x10C4,  # CP210x
}


class Board:
    """A serial connection with a background reader.

    The firmware sends `done <axis>` when a move finishes, which arrives
    whenever the motor happens to stop rather than in reply to anything. So a
    reader thread prints every incoming line as it lands, and separately
    signals whichever axis just finished.
    """

    def __init__(self, port, echo=True):
        self.echo = echo
        self.serial = serial.Serial(port, BAUD, timeout=0.1)
        self.lines = queue.Queue()
        self.done = {"X": threading.Event(), "Y": threading.Event()}
        self.ready = threading.Event()
        self._stop = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self.serial.read(256)
            except (serial.SerialException, OSError):
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("utf-8", "replace").strip()
                if line:
                    self._handle(line)

    def _handle(self, line):
        if self.echo:
            print(f"< {line}", flush=True)
        self.lines.put(line)
        if line.endswith("ready"):
            self.ready.set()
        if line.startswith("done "):
            axis = line.split(None, 1)[1].strip().upper()
            if axis in self.done:
                self.done[axis].set()

    def send(self, text):
        if self.echo:
            print(f"> {text}", flush=True)
        self.serial.write((text + "\n").encode("ascii", "replace"))
        self.serial.flush()

    def wait_done(self, axis, timeout):
        """Block until that axis reports done. Returns False on timeout."""
        event = self.done[axis]
        event.clear()
        return event.wait(timeout)

    def drain(self):
        """Discard anything received so far, so a later wait sees fresh lines."""
        while True:
            try:
                self.lines.get_nowait()
            except queue.Empty:
                return

    def wait_line(self, prefix, timeout):
        """Wait for a received line starting with prefix. Returns it, or None."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty:
                return None
            if line.startswith(prefix):
                return line

    def close(self):
        self._stop.set()
        try:
            self.serial.close()
        except Exception:
            pass


def find_port(explicit=None):
    if explicit:
        return explicit

    ports = list(list_ports.comports())
    if not ports:
        raise SystemExit(
            "error: no serial ports found.\n"
            "Plug the board in and check it appears:  ls /dev/ttyACM*\n"
            "If it still does not show up, try a different USB cable. "
            "Charge-only cables carry power but no data."
        )

    likely = [p for p in ports if p.vid in LIKELY_VIDS]
    candidates = likely or ports

    if len(candidates) == 1:
        return candidates[0].device

    listing = "\n".join(f"  {p.device}  {p.description}" for p in candidates)
    raise SystemExit(
        f"error: more than one serial port found:\n{listing}\n"
        "Say which one to use:  --port <device>"
    )


def describe_ports():
    ports = list(list_ports.comports())
    if not ports:
        print("no serial ports found")
        return
    for p in ports:
        ident = f"{p.vid:04x}:{p.pid:04x}" if p.vid is not None else "     "
        print(f"{p.device}  {ident}  {p.description}")


LOCAL_HELP = """\
Typed lines go straight to the firmware. Send ? for its own command list.

This console adds a few of its own, all starting with a colon:

  :sweep <axis> <steps> <rate> [cycles]   move out and back, repeatedly
  :ports                                  list serial ports
  :help                                   this text
  :quit                                   leave (also ctrl-d)

A sweep is the useful manual check: if the axis does not return to the
position it started from, it is losing steps and the rate is too high or the
driver current too low.
"""


def do_sweep(board, args):
    """Move an axis out and back, checking it returns to where it started."""
    try:
        axis = args[0].upper()
        steps = int(args[1])
        rate = int(args[2])
        cycles = int(args[3]) if len(args) > 3 else 1
    except (IndexError, ValueError):
        print("usage: :sweep <axis> <steps> <rate> [cycles]")
        return
    if axis not in ("X", "Y"):
        print("axis must be X or Y")
        return

    # Generous: the move itself plus time for the board to answer.
    timeout = abs(steps) / max(rate, 1) + 5.0

    for n in range(1, cycles + 1):
        print(f"-- cycle {n} of {cycles}")
        for direction in (steps, -steps):
            board.wait_done(axis, 0)  # clear any stale flag
            board.send(f"M {axis} {direction} {rate}")
            if not board.wait_done(axis, timeout):
                print(f"!! no 'done {axis}' within {timeout:.1f}s, stopping")
                board.send("A")
                return
    board.drain()
    board.send("S")
    # Wait for the reply so it prints before the summary rather than after it.
    board.wait_line("pos ", 2.0)
    print("-- sweep finished. The position above should match where it started.")


def repl(board):
    print(LOCAL_HELP)
    while True:
        try:
            line = input("").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue

        if line.startswith(":"):
            parts = line[1:].split()
            cmd = parts[0].lower() if parts else ""
            if cmd in ("quit", "exit", "q"):
                return
            if cmd == "help":
                print(LOCAL_HELP)
            elif cmd == "ports":
                describe_ports()
            elif cmd == "sweep":
                do_sweep(board, parts[1:])
            else:
                print(f"unknown console command: :{cmd}  (try :help)")
            continue

        board.send(line)


def main():
    parser = argparse.ArgumentParser(
        description="Manual test console for the cheapyscan firmware."
    )
    parser.add_argument("--port", help="serial device, found automatically if omitted")
    parser.add_argument(
        "-c",
        "--command",
        action="append",
        default=[],
        metavar="CMD",
        help="send a command and exit; repeat for several",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="with -c, how long to keep listening after the last command (default 1)",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=6.0,
        metavar="SECONDS",
        help="how long to wait for the board's banner after connecting (default 6)",
    )
    parser.add_argument("--list", action="store_true", help="list serial ports and exit")
    args = parser.parse_args()

    if args.list:
        describe_ports()
        return 0

    port = find_port(args.port)

    try:
        board = Board(port)
    except serial.SerialException as exc:
        raise SystemExit(f"error: cannot open {port}: {exc}\n{permission_hint(port)}")

    # Opening the port asserts DTR, which resets the board, so the firmware
    # restarts here and its position counters go back to zero. Wait for its
    # banner rather than guessing at a delay: until the bootloader has handed
    # over, anything sent is thrown away.
    print(f"# connected to {port} at {BAUD}")
    print("# the board resets on connect, so positions start at zero")

    if not board.ready.wait(args.connect_timeout):
        print(
            f"# no banner within {args.connect_timeout:.0f}s. Carrying on anyway,"
            " but if commands are ignored, reset the board and reconnect.",
            file=sys.stderr,
        )

    try:
        if args.command:
            for cmd in args.command:
                board.send(cmd)
            time.sleep(args.wait)
        else:
            repl(board)
    finally:
        # Leave nothing moving behind us.
        try:
            board.send("A")
            time.sleep(0.2)
        except Exception:
            pass
        board.close()
        print("# closed")

    return 0


def permission_hint(port):
    import grp
    import os

    try:
        group = grp.getgrgid(os.stat(port).st_gid).gr_name
    except Exception:
        return ""

    if group in (grp.getgrgid(g).gr_name for g in os.getgroups()):
        return (
            f"You are a member of '{group}', so this shell predates that change.\n"
            "Log out and back in, then try again."
        )
    return (
        f"Add yourself to the '{group}' group, then log out and back in:\n"
        f"    sudo usermod -aG {group} {os.getlogin()}"
    )


if __name__ == "__main__":
    sys.exit(main())
