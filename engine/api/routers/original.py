"""Original Story Studio endpoints (docs/ORIGINAL_STORY_STUDIO.md)."""
import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.llm.registry import llm_registry
from engine.original import art as art_mod
from engine.original.beats import BEATS_FILE, expand_story, media_story
from engine.original import story as story_mod
from engine.original.genres import GENRES
from engine.original.models import OriginalStory

router = APIRouter(prefix="/api/original", tags=["original"])
STORY_ROOT = Path(__file__).resolve().parents[3] / "output" / "Original_Stories"


class StoryRequest(BaseModel):
    genre: str
    idea: str = Field(default="", max_length=600)
    scenes: int | None = Field(default=None, ge=3, le=14)


@router.get("/genres")
def genres():
    return {k: {"tone": g.tone, "scenes": g.scenes, "child_safe": g.child_safe} for k, g in GENRES.items()}


@router.post("/story")
async def create_story(req: StoryRequest):
    """Writes premise, bible, outline and panel script with the local LLM and stores story.json."""
    if req.genre not in GENRES:
        raise HTTPException(status_code=422, detail=f"genre must be one of {sorted(GENRES)}")
    provider = llm_registry.get_ollama_provider()  # local first, no cloud or mock fallback
    if not await provider.health_check():
        raise HTTPException(status_code=503, detail="Ollama is not reachable")
    try:
        story = await story_mod.generate_story(req.genre, provider, req.idea, req.scenes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    slug = f"{req.genre}_{uuid.uuid4().hex[:6]}"
    ws = STORY_ROOT / slug
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "story.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    return {"slug": slug, "title": story.bible.premise.title, "panels": len(story.panels), "scenes": len(story.scenes),
            "estimated_minutes": story_mod.estimated_minutes(story), "warnings": story.warnings}


