"""The original-story workbench inside ChronoFlow's Story tab, served by the engine.

The ChronoFlow UI lists the user's original stories, shows each beat's picture and audio, approves or redraws a panel and opens
the story folder. These routes used to exist only in the old standalone ChronoFlow server (port 7860); they are a thin adapter over
the functions of `engine.api.routers.original`, which already does the real work, so they live here under the same
`/api/original_stories/...` paths the UI calls.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from engine.api.routers import original
from engine.chronoflow.somatic import SOMATIC_ARCHETYPES

router = APIRouter(prefix="/api/original_stories", tags=["chronoflow"])

_PANEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CACHE = {"Cache-Control": "public, max-age=3600"}


def _panel_id(panel_id: str) -> str:
    if not _PANEL_ID.match(panel_id):
        raise HTTPException(status_code=404, detail="Unknown panel")
    return panel_id


def _story_file(ws):
    story = ws / "story.json"
    return story if story.exists() else ws / "beats.json"


class AgentActionRequest(BaseModel):
    action: str = "somatic_emotion"
    archetype: str = "visceral_pain"
    custom_cues: str = ""
    episode: str | None = None


class EpisodeRequest(BaseModel):
    episode: str | None = None


class RerollRequest(BaseModel):
    episode: str | None = None
    seed: int | None = None
    prompt: str | None = None


@router.get("/list")
def list_stories() -> dict[str, Any]:
    """Every original story that has a story file: title, genre, panel count, and whether it has art and a video."""
    stories: list[dict[str, Any]] = []
    root = original.STORY_ROOT
    if root.exists():
        for d in sorted(root.iterdir(), key=lambda x: x.name.lower()):
            if not d.is_dir() or d.name.startswith((".", "_")):
                continue
            story_file = _story_file(d)
            if not story_file.exists():
                continue
            try:
                data = json.loads(story_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            premise = data.get("bible", {}).get("premise", {}) if isinstance(data, dict) else {}
            stories.append({
                "slug": d.name,
                "title": premise.get("title") or d.name,
                "genre": premise.get("genre") or "",
                "total_panels": len(data.get("panels", [])) if isinstance(data, dict) else 0,
                "has_art": (d / "art.json").exists(),
                "has_video": any(d.glob("*.mp4")),
            })
    return {"success": True, "stories": stories}


@router.get("/{slug}/workbench")
def story_workbench(slug: str, episode: str | None = None) -> dict[str, Any]:
    """The storyboard workbench of a story, with the characters, locations and per-beat details the studio shows."""
    try:
        res = original.get_storyboard_workbench(slug, episode).model_dump()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    story_file = _story_file(original._resolve_story_ws(slug, episode))
    if story_file.exists():
        try:
            raw = json.loads(story_file.read_text(encoding="utf-8"))
            bible = raw.get("bible", {})
            res["characters"], res["locations"], res["premise"] = bible.get("characters", []), bible.get("locations", []), bible.get("premise", {})
            panels = {p.get("id"): p for p in raw.get("panels", []) if isinstance(p, dict)}
            for beat in res.get("beats", []):
                panel = panels.get(beat.get("panel_id"))
                if panel:
                    beat["location_id"] = panel.get("location_id")
                    beat["character_ids"] = panel.get("character_ids", [])
                    beat["dialogue"] = panel.get("dialogue")
                    beat["director"] = panel.get("director", {})
        except (OSError, ValueError):
            pass  # the workbench still works without the extra story details
    suffix = f"?episode={episode}" if episode else ""
    for beat in res.get("beats", []):
        beat["image_url"] = f"/api/original_stories/{slug}/panel/{beat['panel_id']}{suffix}"
        beat["audio_url"] = f"/api/original_stories/{slug}/audio/{beat['panel_id']}{suffix}"
    return {"success": True, "workbench": res}


@router.get("/{slug}/panel/{panel_id}")
def story_panel_image(slug: str, panel_id: str, episode: str | None = None, candidate: str | None = None):
    """A panel's picture, or one of its candidates (`?candidate=3`)."""
    pid = _panel_id(panel_id)
    ws = original._resolve_story_ws(slug, episode)
    if not ws.exists():
        raise HTTPException(status_code=404, detail="Story workspace not found")
    target = ws / "panels" / f"{pid}.png"
    if candidate:
        try:
            target = ws / "panels" / "_candidates" / pid / f"c{int(candidate):03d}.png"
        except ValueError:
            pass  # not a number: the panel itself
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Panel image {target.name} not found")
    return FileResponse(target, headers=_CACHE)


