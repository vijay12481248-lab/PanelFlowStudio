"""ChronoFlow media library: every video PanelFlow has made (or the owner points at), and importing it into the studio.

The studio used to see only ``output/chronoflow``; stories, series, reels and uploads live in sibling folders, so recent work never showed up.
Importing hard-links the file into the studio output folder as ``<job>_chunk_<n>`` (copy across drives), so the player, thumbnails and
``media_tools.resolve_media`` work unchanged and the clip survives the original being moved.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.api.routers import chronoflow as cf
from engine.chronoflow import media_tools
from engine.chronoflow.folder_dialog import pick_native_files
from engine.chronoflow.pipeline import STUDIO_OUTPUT_DIR

router = APIRouter(prefix="/api/chronoflow/library", tags=["chronoflow-library"])

VIDEO_EXTS = {".mp4", ".webm", ".mov"}      # what Chromium's <video> plays; mkv/avi would import but not preview
LIBRARY_ROOT = STUDIO_OUTPUT_DIR.parent     # .../output: one sub-folder per producer (Original_Stories, reels, series_1000, ...)
_SCAN_TTL = 10.0
_scan_cache: dict[str, Any] = {"t": 0.0, "items": [], "sources": []}


def _label(folder: str) -> str:
    return "ChronoFlow renders" if folder == "chronoflow" else folder.replace("_", " ")


def _roots() -> list[dict[str, str]]:
    roots: list[dict[str, str]] = []
    if LIBRARY_ROOT.is_dir():
        for d in sorted(LIBRARY_ROOT.iterdir()):
            if d.is_dir() and not d.name.startswith(("_", ".")):
                roots.append({"id": d.name, "label": _label(d.name), "path": str(d), "kind": "output"})
    for loc in cf.load_storage_locations():
        p = Path(loc.get("path", ""))
        if p.is_dir():
            roots.append({"id": loc.get("id", p.name), "label": loc.get("name", p.name), "path": str(p), "kind": "location"})
    return roots


def _scan(force: bool = False) -> dict[str, Any]:
    if not force and time.time() - _scan_cache["t"] < _SCAN_TTL:
        return _scan_cache
    items: list[dict[str, Any]] = []
    sources = []
    for root in _roots():
        n = 0
        for dirpath, _dirs, files in os.walk(root["path"]):
            for fn in files:
                if Path(fn).suffix.lower() not in VIDEO_EXTS or fn.startswith("concat_"):
                    continue
                full = Path(dirpath) / fn
                try:
                    st = full.stat()
                except OSError:
                    continue
                if st.st_size == 0:
                    continue
                n += 1
                items.append({"path": str(full), "name": fn, "source": root["id"], "folder": str(Path(dirpath).relative_to(root["path"])).replace("\\", "/").lstrip("."),
                              "size_mb": round(st.st_size / 1048576, 1), "mtime": st.st_mtime})
        sources.append({**root, "count": n})
    items.sort(key=lambda i: i["mtime"], reverse=True)
    _scan_cache.update(t=time.time(), items=items, sources=sources)
    return _scan_cache


@router.get("/sources")
def library_sources() -> dict[str, Any]:
    s = _scan(force=True)
    return {"sources": [x for x in s["sources"] if x["count"]], "total": len(s["items"])}


@router.get("/videos")
def library_videos(source: str = "", q: str = "", limit: int = 60, offset: int = 0) -> dict[str, Any]:
    items = _scan()["items"]
    if source:
        items = [i for i in items if i["source"] == source]
    if q.strip():
        needle = q.strip().lower()
        items = [i for i in items if needle in i["name"].lower() or needle in i["folder"].lower()]
    limit = max(1, min(limit, 200))
    return {"items": items[offset:offset + limit], "total": len(items)}


@router.post("/pick_files")
async def library_pick_files() -> dict[str, Any]:
    """Native multi-file dialog (this is a local app: real paths, nothing is uploaded)."""
    paths = await pick_native_files()
    return {"success": bool(paths), "cancelled": not paths, "paths": paths}


class ImportRequest(BaseModel):
    paths: list[str]
    job_id: str | None = None     # append to an earlier import instead of making a new project
    title: str | None = None


def _place(src: Path, dest: Path) -> None:
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


@router.post("/import")
def library_import(req: ImportRequest) -> dict[str, Any]:
    if not req.paths:
        raise HTTPException(status_code=400, detail="Choose at least one video")
    job = cf.active_jobs.get(req.job_id) if req.job_id else None
    if req.job_id and (not job or job.get("workflow_mode") != "imported"):
        raise HTTPException(status_code=400, detail="Videos can only be added to a project that was itself imported")
    first = Path(req.paths[0])
    job_id = req.job_id or f"imp_{uuid.uuid4().hex[:8]}"
    chunks = list(job["chunks"]) if job else []
    scenes = list(job["scenes"]) if job else []
    prompts = list(job["chunk_prompts"]) if job else []
    added, skipped = [], []
    for raw in req.paths:
        src = Path(raw)
        if not src.is_file() or src.suffix.lower() not in VIDEO_EXTS:
            skipped.append({"path": raw, "reason": "not a .mp4 / .webm / .mov file" if src.is_file() else "file not found"})
            continue
        try:
            info = media_tools.probe(src)
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            skipped.append({"path": raw, "reason": f"could not read the video ({type(e).__name__})"})
            continue
        n = len(chunks) + 1
        dest_name = f"{job_id}_chunk_{n}{src.suffix.lower()}"
        _place(src, STUDIO_OUTPUT_DIR / dest_name)
        url = f"/chronoflow/outputs/{dest_name}"
        chunks.append(url)
        prompts.append(src.stem)
        scenes.append({"shot_index": n, "title": src.stem, "prompt": "", "duration": round(info["duration"], 2), "rendered_video": url, "source_path": str(src)})
        added.append({"name": src.name, "duration": round(info["duration"], 2)})
    if not added:
        raise HTTPException(status_code=400, detail={"message": "Nothing could be imported", "skipped": skipped})
    fields = {
        "chunks": chunks, "chunk_prompts": prompts, "scenes": scenes, "total_chunks": len(chunks), "current_chunk": len(chunks),
        "total_duration": sum(float(s["duration"]) for s in scenes), "master_video": chunks[0],
        "status": "completed", "status_msg": f"{len(chunks)} imported video(s)",
    }
    if job:
        job.update(fields)
    else:
        job = {"id": job_id, "prompt": (req.title or first.stem)[:120], "initial_image": None, "workflow_mode": "imported", "width": 1344, "height": 768,
               "step_progress": 100, "cancelled": False, "error": None, "created_at": time.time(), "reviews": {}, **fields}
        cf.active_jobs[job_id] = job
    cf.supervisor._save_jobs_to_disk()
    cf.supervisor.state_version += 1
    return {"success": True, "job_id": job_id, "added": added, "skipped": skipped, "job": job}
