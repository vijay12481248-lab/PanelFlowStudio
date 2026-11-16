"""Audio Studio REST API: sound plans (cue sheets), sourcing, checks, mix and export. The MCP tools call exactly these endpoints."""
from __future__ import annotations

import asyncio
import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from engine.audio.studio import mix as mixer
from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.peaks import file_peaks
from engine.audio.studio.plan import Cue, PlanStore, SoundPlan, Track, check_id, snap
from engine.audio.studio.preview import audio_signature, build_preview
from engine.audio.studio.qa import check_plan
from engine.audio.studio.sources import music as music_source
from engine.audio.studio.sources.ambient_synth import AmbientSynthProvider
from engine.audio.studio.sources.foley_synth import FoleySynthProvider
from engine.audio.studio.sources.local_bank import LocalBankProvider
from engine.audio.studio.sources.music import MusicProvider
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
        _engine = AudioEngine(PlanStore(), [LocalBankProvider(), FoleySynthProvider(), AmbientSynthProvider(), SynthProvider(), OpenverseProvider(), MusicProvider()])
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


class SpotBody(BaseModel):
    use_vision: bool = False


class ImportCueBody(BaseModel):
    file_path: str
    label: str = ""


class SearchAudioBody(BaseModel):
    query: str
    track: str = "sfx"
    limit: int = 12


class PickBody(BaseModel):
    candidate_id: str


class RenderBody(BaseModel):
    target_lufs: float = -14.0
    mux: bool = False
    allow_incomplete: bool = False


class ApplyRemediationsBody(BaseModel):
    remediation_ids: list[str] = []


class MasterBody(BaseModel):
    standard: Literal["youtube", "ebu_r128", "custom"] = "youtube"
    target_lufs: float | None = None
    mux: bool = False


class ExportDawBody(BaseModel):
    standard: Literal["youtube", "ebu_r128", "custom"] = "youtube"
    target_lufs: float | None = None
    make_zip: bool = True


class AutoStoryBody(BaseModel):
    narration_path: str | None = None
    story_title: str = "Story"
    use_vision: bool = False
    standard: Literal["youtube", "ebu_r128", "custom"] = "youtube"


def _save_measured(engine: AudioEngine, plan_id: str, measured: Any, note: str):
    """Copy the placement errors a long run measured onto the plan as it is now, so edits made meanwhile are not overwritten."""
    errors = {c.id: c.placement_error_ms for c in measured.cues if c.placement_error_ms is not None}
    with engine.store.lock(plan_id):
        fresh = engine.store.load(plan_id)
        for c in fresh.cues:
            if c.id in errors:
                c.placement_error_ms = errors[c.id]
        return engine.store.save(fresh, note)


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
        for field in ("mode", "allow_cc_by", "dialogue_path"):
            if getattr(body, field) is not None:
                setattr(plan, field, getattr(body, field))
        return engine.store.save(plan, body.note or "edited").model_dump()


@router.get("/library/files")
def list_library_files(engine: AudioEngine = Depends(get_engine)) -> list[dict[str, Any]]:
    with _errors():
        provider = next((p for p in engine.providers if isinstance(p, LocalBankProvider)), None)
        if provider is None:
            provider = LocalBankProvider()
        files = provider.scan_library()
        return [{"name": f.name, "path": str(f), "size": f.stat().st_size} for f in files]


@router.post("/library/upload")
async def upload_library_file(
    file: UploadFile = File(...),
    engine: AudioEngine = Depends(get_engine),
) -> dict[str, Any]:
    with _errors():
        provider = next((p for p in engine.providers if isinstance(p, LocalBankProvider)), None)
        if provider is None:
            provider = LocalBankProvider()
        dest_dir = provider.library_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(file.filename or "sound.wav").name
        dest_file = dest_dir / safe_name
        contents = await file.read()
        dest_file.write_bytes(contents)
        return {
            "name": safe_name,
            "path": str(dest_file.resolve()),
            "size": len(contents),
        }


