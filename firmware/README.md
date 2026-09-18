# cheapscan firmware

Minimal firmware for an Arduino Mega 2560 with a RAMPS 1.4 shield, salvaged
from a 3D printer and reused as the motion controller for a photogrammetry rig.
It drives two stepper motors, one per axis, over USB serial. Nothing else: no
heaters, no thermistors, no fans, no G-code, no SD card.

Built with plain avr-gcc against the AVR registers directly. No Arduino core.

- Flash used: 3520 bytes of 256 KB
- RAM used: 608 bytes of 8 KB

## Hardware

| Signal | Arduino pin | AVR |
|---|---|---|
| X step | 54 (A0) | PORTF bit 0 |
| X direction | 55 (A1) | PORTF bit 1 |
| X enable | 38 | PORTD bit 7 |
| Y step | 60 (A6) | PORTF bit 6 |
| Y direction | 61 (A7) | PORTF bit 7 |
| Y enable | 56 (A2) | PORTF bit 2 |

These are the standard RAMPS 1.4 assignments, taken from Marlin's
`pins_RAMPS.h` and cross-checked against the RepRap wiki. The port and bit for
each came from the Arduino core's Mega variant file.

Motor power comes from the RAMPS 12V input. USB supplies logic power only and
cannot drive the motors.

Before applying 12V, check the current limit trimpot on each stepper driver.
The drivers are energised as soon as the firmware starts, so a current limit
set too high will heat them with the motors standing still.

Microstepping is set by the jumpers under each driver socket, not in firmware.
For an A4988 at 1/16 microstepping, all three jumpers are fitted.

## Building and flashing

Install the toolchain and get serial access:

```
./scripts/setup-toolchain.sh
```

The script covers pacman, apt-get and dnf, and adds you to the group that owns
USB serial devices (`uucp` on Arch, `dialout` elsewhere). Group membership does
not apply to a session that is already open, so log out and back in afterwards.

Then:

```
make                            # build build/cheapscan.hex
make size                       # flash and RAM usage
make flash                      # upload
make flash PORT=/dev/ttyACM1    # upload to a different port
```

Fuses are never touched, so the stock bootloader keeps working.

## Talking to it

115200 baud, 8N1. One command per line. Carriage returns are ignored, so any
terminal program works.

```
picocom -b 115200 /dev/ttyACM0
```

On start the firmware sends `cheapscan ready`.

### Commands

| Command | Meaning |
|---|---|
| `M <axis> <steps> [rate]` | Move. `steps` is signed and its sign sets direction. `rate` is in steps per second, 10 to 4000, defaulting to 400. |
| `S` | Status. |
| `Z [axis]` | Zero the position counter. Both axes if no axis is given. |
| `H <axis> <0\|1>` | Driver holding off or on for that axis. |
| `A` | Abort all motion immediately. |
| `?` | Command help. |

`axis` is `X` or `Y`. Commands are case-insensitive.

### Replies

| Reply | Meaning |
|---|---|
| `ok` | Command accepted. |
| `err <reason>` | Command rejected. |
| `done <axis>` | That axis finished its move. |
| `pos X=.. Y=.. busy X=.. Y=.. hold X=.. Y=..` | Reply to `S`. |

A move command for an axis that is already moving is rejected with `err busy`.
Both axes can move at once; send one `M` per axis.

### Example

```
S
pos X=0 Y=0 busy X=0 Y=0 hold X=1 Y=1
M X 1600 400
ok
done X
S
pos X=1600 Y=0 busy X=0 Y=0 hold X=1 Y=1
```

`done` is the signal a capture application waits for before firing the shutter.

## How it works

Each axis has its own 16-bit timer, so the two run at independent rates without
interfering. Timer1 drives X, Timer3 drives Y. Both are in CTC mode with a
prescaler of 64, giving a 4 microsecond tick, and the compare value is
`(F_CPU / 64 / rate) - 1`.

Each timer interrupt emits one complete step pulse: step pin high, a 2
microsecond wait, step pin low. Grbl uses a second timer to end the pulse, which
is unnecessary here because the top step rate is low enough that the wait costs
about 1 percent of interrupt time.

Moves run at a constant rate with no acceleration ramp. The rig turns slowly
enough that a motor will not stall from a standing start.

There are no endstops, so position is a step count relative to wherever the
axis was at power-on or when it was last zeroed.

The firmware counts steps, not degrees. The steps-per-degree constant for each
axis belongs in whatever drives it, so that calibration can change without
reflashing.

### Driver holding

Both drivers stay energised after a move by default. An object mounted off the
centre of the rotational axis will sag the moment its driver releases, which
loses the position the firmware believes it is at.

Use `H <axis> 0` to release an axis when you want it silent and cool, for
example during a long exposure, and `H <axis> 1` to hold it again.

### JTAG

`stepper_init()` disables JTAG at runtime. This is precautionary rather than
necessary, and is documented here so it does not look like a mystery.

The Y axis uses PF6 and PF7, which the ATmega2560 assigns to its JTAG interface
when the JTAGEN fuse is programmed. A stock Mega 2560 has a high fuse of 0xD8,
which leaves JTAGEN unprogrammed, so those pins are already plain GPIO. Neither
Marlin nor grbl-Mega disables JTAG, and both drive these same pins on this same
board.

It only matters if a board's fuses were changed to enable JTAG, in which case
the Y axis would never move and nothing would say why. The guard costs 18 bytes,
so it is kept rather than relying on the fuse being right.

## Layout

```
src/config.h      pin map, step rate limits, holding default
src/stepper.c/.h  timers, step pulses, position counters
src/uart.c/.h     UART0 at 115200, interrupt receive, blocking transmit
src/main.c        command parsing and the main loop
tests/            host-side parser test
scripts/          toolchain setup
```

## Tests

```
./tests/run.sh
```

This compiles `src/main.c` natively with the UART and stepper layers replaced
by stubs, and checks every command and reply. It needs a native gcc, not
avr-gcc. The timer and pin code can only be checked on the board.