def _story_videos(folder: Path) -> list[Path]:
    """Finished renders in a story folder, newest first (the *_backup and v*_prev copies are not listed)."""
    return sorted(folder.glob("story_1080p*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)


@router.get("/stories")
def list_stories():
    """Every story folder under output/Original_Stories: the dashboard shows these next to the database projects."""
    out = []
    if not STORY_ROOT.exists():
        return out
    for folder in STORY_ROOT.iterdir():
        f = folder / "story.json"
        if not folder.is_dir() or not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue    # a half-written story must not hide the others
        premise = (data.get("bible") or {}).get("premise") or {}
        videos = _story_videos(folder)
        out.append({
            "slug": folder.name,
            "title": premise.get("title") or folder.name,
            "genre": premise.get("genre") or folder.name.split("_")[0],
            "panels": len(data.get("panels") or []),
            "has_video": bool(videos),
            "video": videos[0].name if videos else None,
            "updated_at": max(p.stat().st_mtime for p in (f, *videos)),
        })
    return sorted(out, key=lambda s: -s["updated_at"])


class OpenStoryRequest(BaseModel):
    target: Literal["folder", "video"] = "folder"


@router.post("/story/{slug}/open")
def open_story(slug: str, req: OpenStoryRequest):
    """Open the story folder, or its newest finished video, with the desktop's default app."""
    folder = STORY_ROOT / Path(slug).name
    if not (folder / "story.json").exists():
        raise HTTPException(status_code=404, detail="story not found")
    target = folder
    if req.target == "video":
        videos = _story_videos(folder)
        if not videos:
            raise HTTPException(status_code=404, detail="this story has no rendered video yet")
        target = videos[0]
    if not hasattr(os, "startfile"):
        raise HTTPException(status_code=501, detail="opening files is only supported on Windows")
    os.startfile(str(target))
    return {"opened": True, "path": str(target)}


@router.get("/story/{slug}", response_model=OriginalStory)
def get_story(slug: str):
    f = STORY_ROOT / Path(slug).name / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    return OriginalStory.model_validate_json(f.read_text(encoding="utf-8"))


@router.post("/story/{slug}/art")
async def create_art(slug: str, limit: int | None = None, check: bool = True, refine: bool = False):
    """Character sheets + panel images through ComfyUI (cached; reruns only redo changed panels). Long: minutes per ~10 panels.

    refine=true runs directed panels through the review -> plan -> repair/redraw loop (slower; needs the consistency check, i.e. check=true).
    Every candidate is kept under panels/_candidates/ and repaired pictures are flagged for a look."""
    if refine and not check:
        raise HTTPException(status_code=422, detail="refine needs the picture review: it cannot run with check=false")
    ws = STORY_ROOT / Path(slug).name
    f = ws / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    story = media_story(ws)
    provider = None
    if check:
        provider = llm_registry.get_ollama_provider()
        if not await provider.health_check():
            raise HTTPException(status_code=503, detail="Ollama is not reachable (needed for the consistency check)")
    try:
        runner = art_mod.ComfyRunner()
    except Exception as e:  # ComfyUI down or workflow/model missing
        raise HTTPException(status_code=503, detail=str(e))
    return await asyncio.to_thread(art_mod.generate_art, story, ws, runner, provider, limit, refine=True if refine else None)


@router.post("/story/{slug}/animate")
async def animate_story(slug: str, beats: str | None = None, max_clips: int | None = None, seconds: float = 3.6):
    """Animates beats with the fast H3 image-to-video workflow (about a minute each) into clips/<beat>.mp4; the video step then shows them.
    `beats` is a comma list of beat ids; without it the most active beat of each scene is chosen (about one in five, or `max_clips`)."""
    from engine.original import animate as animate_mod

    if not 1.0 <= seconds <= 8.0:
        raise HTTPException(status_code=422, detail="seconds must be between 1 and 8")
    ws = STORY_ROOT / Path(slug).name
    if not (ws / "story.json").exists():
        raise HTTPException(status_code=404, detail="story not found")
    story = media_story(ws)
    ids = [b.strip() for b in beats.split(",") if b.strip()] if beats else None
    try:
        return await asyncio.to_thread(animate_mod.animate_beats, story, ws, ids, max_clips, seconds=seconds)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # ComfyUI down, workflow or models missing
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/story/{slug}/video")
async def create_video(slug: str, burn_captions: bool = True):
    """Voices every panel with an image, renders the 1080p video (Ken Burns, captions, music) and writes the YouTube package."""
    from engine.original import video as video_mod

    ws = STORY_ROOT / Path(slug).name
    f = ws / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    story = media_story(ws)
    try:
        out = await asyncio.to_thread(video_mod.build_video, story, ws, None, 30.0, burn_captions)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {**out, "package": await asyncio.to_thread(video_mod.package, story, ws)}


@router.post("/story/{slug}/pages")
async def create_pages(slug: str):
    """Letters the panels (balloons, narrator box, SFX) and composes comic pages + a PDF from the generated art."""
    from engine.original import pages as pages_mod

    ws = STORY_ROOT / Path(slug).name
    f = ws / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    story = media_story(ws)
    try:
        return await asyncio.to_thread(pages_mod.build_pages, story, ws)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---- series: a persistent cast/world, many episodes, one daily queue ---------------------------------------------------
from datetime import date as _date

from fastapi import Depends
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.jobs.manager import job_manager
from engine.original.queue import JOB_TYPE, enqueue_episodes
from engine.original.series import SeriesStore, publish_times

SERIES_ROOT = STORY_ROOT / "series"


def _store() -> SeriesStore:
    return SeriesStore(SERIES_ROOT)


class SeriesRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    genre: str
    idea: str = Field(default="", max_length=600)
    channel_id: str = ""


class EpisodesRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=30)
    start_date: _date | None = None  # first publish day; default tomorrow, then one per day at 18:00
    scenes: int | None = Field(default=None, ge=3, le=14)
    check: bool = True
    refine: bool = False  # review each picture, then repair or redraw it (slower; needs check=true)
    animate: bool = False  # animate about one beat in five with the fast H3 workflow (about a minute each)


@router.post("/series")
async def create_series(req: SeriesRequest):
    if req.genre not in GENRES:
        raise HTTPException(status_code=422, detail=f"genre must be one of {sorted(GENRES)}")
    if req.channel_id:
        from engine.anime.review.channels import channel_store
        try:
            channel_store.get(req.channel_id)
        except KeyError as e:
            raise HTTPException(status_code=422, detail=str(e))
    provider = llm_registry.get_ollama_provider()
    if not await provider.health_check():
        raise HTTPException(status_code=503, detail="Ollama is not reachable")
    try:
        bible = await story_mod.generate_series_bible(req.genre, provider, req.idea)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _store().create(req.name, req.genre, bible, req.channel_id, req.idea)


@router.get("/series")
def list_series():
    return _store().list()


@router.get("/series/{series_id}")
def get_series(series_id: str):
    try:
        return _store().get(series_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="series not found")


@router.post("/series/{series_id}/episodes")
def queue_episodes(series_id: str, req: EpisodesRequest, db: Session = Depends(get_db)):
    """Queues `count` consecutive episodes as durable jobs with one publish slot per day (upload itself is not automated yet)."""
    if req.refine and not req.check:
        raise HTTPException(status_code=422, detail="refine needs the picture review: it cannot run with check=false")
    store = _store()
    try:
        store.get(series_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="series not found")
    try:
        return enqueue_episodes(db, store, series_id, req.count, publish_times(req.count, req.start_date), req.scenes, req.check, req.refine, req.animate)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/jobs")
def list_episode_jobs(limit: int = 50):
    return [j for j in job_manager.list_all_jobs(limit=200) if j["job_type"] == JOB_TYPE][:limit]


class UploadRequest(BaseModel):
    made_for_kids: bool  # required: a legal declaration the channel owner makes, never defaulted
    privacy: str = "private"
    schedule: bool = False  # private upload that YouTube publishes at the episode's slot
    confirm_public: bool = False
    force: bool = False


@router.post("/series/{series_id}/episodes/{number}/upload", status_code=202)
def upload_episode_route(series_id: str, number: int, req: UploadRequest):
    """Starts the upload in the background (minutes for a long video); poll the series for `upload_status`."""
    import threading

    from engine.api.routers.youtube import auth as yt_auth
    from engine.original import upload as upload_mod
    from engine.youtube.auth import AuthError
    from engine.youtube.client import YouTubeClient

    store = _store()
    if not yt_auth.status()["connected"]:
        raise HTTPException(status_code=409, detail="YouTube is not connected")
    kwargs = dict(made_for_kids=req.made_for_kids, privacy=req.privacy, schedule=req.schedule,
                  confirm_public=req.confirm_public, force=req.force)
    try:
        upload_mod.plan_upload(store, series_id, number, **kwargs)  # refuse before starting anything
    except KeyError:
        raise HTTPException(status_code=404, detail="series not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    def run():
        try:
            upload_mod.upload_episode(store, series_id, number, YouTubeClient(yt_auth), **kwargs)
        except (AuthError, Exception):  # the failure is recorded on the episode by upload_episode
            pass

    threading.Thread(target=run, daemon=True).start()
    return {"series": series_id, "episode": number, "status": "uploading"}


@router.post("/story/{slug}/beats")
async def create_beats(slug: str):
    """One picture per narrated moment: splits each panel's narration and writes a brief from the spoken text (beats.json)."""
    ws = STORY_ROOT / Path(slug).name
    f = ws / "story.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="story not found")
    provider = llm_registry.get_ollama_provider()
    if not await provider.health_check():
        raise HTTPException(status_code=503, detail="Ollama is not reachable")
    story = await expand_story(OriginalStory.model_validate_json(f.read_text(encoding="utf-8")), provider)
    (ws / BEATS_FILE).write_text(story.model_dump_json(indent=2), encoding="utf-8")
    return {"beats": len(story.panels), "warnings": story.warnings}


# ------------------------------------------------------------------ animated film (engine/original/film.py, film_master.py, score.py)
_FILM_JOBS: dict[str, dict] = {}


def _film_start(slug: str, kind: str, fn) -> dict:
    """Runs one film stage in a background thread (a stage is minutes to hours). One at a time: the stages share one GPU."""
    import threading

    if any(j["status"] == "running" for j in _FILM_JOBS.values()):
        raise HTTPException(status_code=409, detail="another film stage is running (one GPU); poll /film/job/{id} or cancel it")
    job = {"id": uuid.uuid4().hex[:8], "slug": slug, "kind": kind, "status": "running", "progress": 0.0, "message": "starting", "result": None, "error": None,
           "cancel": False}
    _FILM_JOBS[job["id"]] = job

    def run():
        try:
            job["result"] = fn(lambda p, m: job.update(progress=round(p, 3), message=m), lambda: job["cancel"])
            job["status"] = "done"
        except BaseException as e:  # recorded on the job; the thread must not die silently
            job["status"], job["error"] = ("cancelled" if str(e) == "cancelled" else "failed"), str(e)[:600]

    threading.Thread(target=run, daemon=True).start()
    return {k: job[k] for k in ("id", "slug", "kind", "status")}


def _film_story(slug: str) -> tuple[Path, OriginalStory]:
    ws = STORY_ROOT / Path(slug).name
    if not (ws / "story.json").exists():
        raise HTTPException(status_code=404, detail="story not found")
    return ws, OriginalStory.model_validate_json((ws / "story.json").read_text(encoding="utf-8"))


def _ids(ids: str | None) -> list[str] | None:
    return [i.strip() for i in ids.split(",") if i.strip()] if ids else None


def _pairs(text: str | None) -> dict[str, int] | None:
    return {k: int(v) for k, v in (kv.split(":") for kv in text.split(","))} if text else None


@router.post("/story/{slug}/film/frames", status_code=202)
def film_frames(slug: str, ids: str | None = None, rerolls: str | None = None):
    """16:9 first frame per shot (`ids` = comma list; `rerolls` = `p003:1,p005:2` new seeds for pictures that were not good enough)."""
    from engine.original import film

    ws, story = _film_story(slug)
    rer = _pairs(rerolls)
    return _film_start(slug, "frames", lambda prog, cancelled: film.make_frames(story, ws, art_mod.ComfyRunner(), _ids(ids), rer, prog, cancelled))


@router.post("/story/{slug}/film/clips", status_code=202)
def film_clips(slug: str, ids: str | None = None, seeds: str | None = None, quiet: str | None = None):
    """H3 clip per shot from its frame; a speaking shot gets its character's voice anchored to the face (lip sync). Hours for a whole film."""
    from engine.original import film

    ws, story = _film_story(slug)
    sd = _pairs(seeds)
    return _film_start(slug, "clips", lambda prog, cancelled: film.make_clips(story, ws, _ids(ids), sd, progress=prog, is_cancelled=cancelled, quiet=_ids(quiet)))


@router.post("/story/{slug}/film/score", status_code=202)
def film_score(slug: str):
    """One local ACE-Step cue per scene, sized from the clips already made (unloads ComfyUI and the LLM first)."""
    from engine.original import film_master, score

    ws, story = _film_story(slug)

    def run(prog, cancelled):
        secs: dict[str, float] = {}
        for c in film_master.timeline(story, ws):
            secs[c["scene"]] = secs.get(c["scene"], 0.0) + c["seconds"]
        score.free_gpu()
        return {k: str(v) for k, v in score.make_cues(story, ws, secs, prog).items()}

    return _film_start(slug, "score", run)


@router.post("/story/{slug}/film/master", status_code=202)
def film_master_render(slug: str, ids: str | None = None, music: bool = True, name: str = "film_master"):
    """Cuts every clip in story order, mixes the score under it (ducked), writes the 1080p mp4 and the SRT captions."""
    from engine.original import film_master

    ws, story = _film_story(slug)

    def run(prog, cancelled):
        cues = {sc.id: ws / "film" / "audio" / "music" / f"{sc.id}.wav" for sc in story.scenes} if music else None
        out = film_master.render(story, ws, cues, _ids(ids), name, story.bible.premise.title)
        return {**out, "loudness": film_master.loudness(Path(out["video"]))}

    return _film_start(slug, "master", run)


@router.get("/film/job/{job_id}")
def film_job(job_id: str):
    job = _FILM_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="film job not found (jobs live in engine memory; a restart forgets them)")
    return {k: v for k, v in job.items() if k != "cancel"}


@router.post("/film/job/{job_id}/cancel")
def film_job_cancel(job_id: str):
    job = _FILM_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="film job not found")
    job["cancel"] = True
    return {"id": job_id, "cancelling": True}


