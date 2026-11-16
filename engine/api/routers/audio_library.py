"""REST for the sound library behind the Audio Studio: make, import, record, edit (versions, undo/redo), trash, files and peaks."""
from __future__ import annotations

import asyncio
import secrets
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from engine.audio.library import make
from engine.audio.library.ops import ops_catalog
from engine.audio.library.store import SoundStore
from engine.audio.studio.plan import Provenance
from engine.audio.studio.sources import music as music_source

router = APIRouter(prefix="/api/audio/library", tags=["audio-library"])
MAX_UPLOAD = 300 * 1024 * 1024
Kind = Literal["voice", "music", "effect"]
_store: SoundStore | None = None


def get_store() -> SoundStore:
    global _store
    if _store is None:
        _store = SoundStore()
    return _store


def get_makers() -> dict[str, Any]:
    """The sources that make sounds; tests replace them with fakes."""
    return {"narration": None, "music": None, "effects": None}


@contextmanager
def _errors():
    try:
        yield
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (FileNotFoundError, KeyError) as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'\""))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


class VoiceBody(BaseModel):
    text: str
    voice: str = ""
    provider: str = "kokoro"
    speed: float = 1.0
    language: str = "English"
    name: str = ""


class MusicBody(BaseModel):
    description: str
    seconds: float = 30.0
    bpm: int | None = None
    key_scale: str | None = None
    name: str = ""


class EffectBody(BaseModel):
    description: str = ""
    kind: str = "whoosh"
    limit: int = 3
    allow_cc_by: bool = False


class KeepBody(BaseModel):
    candidate_id: str
    name: str = ""


class ImportBody(BaseModel):
    path: str
    name: str = ""
    kind: Kind = "effect"


class EditBody(BaseModel):
    op: str
    params: dict[str, Any] = {}
    a: float | None = None
    b: float | None = None


class UpdateBody(BaseModel):
    name: str | None = None
    kind: Kind | None = None


class SplitBody(BaseModel):
    at: float


class JoinBody(BaseModel):
    other: str


def _out(s) -> dict[str, Any]:
    d = s.model_dump()
    d["duration_s"] = s.duration_s
    return d


@router.get("/ops")
def ops() -> list[dict[str, Any]]:
    return ops_catalog()


@router.get("/sounds")
def list_sounds(kind: Kind | None = None, q: str = "", trash: bool = False, store: SoundStore = Depends(get_store)) -> list[dict[str, Any]]:
    return [_out(s) for s in store.list(kind, q, trash)]


