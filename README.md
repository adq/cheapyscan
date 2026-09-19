# cheapyscan

A photogrammetry rig built from 3D printer parts. A turntable rotates the
object and a second rotational axis reorients it, while the camera stays fixed.

Motion is driven by an Arduino Mega 2560 with a RAMPS 1.4 shield, salvaged from
an old 3D printer.

## Contents

| Folder | What it is |
|---|---|
| [`firmware/`](firmware/) | Firmware for the Mega 2560 and RAMPS 1.4. Drives the two stepper motors over USB serial. Plain C, built with avr-gcc. |

The host application that drives the firmware and triggers the camera is not
written yet.

## Getting started

See [`firmware/README.md`](firmware/README.md) for the pin map, the serial
command protocol, and how to build and flash.

```
cd firmware
./scripts/setup-toolchain.sh
make
make flash
```

## Licence

MIT. See [LICENSE](LICENSE).

The firmware contains no code from any other project. The references used while
writing it, and why they carry no licensing obligation here, are recorded in
[`firmware/README.md`](firmware/README.md#licence-and-attribution).
