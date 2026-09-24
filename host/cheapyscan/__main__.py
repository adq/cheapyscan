# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""Command line entry point.

    cheapyscan serve               start the web UI on http://127.0.0.1:8080
    cheapyscan serve --simulate    no board or camera needed
"""

from __future__ import annotations

import argparse
import logging
import threading
import webbrowser
from pathlib import Path

from . import config


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cheapyscan", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the web UI")
    serve.add_argument("--host", default="127.0.0.1",
                       help="address to listen on (default 127.0.0.1, this machine only)")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--simulate", action="store_true",
                       help="use the simulated board and the dummy camera")
    serve.add_argument("--config", type=Path, default=config.default_config_path(),
                       help="settings file (default %(default)s)")
    serve.add_argument("--no-browser", action="store_true", help="do not open a browser")
    serve.add_argument("-v", "--verbose", action="store_true", help="log every serial line")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    import uvicorn

    from .api import create_app
    from .rig import Rig

    settings = config.load(args.config)
    rig = Rig(settings, config_path=args.config, simulate=args.simulate)
    app = create_app(rig)

    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    print(f"cheapyscan on {url}" + (" (simulated board and camera)" if args.simulate else ""), flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
