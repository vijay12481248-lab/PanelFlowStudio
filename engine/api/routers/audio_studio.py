"""Audio Studio REST API: sound plans (cue sheets), sourcing, checks, mix and export. The MCP tools call exactly these endpoints."""
from __future__ import annotations

import asyncio
import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from engine.audio.studio import mix as mixer
from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.fix import fix_plan
from engine.audio.studio.script import add_script
from engine.audio.studio.peaks import file_peaks
from engine.audio.studio.plan import Cue, PlanStore, Track, check_id, snap
from engine.audio.studio.preview import audio_signature, build_preview
from engine.audio.studio.qa import check_plan
from engine.audio.studio.sources import music as music_source
from engine.audio.studio.sources.music import MusicProvider
from engine.audio.studio.sources.narration import PROVIDERS as SPEECH_PROVIDERS
from engine.audio.studio.sources.narration import NarrationProvider, list_voices
from engine.audio.studio.sources.openverse import OpenverseProvider
from engine.audio.studio.sources.synth import SynthProvider
from engine.audio.studio.spot import detect_cuts, draft_cues
from engine.audio.studio.stems import export as export_plan

router = APIRouter(prefix="/api/audio/studio", tags=["audio-studio"])
# These come from source_cue / pick / qa, never from a caller: otherwise a caller could attach any file with any licence to a cue.
_SERVER_OWNED = {"takes", "candidates", "chosen_take", "status", "reason", "placement_error_ms"}
_engine: AudioEngine | None = None


def get_engine() -> AudioEngine:
    global _engine
    if _engine is None:
        _engine = AudioEngine(PlanStore(), [OpenverseProvider(), SynthProvider(), MusicProvider(), NarrationProvider()])
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
    keep_original_audio: bool | None = None
    cues: list[dict[str, Any]] | None = None
    remove_cues: list[str] | None = None
    tracks: list[dict[str, Any]] | None = None
    mode: Literal["auto", "ask"] | None = None
    allow_cc_by: bool | None = None
    dialogue_path: str | None = None
    note: str = ""


class SampleBody(BaseModel):
    text: str
    voice: str = ""
    provider: str = "kokoro"
    speed: float = 1.0
    language: str = "English"


class AddSoundBody(BaseModel):
    intent: str
    kind: str = "whoosh"
    track: Literal["music", "sfx", "ambience", "foley"] = "sfx"
    hit_t: float | None = None
    t_in: float = 0.0
    t_out: float | None = None
    mode: Literal["auto", "ask"] | None = "ask"


class ScriptBody(BaseModel):
    text: str
    mode: Literal["sequential", "per_cut"] = "sequential"
    start: float = 0.0
    gap: float = 0.4
    voice: str = ""
    provider: str = ""
    speed: float = 1.0


class TimelineBody(BaseModel):
    clips: list[dict[str, Any]]
    overlays: list[dict[str, Any]] = []
    luts: dict[str, Any] = {}
    cuts: list[float] = []
    job_id: str | None = None


class SourceBody(BaseModel):
    mode: Literal["auto", "ask"] | None = None


class PickBody(BaseModel):
    candidate_id: str


class RenderBody(BaseModel):
    target_lufs: float = -14.0
    mux: bool = False
    allow_incomplete: bool = False


def _save_measured(engine: AudioEngine, plan_id: str, measured: Any, note: str):
    """Copy the placement errors a long run measured onto the plan as it is now, so edits made meanwhile are not overwritten."""
    errors = {c.id: c.placement_error_ms for c in measured.cues if c.placement_error_ms is not None}
    with engine.store.lock(plan_id):
        fresh = engine.store.load(plan_id)
        for c in fresh.cues:
            if c.id in errors:
                c.placement_error_ms = errors[c.id]
        return engine.store.save(fresh, note)