@router.post("/search")
def search_catalog(body: SearchAudioBody, engine: AudioEngine = Depends(get_engine)) -> list[dict[str, Any]]:
    with _errors():
        from engine.audio.studio.sources.local_bank import LocalBankProvider
        from engine.audio.studio.sources.openverse import OpenverseProvider
        import urllib.parse

        results: list[dict[str, Any]] = []
        track_role = body.track if body.track in ("dialogue", "music", "sfx", "ambience", "foley") else "sfx"
        dummy_cue = Cue(id="search", track=track_role, kind=body.query, intent=body.query)
        dummy_plan = SoundPlan(id="search", video_path="v.mp4", fps=24, duration=60)
        tmp_dir = engine.store.root / "cache_search"

        # 1. Search local user sound bank
        local_p = next((p for p in engine.providers if isinstance(p, LocalBankProvider)), None)
        if local_p:
            local_cands = local_p.find(dummy_cue, tmp_dir, dummy_plan, limit=body.limit)
            for c in local_cands:
                results.append({
                    "id": c.id,
                    "name": c.label,
                    "type": dummy_cue.track,
                    "duration_sec": c.duration_s,
                    "file_url": f"/api/audio/studio/stream?path={urllib.parse.quote(str(Path(c.path).resolve()))}",
                    "license": (c.provenance and c.provenance.licence) or "User-Supplied",
                    "source": "local_library"
                })

        # 2. Search Openverse CC0 if more results needed
        if len(results) < body.limit:
            ov_p = next((p for p in engine.providers if isinstance(p, OpenverseProvider)), None)
            if ov_p:
                ov_cands = ov_p.find(dummy_cue, tmp_dir, dummy_plan, limit=body.limit - len(results))
                for c in ov_cands:
                    results.append({
                        "id": c.id,
                        "name": c.label,
                        "type": dummy_cue.track,
                        "duration_sec": c.duration_s,
                        "file_url": f"/api/audio/studio/stream?path={urllib.parse.quote(str(Path(c.path).resolve()))}",
                        "license": (c.provenance and c.provenance.licence) or "CC0",
                        "source": "openverse"
                    })

        return results


@router.get("/stream")
def stream_audio(path: str):
    with _errors():
        target = Path(path).resolve()
        if not target.is_file():
            raise FileNotFoundError(f"audio file not found: {path}")
        ext = target.suffix.lower()
        media_type = "audio/wav"
        if ext == ".mp3":
            media_type = "audio/mpeg"
        elif ext == ".ogg":
            media_type = "audio/ogg"
        elif ext == ".flac":
            media_type = "audio/flac"
        elif ext in (".m4a", ".aac"):
            media_type = "audio/mp4"
        return FileResponse(target, media_type=media_type)


