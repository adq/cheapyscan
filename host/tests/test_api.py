# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey

import io
import zipfile

import httpx
import pytest

from cheapyscan.api import create_app


@pytest.fixture
async def client(rig):
    app = create_app(rig, web_dist=None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_status_and_jog(client):
    r = await client.get("/api/status")
    assert r.json()["connected"] is True
    r = await client.post("/api/motors/reference")
    assert r.json()["referenced"] is True
    r = await client.post("/api/motors/jog", json={"axis": "rotor", "degrees": -10})
    assert r.json()["angles"]["theta"] == pytest.approx(80, abs=0.05)


async def test_path_preview(client):
    r = await client.post("/api/path/preview", json={"points": 30})
    body = r.json()
    assert len(body["points"]) == 30
    assert body["move_time_s"] > 0


async def test_scan_and_zip(client, rig):
    await client.post("/api/motors/reference")
    assert (await client.post("/api/projects", json={"name": "cup"})).status_code == 200
    r = await client.post("/api/projects/cup/scans", json={"points": 4, "settle_ms": 0})
    assert r.status_code == 200, r.text
    await rig.scan.wait()

    r = await client.get("/api/projects/cup")
    assert r.json()["scans"][0]["status"] == "completed"
    r = await client.get("/api/projects/cup/scans/1")
    assert len(r.json()["photos"]) == 4

    r = await client.get("/api/projects/cup/scans/1/photos/scan01_000.jpg?size=256")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"

    r = await client.get("/api/projects/cup/zip")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "cup/scan01/scan01_000.jpg" in names
    assert "cup/scan01/path.json" in names
    assert "cup/project.json" in names

    r = await client.get("/api/projects/cup/zip?photos_only=true")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert sorted(names) == [f"scan01_{i:03d}.jpg" for i in range(4)]


async def test_errors_are_readable(client):
    r = await client.post("/api/projects/nope/scans", json={"points": 4})
    assert r.status_code == 409
    assert "reference" in r.json()["detail"]
    r = await client.post("/api/projects", json={"name": "../evil"})
    assert r.status_code == 400
    r = await client.get("/api/projects/missing")
    assert r.status_code == 404


async def test_config_rejects_same_axis(client):
    cfg = (await client.get("/api/config")).json()
    cfg["rotor"]["firmware_axis"] = cfg["turntable"]["firmware_axis"]
    r = await client.put("/api/config", json=cfg)
    assert r.status_code == 409
