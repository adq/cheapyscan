# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""HTTP and WebSocket API for the web UI, all under /api.

The built web UI (web/dist) is served from / when it exists.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from zipstream import ZIP_STORED, ZipStream

from .. import cameras, config
from ..firmware import list_ports
from ..projects import ProjectError, read_json
from ..rig import Rig, RigError

log = logging.getLogger(__name__)

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


class MoveRequest(BaseModel):
    theta: float | None = None
    phi: float | None = None


class JogRequest(BaseModel):
    axis: Literal["rotor", "turntable"]
    degrees: float


class HoldRequest(BaseModel):
    axis: Literal["rotor", "turntable"]
    on: bool


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


def create_app(rig: Rig, web_dist: Path | None = WEB_DIST) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await rig.shutdown()

    app = FastAPI(title="cheapyscan", lifespan=lifespan)
    api = APIRouter(prefix="/api")

    @app.exception_handler(RigError)
    async def rig_error(_req: Request, e: RigError):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(ProjectError)
    async def project_error(_req: Request, e: ProjectError):
        return JSONResponse({"detail": str(e)}, status_code=404 if str(e).startswith("No ") else 400)

    # ---- device ------------------------------------------------------------

    @api.get("/status")
    async def get_status():
        return rig.status()

    @api.get("/config", response_model=config.Settings)
    async def get_config():
        return rig.settings

    @api.put("/config", response_model=config.Settings)
    async def put_config(new: config.Settings):
        rig.update_settings(new)
        return rig.settings

    @api.get("/serial-ports")
    async def serial_ports():
        return list_ports()

    @api.post("/device/connect")
    async def connect():
        await rig.connect()
        return rig.status()

    @api.post("/device/disconnect")
    async def disconnect():
        await rig.disconnect()
        return rig.status()

    # ---- motors ------------------------------------------------------------

    @api.post("/motors/move")
    async def move(req: MoveRequest):
        return await rig.move_to(req.theta, req.phi)

    @api.post("/motors/jog")
    async def jog(req: JogRequest):
        return await rig.move_by(req.axis, req.degrees)

    @api.post("/motors/reference")
    async def reference():
        return await rig.set_reference()

    @api.post("/motors/hold")
    async def hold(req: HoldRequest):
        return await rig.set_hold(req.axis, req.on)

    @api.post("/motors/abort")
    async def abort():
        return await rig.abort()

    # ---- camera ------------------------------------------------------------

    @api.get("/camera/backends")
    async def camera_backends():
        return cameras.available()

    @api.get("/camera/info")
    async def camera_info():
        return await rig.camera_info()

    @api.post("/camera/test-capture")
    async def test_capture():
        return await rig.test_capture()

    @api.get("/camera/test-photos/{filename}")
    async def test_photo(filename: str):
        return FileResponse(rig.test_photo_path(filename))

    # ---- path --------------------------------------------------------------

    @api.post("/path/preview")
    async def path_preview(s: config.ScanSettings):
        return rig.preview_path(s)

    # ---- projects ----------------------------------------------------------

    def scan_view(project: str, data: dict) -> dict:
        # A scan left "running" on disk by a crash or restart is interrupted.
        active = rig.scan and rig.scan.active and rig.scan.project == project and rig.scan.scan_index == data["index"]
        if data.get("status") in ("running", "paused", "cancelling") and not active:
            data = {**data, "status": "interrupted"}
        if active:
            data = {**data, "status": rig.scan.state}
        return data

    @api.get("/projects")
    async def projects_list():
        return rig.projects.list()

    @api.post("/projects")
    async def projects_create(req: ProjectCreate):
        return rig.projects.create(req.name.strip(), req.description)

    @api.get("/projects/{name}")
    async def project_get(name: str):
        p = rig.projects
        return {**p.summary(name), "scans": [scan_view(name, s) for s in p.scans(name)]}

    @api.delete("/projects/{name}")
    async def project_delete(name: str):
        if rig.scan and rig.scan.active and rig.scan.project == name:
            raise RigError("That project has a scan running.")
        rig.projects.delete(name)
        return {"ok": True}

    @api.get("/projects/{name}/thumbnail")
    async def project_thumbnail(name: str):
        f = rig.projects.project_dir(name) / "thumbnail.jpg"
        if not f.exists():
            raise HTTPException(404, "No thumbnail yet.")
        return FileResponse(f, headers={"Cache-Control": "no-cache"})

    @api.post("/projects/{name}/scans")
    async def scan_start(name: str, s: config.ScanSettings):
        return await rig.start_scan(name, s)

    @api.get("/projects/{name}/scans/{index}")
    async def scan_get(name: str, index: int):
        p = rig.projects
        return {**scan_view(name, p.read_scan(name, index)), "photos": p.photos(name, index)}

    @api.delete("/projects/{name}/scans/{index}")
    async def scan_delete(name: str, index: int):
        if rig.scan and rig.scan.active and rig.scan.project == name and rig.scan.scan_index == index:
            raise RigError("That scan is running.")
        rig.projects.delete_scan(name, index)
        return {"ok": True}

    @api.get("/projects/{name}/scans/{index}/path")
    async def scan_path(name: str, index: int):
        return read_json(rig.projects.scan_dir(name, index) / "path.json")

    @api.post("/projects/{name}/scans/{index}/pause")
    async def scan_pause(name: str, index: int):
        t = rig.active_scan(name, index)
        t.pause()
        return t.snapshot()

    @api.post("/projects/{name}/scans/{index}/resume")
    async def scan_resume(name: str, index: int):
        # Resume a paused scan, or restart one that was interrupted.
        if rig.scan and rig.scan.active and rig.scan.project == name and rig.scan.scan_index == index:
            rig.scan.resume()
            return rig.scan.snapshot()
        return await rig.resume_scan(name, index)

    @api.post("/projects/{name}/scans/{index}/cancel")
    async def scan_cancel(name: str, index: int):
        t = rig.active_scan(name, index)
        t.cancel()
        return t.snapshot()

    @api.get("/projects/{name}/scans/{index}/photos/{filename}")
    async def photo(name: str, index: int, filename: str, size: int | None = Query(None)):
        p = rig.projects
        if size:
            return FileResponse(p.thumbnail(name, index, filename, size))
        return FileResponse(p.photo_path(name, index, filename))

    @api.get("/projects/{name}/zip")
    async def project_zip(
        name: str,
        photos_only: bool = False,
        scans: list[int] | None = Query(None),
    ):
        entries = list(rig.projects.zip_entries(name, photos_only, scans))
        zs = ZipStream(compress_type=ZIP_STORED, sized=True)
        for path, arcname in entries:
            zs.add_path(str(path), arcname)
        suffix = "_photos" if photos_only else ""
        return StreamingResponse(
            zs,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{name}{suffix}.zip"',
                "Content-Length": str(len(zs)),
            },
        )

    # ---- live events -------------------------------------------------------

    @api.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        q = rig.bus.subscribe()

        async def reader() -> None:
            # The client sends nothing; this only notices it going away.
            try:
                while True:
                    await sock.receive_text()
            except WebSocketDisconnect:
                pass

        closed = asyncio.create_task(reader())
        try:
            await sock.send_json({"type": "status", "status": rig.status()})
            while not closed.done():
                get = asyncio.create_task(q.get())
                done, _ = await asyncio.wait({get, closed}, return_when=asyncio.FIRST_COMPLETED)
                if get in done:
                    await sock.send_json(get.result())
                else:
                    get.cancel()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            closed.cancel()
            rig.bus.unsubscribe(q)

    app.include_router(api)

    if web_dist and web_dist.exists():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            f = web_dist / full_path
            if full_path and f.is_file() and web_dist in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(web_dist / "index.html")

    return app
