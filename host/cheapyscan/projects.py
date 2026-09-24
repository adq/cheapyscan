# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""Projects and scans on disk.

The layout follows OpenScan3, so tools written for its projects find the
photos in the same places:

    <root>/<project>/project.json
    <root>/<project>/thumbnail.jpg
    <root>/<project>/scanNN/scan.json
    <root>/<project>/scanNN/path.json
    <root>/<project>/scanNN/scanNN_PPP.jpg        PPP is the Fibonacci index
    <root>/<project>/scanNN/metadata/scanNN_PPP.json

JSON files are written to a temporary name and renamed, so a crash mid-write
never leaves a half-written file.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Iterator

from PIL import Image

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")
SCAN_RE = re.compile(r"^scan(\d{2,})$")
PHOTO_EXTS = {".jpg", ".jpeg", ".nef", ".cr2", ".cr3", ".arw", ".dng", ".tif", ".tiff", ".png"}
THUMB_SIZES = (256, 512)


class ProjectError(Exception):
    pass


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def scan_dir_name(index: int) -> str:
    return f"scan{index:02d}"


def photo_stem(scan_index: int, point_index: int) -> str:
    return f"{scan_dir_name(scan_index)}_{point_index:03d}"


class Projects:
    def __init__(self, root: Path):
        self.root = root

    def _project_dir(self, name: str) -> Path:
        if not NAME_RE.match(name) or name in (".", ".."):
            raise ProjectError(
                "Project names use letters, digits, spaces, dots, dashes and "
                "underscores, start with a letter or digit, and are at most 64 "
                "characters."
            )
        return self.root / name

    def project_dir(self, name: str) -> Path:
        d = self._project_dir(name)
        if not (d / "project.json").exists():
            raise ProjectError(f"No project called {name!r}.")
        return d

    def list(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        out = []
        for d in sorted(self.root.iterdir()):
            if (d / "project.json").exists():
                out.append(self.summary(d.name))
        return out

    def summary(self, name: str) -> dict[str, Any]:
        d = self.project_dir(name)
        meta = read_json(d / "project.json")
        scans = self.scans(name)
        return {
            **meta,
            "name": name,
            "scan_count": len(scans),
            "photo_count": sum(s.get("photo_count", 0) for s in scans),
            "has_thumbnail": (d / "thumbnail.jpg").exists(),
        }

    def create(self, name: str, description: str = "") -> dict[str, Any]:
        d = self._project_dir(name)
        if d.exists():
            raise ProjectError(f"A project called {name!r} already exists.")
        d.mkdir(parents=True)
        write_json(d / "project.json", {"name": name, "description": description, "created": time.time()})
        return self.summary(name)

    def delete(self, name: str) -> None:
        shutil.rmtree(self.project_dir(name))

    def scan_dirs(self, name: str) -> list[tuple[int, Path]]:
        d = self.project_dir(name)
        out = []
        for sub in d.iterdir():
            m = SCAN_RE.match(sub.name)
            if m and (sub / "scan.json").exists():
                out.append((int(m.group(1)), sub))
        return sorted(out)

    def scans(self, name: str) -> list[dict[str, Any]]:
        return [self.read_scan(name, i) for i, _ in self.scan_dirs(name)]

    def scan_dir(self, name: str, index: int) -> Path:
        d = self.project_dir(name) / scan_dir_name(index)
        if not (d / "scan.json").exists():
            raise ProjectError(f"Project {name!r} has no scan {index}.")
        return d

    def read_scan(self, name: str, index: int) -> dict[str, Any]:
        d = self.scan_dir(name, index)
        data = read_json(d / "scan.json")
        data["photo_count"] = len(self.photos(name, index))
        return data

    def new_scan(self, name: str) -> tuple[int, Path]:
        existing = self.scan_dirs(name)
        index = existing[-1][0] + 1 if existing else 1
        d = self.project_dir(name) / scan_dir_name(index)
        d.mkdir()
        return index, d

    def delete_scan(self, name: str, index: int) -> None:
        shutil.rmtree(self.scan_dir(name, index))

    def photos(self, name: str, index: int) -> list[str]:
        d = self.project_dir(name) / scan_dir_name(index)
        return sorted(p.name for p in d.iterdir() if p.suffix.lower() in PHOTO_EXTS)

    def photo_path(self, name: str, index: int, filename: str) -> Path:
        d = self.scan_dir(name, index)
        if "/" in filename or "\\" in filename or filename.startswith("."):
            raise ProjectError("bad file name")
        p = d / filename
        if not p.is_file():
            raise ProjectError(f"No photo {filename!r}.")
        return p

    def thumbnail(self, name: str, index: int, filename: str, size: int) -> Path:
        """A JPEG no bigger than size x size, cached next to the scan."""
        if size not in THUMB_SIZES:
            raise ProjectError(f"thumbnail size must be one of {THUMB_SIZES}")
        src = self.photo_path(name, index, filename)
        if src.suffix.lower() not in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
            raise ProjectError("No preview for this file type.")
        out = src.parent / ".thumbs" / str(size) / (src.stem + ".jpg")
        if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as img:
            img.thumbnail((size, size))
            img.convert("RGB").save(out, quality=85)
        return out

    def set_project_thumbnail(self, name: str, photo: Path) -> None:
        d = self.project_dir(name)
        target = d / "thumbnail.jpg"
        if target.exists() or photo.suffix.lower() not in (".jpg", ".jpeg"):
            return
        with Image.open(photo) as img:
            img.thumbnail((512, 512))
            img.convert("RGB").save(target, quality=85)

    def zip_entries(self, name: str, photos_only: bool, scans: list[int] | None = None) -> Iterator[tuple[Path, str]]:
        """(file, name in archive) pairs for a zip download."""
        d = self.project_dir(name)
        for index, sd in self.scan_dirs(name):
            if scans and index not in scans:
                continue
            for f in sorted(sd.rglob("*")):
                if not f.is_file() or ".thumbs" in f.parts or f.name.endswith(".tmp"):
                    continue
                if photos_only:
                    if f.parent == sd and f.suffix.lower() in PHOTO_EXTS:
                        yield f, f.name
                else:
                    yield f, str(f.relative_to(d.parent))
        if not photos_only:
            for f in ("project.json", "thumbnail.jpg"):
                if (d / f).exists():
                    yield d / f, f"{name}/{f}"
