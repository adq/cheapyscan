# cheapyscan

A photogrammetry rig built from 3D printer parts. A turntable rotates the
object and a second rotational axis reorients it, while the camera stays fixed.

The mechanical parts are the 3D printable models of the OpenScan Classic V1,
from [OpenScan](https://openscan.org). They are published in the
[OpenScan-Design](https://github.com/OpenScan-org/OpenScan-Design) repository
under `files/Classic/V1/`. This repository does not include them.

Motion is driven by an Arduino Mega 2560 with a RAMPS 1.4 shield, salvaged from
an old 3D printer.

## Contents

| Folder | What it is |
|---|---|
| [`firmware/`](firmware/) | Firmware for the Mega 2560 and RAMPS 1.4. Drives the two stepper motors over USB serial. Plain C, built with avr-gcc. |
| [`host/`](host/) | The PC application. Drives the board, triggers the camera, saves projects, and serves the web UI. Python. |
| [`web/`](web/) | The web UI served by the host. Svelte 5, TypeScript, three.js. |
| [`tools/`](tools/) | Development tools. `motor-console.py` drives the board by hand for testing. |

## Getting started

See [`firmware/README.md`](firmware/README.md) for the pin map, the serial
command protocol, and how to build and flash.

```
cd firmware
./scripts/setup-toolchain.sh    # AVR toolchain and serial group, once
./scripts/flash.sh              # build, test and flash
```

Then drive the motors by hand:

```
./tools/motor-console.py
```

That needs [uv](https://docs.astral.sh/uv/), which installs its own
dependencies on first run. There is no virtual environment to create.

To scan, start the host application and use the web UI it opens:

```
make run          # or `make simulate` to try it with nothing plugged in
```

See [`host/README.md`](host/README.md) for camera setup, calibration and the
scan sequence.

## Licence

MIT. See [LICENSE](LICENSE).

The firmware contains no code from any other project. The references used while
writing it, and why they carry no licensing obligation here, are recorded in
[`firmware/README.md`](firmware/README.md#licence-and-attribution).

The host application also contains no code from any other project. It follows
the scan sequence of OpenScan3, which was used as a reference only:

| Source | Licence | What was used |
|---|---|---|
| [OpenScan3](https://github.com/OpenScan-org/OpenScan3) `openscan_firmware/utils/paths/`, `controllers/services/tasks/core/scan_task.py`, `controllers/services/projects.py` | GPLv3 | Its algorithms, reimplemented independently: the constrained Fibonacci lattice, the greedy nearest-neighbour reorder, the order of steps at each position, the default scan settings, and the project folder layout and file names. |

The rig itself is built from OpenScan's designs:

| Source | Licence | What was used |
|---|---|---|
| [OpenScan-Design](https://github.com/OpenScan-org/OpenScan-Design) `files/Classic/V1/` | None stated in the repository | The 3D printable models of the OpenScan Classic V1, printed to build the rig. The rotor gear ratio (64:12) used for the default calibration was counted from these models. No model files are included here. |

A Fibonacci lattice on a sphere and greedy nearest-neighbour ordering are
standard mathematical methods, not authored works. Following the same folder
layout keeps the output usable by tools written for OpenScan.

The host's dependencies are installed by uv and npm, not included in this
repository. Two carry a copyleft licence, and both are used unmodified as
libraries: python-gphoto2 (LGPL 3.0 or later) with the libgphoto2 it bundles
(LGPL), and zipstream-ng (LGPL 3.0).