def get_timeline_renderer():
    """Renders the Video Studio timeline (the same EDL renderer the export uses) to a picture file; tests replace it."""
    def render(clips, overlays, luts, out_dir=None):
        import uuid
        from engine.api.routers import chronoflow as cf
        target = (Path(out_dir) if out_dir else cf.STUDIO_OUTPUT_DIR) / f"audio_picture_{uuid.uuid4().hex[:8]}.mp4"
        done = cf.pipeline.render_timeline_edl(clips, target, overlays, luts)
        if not (done and target.exists()):
            raise RuntimeError("the timeline could not be rendered to a picture")
        return target
    return render


def _new_plan(engine: AudioEngine, video_path: str, **kw) -> Any:
    from engine.chronoflow.media_tools import probe
    video = Path(video_path)
    if not video.is_file():
        raise ValueError(f"video not found: {video_path}")
    try:
        info = probe(video)
    except Exception as e:
        raise ValueError(f"cannot read the video: {e}")
    dialogue = kw.pop("dialogue_path", None) or (str(video) if info["has_audio"] else None)
    if dialogue and not Path(dialogue).is_file():
        raise ValueError(f"dialogue file not found: {dialogue}")
    return engine.store.create(str(video), fps=info["fps"], duration=info["duration"], dialogue_path=dialogue, **kw)


def _next_id(plan, prefix: str) -> str:
    n, taken = 1, {c.id for c in plan.cues}
    while f"{prefix}_{n:02d}" in taken:
        n += 1
    return f"{prefix}_{n:02d}"