@router.get("/sounds/{sid}")
def get_sound(sid: str, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        return _out(store.load(sid))


@router.post("/sounds/voice")
async def new_voice(body: VoiceBody, store: SoundStore = Depends(get_store), makers=Depends(get_makers)) -> dict[str, Any]:
    music_source.bind_loop(asyncio.get_running_loop())   # Qwen3-TTS takes the shared GPU slot

    def work():
        with _errors():
            return _out(make.make_voice(store, body.text, body.voice, body.provider, body.speed, body.language, body.name, narration=makers["narration"]))
    return await run_in_threadpool(work)


@router.post("/sounds/music")
async def new_music(body: MusicBody, store: SoundStore = Depends(get_store), makers=Depends(get_makers)) -> dict[str, Any]:
    music_source.bind_loop(asyncio.get_running_loop())

    def work():
        with _errors():
            return _out(make.make_music(store, body.description, body.seconds, body.bpm, body.key_scale, body.name, music=makers["music"]))
    return await run_in_threadpool(work)


@router.post("/effects/find")
async def find_effects(body: EffectBody, store: SoundStore = Depends(get_store), makers=Depends(get_makers)) -> dict[str, Any]:
    def work():
        with _errors():
            return {"candidates": make.find_effects(store, body.description, body.kind, body.limit, makers["effects"], body.allow_cc_by)}
    return await run_in_threadpool(work)


@router.get("/effects/candidates/{cid}/file")
def candidate_file(cid: str, store: SoundStore = Depends(get_store)):
    with _errors():
        return FileResponse(make.candidate_file(store, cid))


@router.post("/effects/keep")
def keep_effect(body: KeepBody, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        return _out(make.keep_candidate(store, body.candidate_id, body.name))


@router.post("/sounds/import")
async def import_path(body: ImportBody, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    """A file on this PC (audio, or the sound track of a video). The owner vouches for files they bring."""
    def work():
        with _errors():
            p = Path(body.path)
            return _out(store.create_from_file(p, body.name or p.stem, body.kind, Provenance(source="import", licence="owner", url=str(p))))
    return await run_in_threadpool(work)


@router.post("/sounds/upload")
async def upload(file: UploadFile = File(...), name: str = Form(""), kind: Kind = Form("effect"), source: Literal["import", "recording"] = Form("import"),
                 store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    """A dropped file or a microphone recording from the page."""
    suffix = Path(file.filename or "x.wav").suffix.lower()[:8] or ".wav"
    with tempfile.TemporaryDirectory(prefix="pf-lib-up-") as tmp:
        dst, size = Path(tmp) / f"upload{suffix}", 0
        with open(dst, "wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(status_code=413, detail="the file is larger than 300 MB")
                f.write(chunk)

        def work():
            with _errors():
                default = "Recording " + secrets.token_hex(2) if source == "recording" else Path(file.filename or "Imported").stem
                return _out(store.create_from_file(dst, name or default, kind, Provenance(source=source, licence="owner")))
        return await run_in_threadpool(work)


@router.post("/sounds/{sid}/edit")
async def edit(sid: str, body: EditBody, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    def work():
        with _errors():
            return _out(store.edit(sid, body.op, body.params, body.a, body.b))
    return await run_in_threadpool(work)


@router.post("/sounds/{sid}/preview")
async def preview(sid: str, body: EditBody, store: SoundStore = Depends(get_store)):
    """Hear an operation before keeping it: the result is rendered to a temporary file, the sound is not changed."""
    def work():
        with _errors():
            import soundfile as sf
            from engine.audio.library import ops as opmod
            y = opmod.apply(body.op, store.read(sid), opmod.SR, body.params, body.a, body.b)
            d = store.dir(sid) / "preview"
            d.mkdir(exist_ok=True)
            for old in d.glob("*.wav"):
                old.unlink(missing_ok=True)
            out = d / f"p_{secrets.token_hex(4)}.wav"
            sf.write(str(out), y, opmod.SR, subtype="FLOAT")
            return out
    return FileResponse(await run_in_threadpool(work), media_type="audio/wav")


@router.post("/sounds/{sid}/undo")
def undo(sid: str, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        return _out(store.undo(sid))


@router.post("/sounds/{sid}/redo")
def redo(sid: str, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        return _out(store.redo(sid))


@router.post("/sounds/{sid}/versions/{n}/current")
def set_current(sid: str, n: int, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        return _out(store.set_current(sid, n))


@router.patch("/sounds/{sid}")
def update(sid: str, body: UpdateBody, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        return _out(store.update(sid, body.name, body.kind))


@router.post("/sounds/{sid}/split")
def split(sid: str, body: SplitBody, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        head, tail = store.split(sid, body.at)
        return {"sound": _out(head), "new": _out(tail)}


@router.post("/sounds/{sid}/duplicate")
def duplicate(sid: str, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        return _out(store.duplicate(sid))


@router.post("/sounds/{sid}/join")
def join(sid: str, body: JoinBody, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        return _out(store.join(sid, body.other))


@router.delete("/sounds/{sid}")
def trash(sid: str, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    """Moves the sound to the trash (restorable)."""
    with _errors():
        return _out(store.trash(sid, True))


@router.post("/sounds/{sid}/restore")
def restore(sid: str, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        return _out(store.trash(sid, False))


@router.post("/trash/empty")
def empty_trash(store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    """Permanently removes every trashed sound (the page asks first)."""
    return {"removed": store.empty_trash()}


@router.get("/sounds/{sid}/file")
def sound_file(sid: str, v: int | None = None, store: SoundStore = Depends(get_store)):
    with _errors():
        return FileResponse(store.file(sid, v), media_type="audio/wav")


@router.get("/sounds/{sid}/peaks")
def peaks(sid: str, v: int | None = None, bins: int = 1200, store: SoundStore = Depends(get_store)) -> dict[str, Any]:
    with _errors():
        return store.peaks(sid, v, bins)