@router.get("/story/{slug}/film/status")
def film_status(slug: str):
    """What exists per shot: frame, clip, its measured motion (a clip below the stillness limit is flagged), and the running job if any."""
    from engine.original import film

    ws, story = _film_story(slug)
    fd = ws / "film"
    clips = json.loads((fd / "clips.json").read_text(encoding="utf-8")) if (fd / "clips.json").exists() else {}
    shots = []
    for p in story.panels:
        c = clips.get(p.id, {})
        shots.append({"id": p.id, "scene": p.scene_id, "frame": (fd / "frames" / f"{p.id}.png").exists(), "clip": (fd / "clips" / f"{p.id}.mp4").exists(),
                      "speaks": bool(p.dialogue), "seconds": c.get("stats", {}).get("seconds"), "motion": c.get("stats", {}).get("motion"),
                      "too_still": bool(c) and c.get("stats", {}).get("motion", 9) < film.MIN_MOTION})
    running = [{k: j[k] for k in ("id", "kind", "status", "progress", "message")} for j in _FILM_JOBS.values() if j["slug"] == Path(slug).name and j["status"] == "running"]
    return {"shots": len(shots), "frames": sum(s["frame"] for s in shots), "clips": sum(s["clip"] for s in shots),
            "seconds": round(sum(s["seconds"] or 0 for s in shots), 1), "too_still": [s["id"] for s in shots if s["too_still"]], "running": running, "detail": shots}