@router.get("/providers")
def providers(engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    return {n: {"ok": a.ok, "reason": a.reason} for n, a in engine.providers_report().items()}


@router.post("/plans")
def create_plan(body: CreateBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        plan = _new_plan(engine, body.video_path, mode=body.mode, allow_cc_by=body.allow_cc_by, dialogue_path=body.dialogue_path, source={"kind": "file"})
        return engine.store.save(plan, "created").model_dump()


@router.post("/plans/from_timeline")
def plan_from_timeline(body: TimelineBody, engine: AudioEngine = Depends(get_engine), render=Depends(get_timeline_renderer)) -> dict[str, Any]:
    """Video Studio -> Audio Studio: render the timeline to a picture and keep its clip boundaries as the picture cuts."""
    with _errors():
        if not body.clips:
            raise ValueError("the timeline has no clips: add clips in the Video Studio first")
        try:
            picture = render(body.clips, body.overlays, body.luts, None)
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"timeline render failed: {e}")
        plan = _new_plan(engine, str(picture), source={"kind": "timeline", "job_id": body.job_id})
        cuts = sorted({snap(c, plan.fps) for c in body.cuts if 0 < c < plan.duration})
        plan.cuts = [round(c, 4) for c in cuts]
        return engine.store.save(plan, "created from the timeline").model_dump()


@router.get("/plans")
def list_plans(engine: AudioEngine = Depends(get_engine)) -> list[dict[str, Any]]:
    return [{"id": p.id, "video_name": Path(p.video_path).name, "video_path": p.video_path, "version": p.version, "cues": len(p.cues),
             "duration": p.duration, "fps": p.fps} for p in engine.store.list()]


@router.get("/plans/{plan_id}")
def get_plan(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        return engine.store.load(plan_id).model_dump()


@router.put("/plans/{plan_id}")
def put_plan(plan_id: str, body: PutBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors(), engine.store.lock(plan_id):
        for raw in body.cues or []:
            owned = sorted(_SERVER_OWNED & set(raw))
            if owned:
                raise ValueError(f"cue {raw.get('id')!r}: {', '.join(owned)} are set by source_cue / pick / qa, not by put_plan")
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
                old = by_id.get(cid)
                if old is not None and cue.kind == "narration" and cue.chosen_take and any(getattr(old, f) != getattr(cue, f) for f in ("text", "voice", "provider", "speed")):
                    cue.chosen_take, cue.status, cue.reason, cue.placement_error_ms = None, "draft", None, None   # new words or voice need new speech
                if cue.hit_t is not None:
                    if cue.hit_t < 0:
                        raise ValueError(f"cue {cid!r}: hit_t must be 0 or more")
                    cue.hit_t = snap(cue.hit_t, plan.fps)
                if cue.t_out is not None and cue.t_out < cue.t_in:
                    raise ValueError(f"cue {cid!r}: t_out is before t_in")
                by_id[cid] = cue
            plan.cues = list(by_id.values())
        if body.tracks is not None:
            have = {t.id: t for t in plan.tracks}  # upsert, like cues: tracks the body does not mention stay as they are
            for r in body.tracks:
                tr = Track.model_validate({**(have[r["id"]].model_dump() if r.get("id") in have else {}), **r})
                have[tr.id] = tr
            plan.tracks = list(have.values())
        if body.dialogue_path is not None and not Path(body.dialogue_path).is_file():
            raise ValueError(f"dialogue file not found: {body.dialogue_path}")
        for field in ("mode", "allow_cc_by", "dialogue_path", "keep_original_audio"):
            if getattr(body, field) is not None:
                setattr(plan, field, getattr(body, field))
        return engine.store.save(plan, body.note or "edited").model_dump()


@router.post("/plans/{plan_id}/spot")
def spot(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        cuts = detect_cuts(Path(engine.store.load(plan_id).video_path))  # slow: no lock held
        with engine.store.lock(plan_id):
            plan = engine.store.load(plan_id)
            keep = [c for c in plan.cues if c.status != "draft"]
            taken = {c.id for c in keep}
            plan.cues = keep + [c for c in draft_cues(plan, cuts) if c.id not in taken]
            plan.cuts = [round(c, 4) for c in cuts]
            return engine.store.save(plan, "spotted").model_dump()


@router.post("/plans/{plan_id}/cues/{cue_id}/source")
async def source_cue(plan_id: str, cue_id: str, body: SourceBody | None = None, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    music_source.bind_loop(asyncio.get_running_loop())

    def work() -> dict[str, Any]:
        with _errors():
            return engine.source_cue(plan_id, check_id(cue_id), (body.mode if body else None)).model_dump()
    return await run_in_threadpool(work)


@router.get("/voices")
def voices() -> dict[str, Any]:
    nar = NarrationProvider()
    ok = nar.availability()
    return {"voices": list_voices(), "providers": {p: {"ok": ok.ok, "reason": ok.reason} for p in SPEECH_PROVIDERS}}


@router.post("/plans/{plan_id}/narration/sample")
async def narration_sample(plan_id: str, body: SampleBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    """Hear a voice on your own words before adding the line: nothing is added to the plan."""
    music_source.bind_loop(asyncio.get_running_loop())

    def work() -> dict[str, Any]:
        with _errors():
            cue = Cue(id="sample", track="dialogue", kind="narration", text=body.text, voice=body.voice, provider=body.provider, speed=body.speed, hints={"language": body.language})
            got = engine.sample(plan_id, cue, limit=1)[0]
            return {"file": f"samples/{Path(got.path).name}", "seconds": got.duration_s, "voice": body.voice, "provider": body.provider}
    return await run_in_threadpool(work)


@router.post("/plans/{plan_id}/script")
def script(plan_id: str, body: ScriptBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors(), engine.store.lock(plan_id):
        plan = engine.store.load(plan_id)
        new = add_script(plan, body.text, mode=body.mode, start=body.start, gap=body.gap, voice=body.voice, provider=body.provider, speed=body.speed)
        if not new:
            raise ValueError("the script has no lines")
        plan.cues += new
        return engine.store.save(plan, f"script: {len(new)} line(s)").model_dump()


@router.post("/plans/{plan_id}/add_sound")
async def add_sound(plan_id: str, body: AddSoundBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    """Describe a sound and where it goes: the cue is created and sourced in one step (Ask me by default, so you hear the candidates)."""
    music_source.bind_loop(asyncio.get_running_loop())

    def work() -> dict[str, Any]:
        with _errors():
            with engine.store.lock(plan_id):
                plan = engine.store.load(plan_id)
                cid = _next_id(plan, "snd")
                hit = snap(max(0.0, body.hit_t), plan.fps) if body.hit_t is not None else None
                kind = "music" if body.track == "music" else body.kind
                plan.cues.append(Cue(id=cid, track=body.track, kind=kind, intent=body.intent, hit_t=hit, t_in=body.t_in, t_out=body.t_out, mode=body.mode,
                                     anchor="peak" if kind in ("whoosh", "riser") else "onset"))
                engine.store.save(plan, f"added {cid}")
            return engine.source_cue(plan_id, cid, body.mode).model_dump()
    return await run_in_threadpool(work)


@router.post("/plans/{plan_id}/fix")
async def fix(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    """Mechanical repairs for what QA finds (re-source clipped or silent sounds, push overrunning narration later); the rest is returned."""
    music_source.bind_loop(asyncio.get_running_loop())

    def work() -> dict[str, Any]:
        with _errors():
            return fix_plan(engine, plan_id, mixer.render_cue)
    return await run_in_threadpool(work)


@router.post("/plans/{plan_id}/cues/{cue_id}/pick")
def pick(plan_id: str, cue_id: str, body: PickBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        return engine.pick(plan_id, check_id(cue_id), body.candidate_id).model_dump()


@router.post("/plans/{plan_id}/qa")
def qa(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        plan = engine.store.load(plan_id)
        findings = check_plan(plan, mixer.render_cue)  # slow: no lock held
        saved = _save_measured(engine, plan_id, plan, "qa")
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
        _save_measured(engine, plan_id, plan, "exported")  # keeps the placement errors the export measured
        return {**res, "dir": f"exports/v{plan.version}"}


@router.get("/plans/{plan_id}/preview")
def get_preview(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    """The preview that matches the plan's sound; else the last one marked stale (still playable); else {"stale": true}."""
    with _errors():
        plan = engine.store.load(plan_id)
        sig = audio_signature(plan)
        root = engine.store.plan_dir(plan_id) / "preview"
        meta = root / sig / "preview.json"
        if meta.is_file():
            return {**json.loads(meta.read_text(encoding="utf-8")), "stale": False, "dir": f"preview/{sig}"}
        older = sorted(root.glob("*/preview.json"), key=lambda m: m.stat().st_mtime, reverse=True) if root.is_dir() else []
        if not older:
            return {"stale": True}
        return {**json.loads(older[0].read_text(encoding="utf-8")), "stale": True, "dir": f"preview/{older[0].parent.name}"}  # still playable


@router.post("/plans/{plan_id}/preview")
def make_preview(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        plan = engine.store.load(plan_id)
        root = engine.store.plan_dir(plan_id) / "preview"
        sig = audio_signature(plan)
        res = build_preview(plan, root / sig)
        old = sorted((d for d in root.iterdir() if d.is_dir() and d.name != sig), key=lambda d: d.stat().st_mtime, reverse=True)
        for d in old[1:]:  # keep the previous one: a page may still be playing it
            shutil.rmtree(d, ignore_errors=True)
        return {**res, "stale": False, "dir": f"preview/{sig}"}


@router.get("/plans/{plan_id}/video")
def get_video(plan_id: str, engine: AudioEngine = Depends(get_engine)):
    with _errors():
        video = Path(engine.store.load(plan_id).video_path)
        if not video.is_file():
            raise FileNotFoundError(f"the video file is gone: {video}")
        return FileResponse(video)  # Starlette answers Range requests, which <video> seeking needs


@router.get("/plans/{plan_id}/takes/{take_id}/peaks")
def take_peaks(plan_id: str, take_id: str, bins: int = 400, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        check_id(take_id)
        bins = max(16, min(int(bins), 4000))
        plan = engine.store.load(plan_id)
        take = next((t for c in plan.cues for t in [*c.takes, *c.candidates] if t.id == take_id), None)
        if take is None:
            raise FileNotFoundError(f"no take {take_id!r} in plan {plan_id}")
        cache = engine.store.plan_dir(plan_id) / "peaks" / f"{take_id}_{bins}.json"
        if cache.is_file():
            return json.loads(cache.read_text(encoding="utf-8"))
        peaks, dur = file_peaks(Path(take.path), bins)
        out = {"peaks": peaks, "duration": dur}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out


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
