# cheapyscan host application

The program that runs a scan from a PC. It drives the rig's two motors through
the cheapyscan firmware over USB serial, triggers the camera, saves the photos
into projects, and serves a web UI in the browser to control all of it.

It uses the same photo sequence as the OpenScan3 Raspberry Pi software, so a
scan here produces the same set of viewpoints, in the same folder layout, as
OpenScan would.

## Running it

It needs [uv](https://docs.astral.sh/uv/) for the Python side and npm to build
the web UI once. From the repository root:

```
make run          # builds the web UI, then starts the host
make simulate     # the same, with a simulated board and camera
```

Or by hand:

```
cd web && npm ci && npm run build
cd ../host && uv run cheapyscan serve
```

The host listens on http://127.0.0.1:8080 and opens that page in the browser.
`--simulate` needs nothing plugged in: the board is simulated in software and
the camera draws the position into a generated image.

Options for `cheapyscan serve`:

| Option | What it does |
|---|---|
| `--simulate` | Use the simulated board and the dummy camera. |
| `--port N` | Listen on port N instead of 8080. |
| `--host ADDR` | Listen on ADDR. The default, 127.0.0.1, accepts connections from this PC only. |
| `--config FILE` | Settings file. The default is `~/.config/cheapyscan/config.json`. |
| `--no-browser` | Do not open a browser. |
| `-v` | Log every serial line sent and received. |

## Camera setup: Nikon D90

The D90 connects by USB and is driven through libgphoto2, which comes with the
`gphoto2` Python package. There is nothing else to install.

1. Connect the camera by USB and switch it on.
2. Set the lens and camera to manual focus. Autofocus hunting between shots
   slows the scan, and each photo can end up focused on a different part of
   the object.
3. Set the exposure mode to M, so every photo has the same exposure.
4. In the camera's setup menu, set the auto meter-off delay to its longest
   setting. A camera that goes to sleep between shots drops off USB.
5. On the Control page, press Check camera, then Take test photo. The photo
   is saved to `_test` inside the projects folder.

If Check camera says another program has the camera open, the desktop's file
manager has usually claimed it. Close the file manager window for the camera,
or stop the monitor that claims it:

```
pkill -f gvfs-gphoto2-volume-monitor
```

By default each photo is downloaded and nothing is left on the camera's memory
card. Turn on the `keep_on_card` camera option on the Settings page to keep a
copy on the card as well. With the camera set to RAW + JPEG, both files are
downloaded, as `scan01_000.nef` and `scan01_000.jpg`.

## First run: calibrate the axes

The firmware counts steps and knows nothing about angles. The Settings page
holds the conversion, and the defaults assume an OpenScan Classic with 200 step
motors at 1/16 microstepping:

| Axis | Firmware axis | Steps per revolution | Limits |
|---|---|---|---|
| Rotor (tilt) | Y | 17067 (64:12 gear) | 0° to 140° |
| Turntable | X | 3200 (direct drive) | none |

Check them once on the Control page:

1. Press Connect, then Set reference with the object level.
2. Go to rotor 45°. The top of the object should tilt towards the camera,
   because a lower rotor angle means a view from further above. If the
   turntable moves instead, swap the firmware axes on the Settings page. If
   the object tilts away from the camera, turn on Reverse direction for the
   rotor.
3. At rotor 45°, measure the tilt of the object's platform with a protractor
   or a phone level app. It should be 45° from level. If it is not, scale the
   rotor's steps per revolution by the ratio of 45 to the measured angle.
4. Press +45° on the turntable eight times. It should end exactly where it
   started. If it does not, correct the turntable's steps per revolution.

## Scanning

1. On the Control page, press Connect.
2. Jog the rotor until the object sits level (90°), and the turntable until
   its marked edge faces the camera (0°). Press Set reference.
3. On the Scan page, choose or create a project, check the settings, and
   press Start scan.

The rig has no endstops, so the reference position is how it knows where the
motors are. Set it again whenever you reconnect, because opening the serial
port resets the board. Set it again too if an axis may have slipped.

During a scan, the 3D view fills in each viewpoint as its photo is taken, and
the latest photo appears alongside. Pause stops after the current photo. Cancel
stops after the current photo and returns the rig to the end position. The Stop
button in the header halts both motors at once and ends the scan.

A scan that stops part way, for any reason, can be resumed from the Projects
page. It continues from the first photo not yet taken.

## The photo sequence

Each scan follows the steps of OpenScan3's scan task.

1. **Plan the positions.** The positions form a Fibonacci lattice over a band
   of a sphere around the object. They are spaced evenly in the cosine of the
   rotor angle, so each photo covers the same area of the sphere. Each step
   turns the turntable by the golden-ratio fraction of a turn, about 222.5°.
   The first position is at the highest rotor angle.
2. **Reorder the positions.** If Reorder for the shortest moves is on, the
   positions are visited nearest first, starting from the current position.
   Both motors move together, so a move takes as long as the slower motor.
3. **Photograph each position.** At each position the rig moves both axes, waits
   for the pause time, takes the photo, and saves its metadata and the scan's
   progress.
4. **Return to the end position.** The default is rotor 90°, turntable 0°.

Photos are named after the position's place in the Fibonacci sequence, not the
order they were taken in. `scan01_042.jpg` is always the same view of the
object, whether or not the path was reordered.

Two settings differ from OpenScan3, because the D90 and the Classic's moving
object behave differently from a Pi camera on a Mini:

- The pause before each photo defaults to 500 ms rather than 0, so the object
  can stop swaying after the rotor tilts it.
- The reorder estimates move time at the firmware's constant step rate.
  OpenScan3 uses an acceleration ramp, which this firmware does not have.

Focus stacking is not supported yet.

## Files

```
~/cheapyscan-projects/<project>/project.json
~/cheapyscan-projects/<project>/thumbnail.jpg
~/cheapyscan-projects/<project>/scan01/scan.json        settings, progress, status
~/cheapyscan-projects/<project>/scan01/path.json        every position, in the order taken
~/cheapyscan-projects/<project>/scan01/scan01_000.jpg
~/cheapyscan-projects/<project>/scan01/metadata/scan01_000.json
```

The projects folder can be changed on the Settings page. The Projects page
downloads a whole project, or only its photos, as a zip file.

## Adding a camera backend

A backend is one Python file in `cheapyscan/cameras/`. It defines a subclass
of `Camera` from `base.py` and registers it under a name:

```python
class MyCamera(Camera):
    description = "Shown on the Settings page"
    default_options = {"some_option": 1}

    def connect(self): ...
    def close(self): ...
    def info(self): return {"model": "..."}
    def capture(self, dest_dir, stem, context):
        # Save dest_dir / f"{stem}.jpg" and return the paths written.
        ...

register("mycamera", MyCamera)
```

Then import it in `cheapyscan/cameras/__init__.py`. It appears on the Settings
page with its options. `capture` runs in a worker thread, so it can block.

## Developing

```
uv run pytest                     # host tests, from host/
cd ../web && npm run check        # web UI type check
```

To work on the web UI with hot reload, run the host with
`uv run cheapyscan serve --simulate --no-browser` from `host/` and
`npm run dev` from `web/`. Then open the address `npm run dev` prints. It
passes `/api` through to the host.

| Path | What it is |
|---|---|
| `cheapyscan/firmware.py` | Serial protocol client. |
| `cheapyscan/simulator.py` | Simulated board with the same protocol. |
| `cheapyscan/motion.py` | Converts between degrees and steps, and enforces the limits. |
| `cheapyscan/path.py` | Fibonacci lattice and nearest-neighbour reorder. |
| `cheapyscan/scan.py` | The scan sequence. |
| `cheapyscan/rig.py` | Board, motors, camera and scan together. |
| `cheapyscan/projects.py` | Folder layout, thumbnails and zip contents. |
| `cheapyscan/cameras/` | Camera backends. |
| `cheapyscan/api/` | HTTP and WebSocket API for the web UI. |
| `../web/` | The web UI: Svelte 5, TypeScript, three.js. |