@router.post("/plans/{plan_id}/spot")
def spot(plan_id: str, body: SpotBody | None = None, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        video_p = Path(engine.store.load(plan_id).video_path)
        cuts = detect_cuts(video_p)  # slow: no lock held
        with engine.store.lock(plan_id):
            plan = engine.store.load(plan_id)
            keep = [c for c in plan.cues if c.status != "draft"]
            taken = {c.id for c in keep}
            use_v = bool(body and body.use_vision)
            plan.cues = keep + [c for c in draft_cues(plan, cuts, use_vision=use_v, video_path=video_p) if c.id not in taken]
            plan.cuts = [round(c, 4) for c in cuts]
            return engine.store.save(plan, "spotted").model_dump()


@router.post("/plans/{plan_id}/cues/{cue_id}/import_file")
def import_cue_file(plan_id: str, cue_id: str, body: ImportCueBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        from engine.audio.studio.engine import _measured, _to_take
        provider = next((p for p in engine.providers if isinstance(p, LocalBankProvider)), None)
        if provider is None:
            provider = LocalBankProvider()
        out_dir = engine.store.take_dir(plan_id)
        cue = engine.store.load(plan_id).cue(cue_id)
        cand = provider.import_take(Path(body.file_path), cue, out_dir, body.label)
        cand = _measured(cand)
        with engine.store.lock(plan_id):
            plan = engine.store.load(plan_id)
            cue = plan.cue(cue_id)
            take = _to_take(cand)
            cue.takes.append(take)
            cue.chosen_take = take.id
            cue.status = "ready"
            cue.reason = None
            return engine.store.save(plan, f"imported {body.file_path}").model_dump()


@router.post("/plans/{plan_id}/cues/{cue_id}/source")
async def source_cue(plan_id: str, cue_id: str, body: SourceBody | None = None, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    music_source.bind_loop(asyncio.get_running_loop())

    def work() -> dict[str, Any]:
        with _errors():
            return engine.source_cue(plan_id, check_id(cue_id), (body.mode if body else None)).model_dump()
    return await run_in_threadpool(work)


@router.post("/plans/{plan_id}/cues/{cue_id}/pick")
def pick(plan_id: str, cue_id: str, body: PickBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        return engine.pick(plan_id, check_id(cue_id), body.candidate_id).model_dump()


@router.post("/plans/{plan_id}/cues/{cue_id}/loop")
def loop_cue(plan_id: str, cue_id: str, crossfade_sec: float = 1.5, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        from engine.audio.studio.loop import create_seamless_loop
        from engine.audio.studio.measure import measure_take
        plan = engine.store.load(plan_id)
        cue = plan.cue(check_id(cue_id))
        take = cue.chosen()
        if not take or not Path(take.path).is_file():
            raise FileNotFoundError(f"no chosen take for cue {cue_id}")

        in_p = Path(take.path)
        out_p = in_p.parent / f"{in_p.stem}_loop.wav"
        create_seamless_loop(in_p, out_p, crossfade_sec=crossfade_sec)

        m = measure_take(out_p)
        take.path = str(out_p.resolve())
        take.duration_s = m.duration_s
        take.onset_s = m.onset_s
        take.peak_s = m.peak_s
        take.peak_db = m.peak_db
        take.rms_db = m.rms_db
        take.clipped_samples = m.clipped_samples
        saved = engine.store.save(plan, f"converted cue {cue_id} to seamless loop")
        return {"plan": saved.model_dump(), "loop_path": str(out_p.resolve()), "duration_s": m.duration_s}


@router.post("/plans/{plan_id}/cues/{cue_id}/stems")
def isolate_stems(plan_id: str, cue_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        from engine.audio.studio.loop import isolate_score_stems
        plan = engine.store.load(plan_id)
        cue = plan.cue(check_id(cue_id))
        take = cue.chosen()
        if not take or not Path(take.path).is_file():
            raise FileNotFoundError(f"no chosen take for cue {cue_id}")

        in_p = Path(take.path)
        out_d = in_p.parent / "stems"
        stems = isolate_score_stems(in_p, out_d)
        return {"stems": {k: str(v.resolve()) for k, v in stems.items()}}


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


@router.post("/plans/{plan_id}/critique")
def critique(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        from engine.audio.studio.critique import critique_plan
        plan = engine.store.load(plan_id)
        report = critique_plan(plan)
        return report.model_dump()


@router.post("/plans/{plan_id}/critique/apply")
def apply_critique_remediations(plan_id: str, body: ApplyRemediationsBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        from engine.audio.studio.critique import apply_remediations
        plan = engine.store.load(plan_id)
        updated_plan, applied_ids = apply_remediations(plan, body.remediation_ids)
        saved = engine.store.save(updated_plan, f"applied {len(applied_ids)} critique fixes")
        return {"plan": saved.model_dump(), "applied_ids": applied_ids}


@router.get("/plans/{plan_id}/cues/{cue_id}/waveform")
def get_cue_waveform(plan_id: str, cue_id: str, bins: int = 100, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        from engine.chronoflow.media_tools import waveform
        plan = engine.store.load(plan_id)
        cue = plan.cue(cue_id)
        take = cue.chosen()
        if not take or not Path(take.path).is_file():
            return {"peaks": []}
        peaks = waveform(Path(take.path), bins=max(10, min(bins, 1000)))
        return {"peaks": peaks}


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


@router.post("/plans/{plan_id}/master")
def master_broadcast(plan_id: str, body: MasterBody | None = None, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        from engine.audio.studio.master import master_plan
        b = body or MasterBody()
        plan = engine.store.load(plan_id)
        out_wav = engine.store.plan_dir(plan_id) / "exports" / f"master_{b.standard}.wav"
        out_video = engine.store.plan_dir(plan_id) / "exports" / f"master_{b.standard}.mp4" if b.mux and plan.video_path else None
        res = master_plan(
            plan,
            out_wav,
            standard=b.standard,
            custom_target_lufs=b.target_lufs,
            video_in=Path(plan.video_path) if out_video else None,
            out_video=out_video,
        )
        return res


@router.post("/plans/{plan_id}/export_daw")
def export_daw(plan_id: str, body: ExportDawBody | None = None, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        from engine.audio.studio.export_daw import package_daw_delivery
        b = body or ExportDawBody()
        plan = engine.store.load(plan_id)
        out_dir = engine.store.plan_dir(plan_id) / "daw_delivery"
        res = package_daw_delivery(
            plan,
            out_dir,
            standard=b.standard,
            custom_target_lufs=b.target_lufs,
            make_zip=b.make_zip,
        )
        return res


@router.get("/plans/{plan_id}/export_daw/fcpxml")
def export_fcpxml_stream(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> Response:
    with _errors():
        from engine.audio.studio.export_daw import generate_fcpxml
        plan = engine.store.load(plan_id)
        xml_content = generate_fcpxml(plan)
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="timeline_{plan_id}.fcpxml"'},
        )


@router.get("/plans/{plan_id}/export_daw/edl")
def export_edl_stream(plan_id: str, engine: AudioEngine = Depends(get_engine)) -> Response:
    with _errors():
        from engine.audio.studio.export_daw import generate_cmx3600_edl
        plan = engine.store.load(plan_id)
        edl_content = generate_cmx3600_edl(plan)
        return Response(
            content=edl_content,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="timeline_{plan_id}.edl"'},
        )


@router.post("/plans/{plan_id}/pipeline/story_auto")
def pipeline_story_auto(plan_id: str, body: AutoStoryBody | None = None, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    with _errors():
        from engine.audio.studio.pipeline_hooks import auto_soundtrack_original_story
        b = body or AutoStoryBody()
        plan = engine.store.load(plan_id)
        return auto_soundtrack_original_story(
            engine,
            video_path=Path(plan.video_path),
            narration_path=Path(b.narration_path) if b.narration_path else None,
            story_title=b.story_title,
            use_vision=b.use_vision,
            standard=b.standard,
        )


class AutoFoleyBody(BaseModel):
    scenes: list[dict[str, Any]]
    auto_source: bool = True


@router.post("/plans/{plan_id}/auto_foley")
def auto_foley_plan(plan_id: str, body: AutoFoleyBody, engine: AudioEngine = Depends(get_engine)) -> dict[str, Any]:
    """Analyze storyboard scene visual prompts and auto-populate atmospheric soundscapes and foley cues."""
    with _errors():
        from engine.audio.studio.foley_generator import auto_populate_sound_plan
        plan = auto_populate_sound_plan(plan_id, body.scenes, auto_source=body.auto_source)
        return {
            "success": True,
            "plan_id": plan.id,
            "cue_count": len(plan.cues),
            "note": plan.note,
            "plan": plan.model_dump(),
        }

