# cheapyscan firmware

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

### Motor wiring

Switch off the 12V supply before connecting or disconnecting a motor. Unplugging
a motor from a powered driver can destroy the driver, and the drivers are
energised whenever the firmware is running.

A bipolar stepper has two coils, each with two wires. Each coil must sit on an
adjacent pair of pins on the driver's four-pin motor header. To find the pairs,
measure resistance between the wires with a multimeter: the two wires of one
coil read a few ohms, and wires from different coils read open circuit.

If a coil is split across the two pairs, the motor judders or buzzes in place
instead of turning. Salvaged motors often have cables wired for a different
board, so check each one before first use.

Which coil goes on which pair, and which way round each coil's wires go, only
affects the direction of rotation. To reverse an axis, either reverse the two
wires of one coil or set `X_DIR_INVERT` or `Y_DIR_INVERT` to 1 in
`src/config.h` and reflash.

### Setting the driver current

Each A4988 driver has a small trimpot that sets the maximum current it sends
through each motor coil. Set it before running the rig for any length of time.
Too low and the motor stalls or skips steps. Too high and the driver and motor
overheat, which matters here because the firmware keeps the drivers energised
between moves.

The trimpot sets a reference voltage, Vref. The current limit follows from
Vref and the value of the driver's two current sense resistors:

```
I_max = Vref / (8 × Rs)        Vref = 8 × I_max × Rs
```

`Rs` is in ohms. The sense resistors are the two small black surface-mount
parts next to the driver chip. Their marking gives the value:

| Marking | Rs | Vref per amp |
|---|---|---|
| R050 | 0.05 Ω | 0.4 V |
| R068 | 0.068 Ω | 0.544 V |
| R100 | 0.1 Ω | 0.8 V |
| R200 | 0.2 Ω | 1.6 V |

The `R` marks the decimal point, so `R100` is 0.100 Ω, not 10 Ω. A plain
three-digit code with no `R`, such as `100`, is a different part: in that code
`100` means 10 Ω. Check you are reading the resistors beside the chip. Clone
boards differ between manufacturers, so read the marking on your own drivers
rather than assuming a value. The drivers on this rig are marked `R100`.

There is one sense resistor per motor coil. The A4988 drives each coil through
its own H-bridge, and each bridge's current returns to ground through its own
resistor. The chip reads the voltage across each resistor and switches that
bridge off briefly whenever the coil reaches its limit, which holds each coil
at its set current. The coils need separate feedback because microstepping
drives them at different currents at the same moment, one following a sine and
the other a cosine. Vref is shared: the chip scales it for each coil according
to the microstep position, so one trimpot sets the maximum for both, and both
resistors must have the same value.

To choose a target current, find the rated current per phase on the motor's
label or datasheet and stay at or below it. The rig turns slowly, so a lower
current is usually enough and runs cooler. Without a heatsink or fan, an A4988
handles roughly 1 A per coil.

To set it:

1. With the 12V supply on and the motors idle, measure the voltage between the
   trimpot's metal top and a ground pin on the RAMPS board.
2. Turn the trimpot a small amount and measure again. Use an insulated
   screwdriver, because a metal tip slipping onto nearby pins can damage the
   driver. The direction that raises Vref varies between boards, so find it by
   measuring.
3. Stop when the reading matches the Vref for your target current.
4. Run a few moves, then touch the driver chip and the motor. Warm is normal.
   If either is too hot to keep a finger on, lower Vref.

For example, a motor rated at 1.0 A on a driver with `R100` resistors needs
Vref = 8 × 1.0 × 0.1 = 0.8 V. Setting 0.6 V gives 0.75 A, which is usually
plenty for a turntable.

Sources: the [Pololu A4988 product page](https://www.pololu.com/product/1182)
for the formula, the cooling limit and the power-off warning, and the
[RepRap wiki](https://reprap.org/wiki/A4988_vs_DRV8825_Chinese_Stepper_Driver_Boards)
for the resistor values found on clone boards.

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
make                            # build build/cheapyscan.hex, then run the tests
make firmware                   # build only, no tests
make test                       # run the tests only
make size                       # flash and RAM usage
make flash                      # upload
make flash PORT=/dev/ttyACM1    # upload to a different port
```

`make` runs the host tests after the build and stops on a failure, so a broken
parser never reaches `make flash`.

Fuses are never touched, so the stock bootloader keeps working.

`scripts/flash.sh` wraps all of that: it builds, runs the tests, finds the
board, and flashes it. It stops with a readable message if no board is
connected, if more than one serial device is present, or if you lack write
access to the port.

```
./scripts/flash.sh                 # find the board automatically
./scripts/flash.sh /dev/ttyACM1    # use a specific port
./scripts/flash.sh --no-build      # flash what is already built
```

## Talking to it

115200 baud, 8N1. One command per line. Carriage returns are ignored, so any
terminal program works.

```
../tools/motor-console.py     # finds the board, waits for its banner
picocom -b 115200 /dev/ttyACM0
```

On start the firmware sends `cheapyscan ready`.

Opening the port asserts DTR, which resets the board, so the firmware restarts
and both position counters go back to zero every time you connect.

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

`make` runs these automatically. To run them on their own:

```
make test        # or ./tests/run.sh from anywhere
```

This compiles `src/main.c` natively with the UART and stepper layers replaced
by stubs, and checks every command and reply. It needs a native gcc, not
avr-gcc, so it runs on a machine with no AVR toolchain installed.

`tests/run.sh` is a wrapper around `make test`, so the compiler flags have only
one definition.

The timer and pin code can only be checked on the board.

## Licence and attribution

This firmware is MIT licensed. See [LICENSE](../LICENSE) at the repository root.

No code from any other project is included here. It was written against the AVR
registers directly, and the sources below were used as references rather than
copied from. They are recorded so that anyone auditing the licensing can check
the same things.

| Source | Licence | What was used |
|---|---|---|
| [Marlin](https://github.com/MarlinFirmware/Marlin) `Marlin/src/pins/ramps/pins_RAMPS.h` | GPLv3 | The six RAMPS 1.4 pin numbers for the X and Y steppers. |
| [RepRap wiki, RAMPS 1.4](https://reprap.org/wiki/RAMPS_1.4) | CC BY-SA 3.0 | Independent confirmation of those same pin numbers. |
| [ArduinoCore-avr](https://github.com/arduino/ArduinoCore-avr) `variants/mega/pins_arduino.h` | LGPL 2.1 | The AVR port and bit each Arduino pin number maps to. |
| [Grbl](https://github.com/gnea/grbl) `grbl/stepper.c` | GPLv3 | Read for its interrupt structure. Informed the choice of a 16-bit timer in CTC mode, and nothing else. |

On the pin numbers: which Mega pin the RAMPS 1.4 board routes to a given stepper
driver input is a fact about a circuit board, not an authored work, and the same
numbers were confirmed from two independent sources.

On Grbl: the design here is structurally different. Grbl runs a single stepper
interrupt that walks a Bresenham line across all axes from a pre-computed
segment buffer, and uses a second timer to end each step pulse. This firmware
gives each axis its own timer, has no Bresenham, no segment buffer and no
planner, and ends the pulse inside the same interrupt.

If you later paste actual code from Marlin, Repetier or Grbl into this project,
all three are GPLv3 and that licence would attach to the result. The MIT licence
above would no longer be accurate.