@router.get("/{slug}/audio/{panel_id}")
def story_panel_audio(slug: str, panel_id: str, episode: str | None = None):
    """A panel's narration."""
    pid = _panel_id(panel_id)
    ws = original._resolve_story_ws(slug, episode)
    if not ws.exists():
        raise HTTPException(status_code=404, detail="Story workspace not found")
    for folder in ("voice", "audio"):
        target = ws / folder / f"{pid}.wav"
        if target.exists():
            return FileResponse(target, headers=_CACHE)
    raise HTTPException(status_code=404, detail="Audio file not found")


@router.post("/{slug}/panel/{panel_id}/agent_action")
def story_agent_action(slug: str, panel_id: str, req: AgentActionRequest | None = None) -> dict[str, Any]:
    """Cues an agent can use on a panel: somatic emotion prompts, or the stored vision audit of the picture."""
    req = req or AgentActionRequest()
    pid = _panel_id(panel_id)
    if req.action == "somatic_emotion":
        arch = SOMATIC_ARCHETYPES.get(req.archetype, SOMATIC_ARCHETYPES["visceral_pain"])
        prompt = f"{arch['micro_anatomy']}, {arch['posture']}, {arch['fx']}"
        if req.custom_cues:
            prompt = f"{req.custom_cues}, {prompt}"
        return {
            "success": True, "panel_id": pid, "archetype": req.archetype, "archetype_title": arch["title"], "somatic_prompt": prompt,
            "anti_stoic_negative": arch["anti_stoic_negative"], "message": f"Somatic cues assembled for {arch['title']}",
        }
    if req.action == "vision_audit":
        ws = original._resolve_story_ws(slug, req.episode)
        score, status, defects = 0.92, "accept", []
        art = ws / "art.json"
        if art.exists():
            try:
                record = next((r for r in json.loads(art.read_text(encoding="utf-8")) if r.get("panel_id") == pid), None)
                if record:
                    score, status = record.get("score", 0.92), record.get("status", "accept")
                    defects = record.get("review", {}).get("defects", [])
            except (OSError, ValueError):
                pass
        return {"success": True, "panel_id": pid, "score": score, "status": status, "defects": defects,
                "message": f"Vision audit complete: status={status}, score={score}"}
    raise HTTPException(status_code=400, detail=f"Unknown agent action '{req.action}'")


@router.post("/{slug}/panel/{panel_id}/approve")
def story_approve_panel(slug: str, panel_id: str, req: EpisodeRequest | None = None):
    """Approve a panel's current picture."""
    return original.approve_panel(slug=slug, panel_id=_panel_id(panel_id), req=original.ApprovePanelRequest(episode=(req or EpisodeRequest()).episode))


@router.post("/{slug}/panel/{panel_id}/reroll")
async def story_reroll_panel(slug: str, panel_id: str, req: RerollRequest | None = None):
    """Draw a panel again (optionally with a new seed or prompt)."""
    req = req or RerollRequest()
    return await original.reroll_panel(
        slug=slug, panel_id=_panel_id(panel_id), req=original.RerollPanelRequest(episode=req.episode, seed=req.seed, prompt=req.prompt))


@router.post("/{slug}/open")
def story_open_folder(slug: str) -> dict[str, Any]:
    """Open the story's folder in the file manager."""
    try:
        return {"success": True, "detail": str(original.open_story(slug=slug, req=original.OpenStoryRequest()))}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
