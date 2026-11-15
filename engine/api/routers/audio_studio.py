"""Audio Studio REST API: sound plans (cue sheets), sourcing, checks, mix and export. The MCP tools call exactly these endpoints."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from engine.audio.studio import mix as mixer
from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.plan import Cue, PlanStore, Track, check_id, snap
from engine.audio.studio.qa import check_plan
from engine.audio.studio.sources.music import MusicProvider
from engine.audio.studio.sources.openverse import OpenverseProvider
from engine.audio.studio.sources.synth import SynthProvider
from engine.audio.studio.spot import detect_cuts, draft_cues
from engine.audio.studio.stems import export as export_plan

router = APIRouter(prefix="/api/audio/studio", tags=["audio-studio"])
_engine: AudioEngine | None = None


def get_engine() -> AudioEngine:
    global _engine
    if _engine is None:
        _engine = AudioEngine(PlanStore(), [OpenverseProvider(), SynthProvider(), MusicProvider()])
    return _engine


@contextmanager
def _errors():
    try:
        yield
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (FileNotFoundError, KeyError) as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'\""))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


class CreateBody(BaseModel):
    video_path: str
    mode: Literal["auto", "ask"] = "auto"
    allow_cc_by: bool = False
    dialogue_path: str | None = None


class PutBody(BaseModel):
    cues: list[dict[str, Any]] | None = None
    remove_cues: list[str] | None = None
    tracks: list[dict[str, Any]] | None = None
    mode: Literal["auto", "ask"] | None = None
    allow_cc_by: bool | None = None
    dialogue_path: str | None = None
    note: str = ""


class SourceBody(BaseModel):
    mode: Literal["auto", "ask"] | None = None


class PickBody(BaseModel):
    candidate_id: str


class RenderBody(BaseModel):
    target_lufs: float = -14.0
    mux: bool = False
    allow_incomplete: bool = False


@router.get("/providers")
def providers(engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    return {n: {"ok": a.ok, "reason": a.reason} for n, a in engine.providers_report().items()}


@router.post("/plans")
def create_plan(body: CreateBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        from engine.chronoflow.media_tools import probe
        video = Path(body.video_path)
        if not video.is_file():
            raise ValueError(f"video not found: {body.video_path}")
        try:
            info = probe(video)
        except Exception as e:
            raise ValueError(f"cannot read the video: {e}")
        dialogue = body.dialogue_path or (str(video) if info["has_audio"] else None)
        if dialogue and not Path(dialogue).is_file():
            raise ValueError(f"dialogue file not found: {dialogue}")
        plan = engine.store.create(str(video), fps=info["fps"], duration=info["duration"], mode=body.mode,
                                   allow_cc_by=body.allow_cc_by, dialogue_path=dialogue)
        return engine.store.save(plan, "created").model_dump()


@router.get("/plans/{plan_id}")
def get_plan(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        return engine.store.load(plan_id).model_dump()


@router.put("/plans/{plan_id}")
def put_plan(plan_id: str, body: PutBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        plan = engine.store.load(plan_id)
        if body.cues is not None or body.remove_cues:
            by_id = {c.id: c for c in plan.cues}  # upsert: cues the body does not mention stay as they are
            for cid in body.remove_cues or []:
                if cid not in by_id:
                    raise ValueError(f"cannot remove: no cue {cid!r}")
                del by_id[cid]
            seen = set()
            for raw in body.cues or []:
                cid = check_id(raw.get("id"))
                if cid in seen:
                    raise ValueError(f"duplicate cue id {cid!r}")
                seen.add(cid)
                cue = Cue.model_validate({**(by_id[cid].model_dump() if cid in by_id else {}), **raw})
                if cue.hit_t is not None:
                    if cue.hit_t < 0:
                        raise ValueError(f"cue {cid!r}: hit_t must be 0 or more")
                    cue.hit_t = snap(cue.hit_t, plan.fps)
                if cue.t_out is not None and cue.t_out < cue.t_in:
                    raise ValueError(f"cue {cid!r}: t_out is before t_in")
                by_id[cid] = cue
            plan.cues = list(by_id.values())
        if body.tracks is not None:
            have = {t.id: t for t in plan.tracks}
            plan.tracks = [Track.model_validate({**(have[r["id"]].model_dump() if r.get("id") in have else {}), **r}) for r in body.tracks]
        if body.dialogue_path is not None and not Path(body.dialogue_path).is_file():
            raise ValueError(f"dialogue file not found: {body.dialogue_path}")
        for field in ("mode", "allow_cc_by", "dialogue_path"):
            if getattr(body, field) is not None:
                setattr(plan, field, getattr(body, field))
        return engine.store.save(plan, body.note or "edited").model_dump()


@router.post("/plans/{plan_id}/spot")
def spot(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        plan = engine.store.load(plan_id)
        keep = [c for c in plan.cues if c.status != "draft"]
        taken = {c.id for c in keep}
        plan.cues = keep + [c for c in draft_cues(plan, detect_cuts(Path(plan.video_path))) if c.id not in taken]
        return engine.store.save(plan, "spotted").model_dump()


@router.post("/plans/{plan_id}/cues/{cue_id}/source")
def source_cue(plan_id: str, cue_id: str, body: SourceBody | None = None, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        return engine.source_cue(plan_id, check_id(cue_id), (body.mode if body else None)).model_dump()


@router.post("/plans/{plan_id}/cues/{cue_id}/pick")
def pick(plan_id: str, cue_id: str, body: PickBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        return engine.pick(plan_id, check_id(cue_id), body.candidate_id).model_dump()


@router.post("/plans/{plan_id}/qa")
def qa(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        plan = engine.store.load(plan_id)
        findings = check_plan(plan, mixer.render_cue)
        saved = engine.store.save(plan, "qa")
        errors = sum(f.severity == "error" for f in findings)
        return {"plan_version": saved.version, "errors": errors, "warnings": len(findings) - errors,
                "findings": [f.model_dump() for f in findings]}


@router.post("/plans/{plan_id}/mix")
def mix(plan_id: str, body: RenderBody | None = None, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    body = body or RenderBody()
    with _errors():
        plan = engine.store.load(plan_id)
        out = engine.store.plan_dir(plan_id) / "renders"
        loud = mixer.render_master(plan, out / "master.wav", body.target_lufs,
                                   Path(plan.video_path) if body.mux else None, out / "master.mp4" if body.mux else None)
        return {"file": "renders/master.wav", "video": "renders/master.mp4" if body.mux else None, "loudness": loud}


@router.post("/plans/{plan_id}/export")
def export(plan_id: str, body: RenderBody | None = None, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    body = body or RenderBody()
    with _errors():
        plan = engine.store.load(plan_id)
        out = engine.store.plan_dir(plan_id) / "exports" / f"v{plan.version}"
        res = export_plan(plan, out, body.target_lufs, Path(plan.video_path) if body.mux else None, body.allow_incomplete)
        engine.store.save(plan, "exported")  # keeps the placement errors the export measured
        return {**res, "dir": f"exports/v{plan.version}"}


@router.get("/plans/{plan_id}/files/{name:path}")
def get_file(plan_id: str, name: str, engine: AudioEngine = Depends(get_engine)):
    with _errors():
        base = engine.store.plan_dir(plan_id).resolve()
        target = (base / name).resolve()
        if not target.is_relative_to(base):
            raise ValueError("file path must stay inside the plan folder")
        if not target.is_file():
            raise FileNotFoundError(f"no file {name!r} in plan {plan_id}")
        return FileResponse(target)
