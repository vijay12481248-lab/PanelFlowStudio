"""Video Plan -> OriginalStory -> storyboard cards, and the picture job.

The owner hands a chatbot the plan kit (`plan_kit/`), gets one JSON plan back and imports it. Everything after that is the pipeline PanelFlow already has:
the plan becomes an `OriginalStory` (the Director's own shape), the start/end pictures are drawn and checked by `storyboard.draw` (cast counts, redraws, the previous
end picture reused as the next start), and each card's video prompt is `storyboard.clip_prompt`. Nothing here writes prompt text of its own.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from engine.chronoflow import plan_check
from engine.original import director  # noqa: F401  (registers the explainer genre)
from engine.original import film, storyboard
from engine.original.genres import GENRES
from engine.original.models import Bible, Character, Line, Location, OriginalStory, Panel, Premise, Scene

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "output" / "Original_Stories"
SIZES = {"16:9": (1344, 768), "9:16": (768, 1344)}
SHOT_TYPE = {"wide": "Wide Establishing", "medium": "Medium Action", "close": "Macro Close-Up"}


def plan_slug(plan: dict[str, Any]) -> str:
    """A stable folder/file name for this plan: its title plus a short hash of its content."""
    words = re.sub(r"[^a-z0-9]+", "_", str(plan.get("title", "")).lower()).strip("_")[:24] or "plan"
    return f"{words}_{hashlib.sha1(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:6]}"


def _genre_key(plan: dict[str, Any]) -> str:
    """The plan's genre, or (when it has its own style text) a derived genre carrying that look; `custom` starts from the explainer defaults."""
    base_key = plan["genre"] if plan["genre"] in GENRES else "explainer"
    style = str(plan.get("style") or "").strip()
    if not style:
        return base_key
    key = f"plan_{hashlib.sha1((base_key + style).encode()).hexdigest()[:8]}"
    base = GENRES[base_key]
    GENRES[key] = dataclasses.replace(base, key=key, art_style=style if plan["genre"] == "custom" else f"{base.art_style}, {style}")
    return key


def plan_to_story(plan: dict[str, Any]) -> OriginalStory:
    genre_key = _genre_key(plan)
    genre = GENRES[genre_key]
    place_of = {s["id"]: s["place"] for s in plan["scenes"]}
    bible = Bible(
        premise=Premise(title=plan["title"], genre=genre_key, logline=plan["logline"], tone=genre.tone, setting=plan["places"][0]["name"]),
        characters=[Character(**{k: c[k] for k in ("id", "name", "role", "age_group", "look", "personality", "species", "gender")}) for c in plan["cast"]],
        locations=[Location(id=x["id"], name=x["name"], look=x["look"]) for x in plan["places"]],
        rules=list(plan.get("rules", [])))
    scenes = []
    for s in plan["scenes"]:
        cast = list(dict.fromkeys(c for t in plan["takes"] if t["scene"] == s["id"] for c in t["cast"]))
        scenes.append(Scene(id=s["id"], location_id=s["place"], character_ids=cast, summary=s["summary"], mood=s["mood"], score=s.get("music", ""), title=s["title"]))
    panels, prev_end = [], ""
    for t in plan["takes"]:
        start = t.get("start_picture") or prev_end  # previous_end: the previous take's end picture is this take's first picture
        prev_end = t["end_picture"]
        beats = t.get("beats")
        if beats:
            shots = [{"at": b["at"], "framing": t["framing"], "camera": t.get("camera", ""), "action": f"{start} {b['action']}".strip() if k == 0 else b["action"], "characters": t["cast"]} for k, b in enumerate(beats)]
        else:
            shots = [{"at": 0.0, "framing": t["framing"], "camera": t.get("camera", ""), "action": f"{start} {t['motion']}".strip(), "characters": t["cast"]}]
        panels.append(Panel(
            id=t["id"], scene_id=t["scene"], shot=t["framing"], angle="eye_level", location_id=place_of[t["scene"]], character_ids=list(t["cast"]), action=start,
            dialogue=[Line(speaker_id="narrator", text=t["narration"])] if t.get("narration") else [], motion=t["motion"], seconds=float(t["seconds"]), shots=shots,
            end_state=t["end_picture"], atmosphere=t.get("atmosphere", ""), camera=t.get("camera", ""), key_visuals=[t["shows"]] if t.get("shows") else []))
    return OriginalStory(bible=bible, scenes=scenes, panels=panels)


def _require_valid(plan: dict[str, Any]) -> None:
    problems = plan_check.check(plan)
    if problems:
        raise ValueError("\n".join(problems))


def pictures_needed(plan: dict[str, Any]) -> int:
    """How many pictures will be drawn: an end picture per take, plus a start picture wherever the take does not start on the previous end picture."""
    story, n, prev = plan_to_story(plan), 0, None
    for p in story.panels:
        n += 1 + (0 if storyboard.continues(prev, p) else 1)
        prev = p
    return n


def plan_to_cards(plan: dict[str, Any]) -> dict[str, Any]:
    """{screenplay, warnings, story}: the storyboard (one card per take) ready for /screenplay/save, the notes for the owner, and the OriginalStory it was built from."""
    _require_valid(plan)
    story = plan_to_story(plan)
    width, height = SIZES[plan["format"]]
    warnings, cards, prev = [], [], None
    if plan["production"]["join"] == "seamless_chain":
        warnings.append("seamless_chain is not available in PanelFlow yet: the plan is imported as matched pictures (each take starts on the picture the previous take ended on).")
    for i, (t, panel) in enumerate(zip(plan["takes"], story.panels)):
        chained = storyboard.continues(prev, panel)
        if t["start_from"] == "new_picture" and chained:
            warnings.append(f"{t['id']}: starts a new picture in the same place with the same cast, so PanelFlow starts it from the previous end picture (the pictures are drawn that way).")
        cards.append({
            "shot_index": i + 1, "title": f"Shot {i + 1}: {next(s['title'] for s in plan['scenes'] if s['id'] == t['scene'])}", "shot_type": SHOT_TYPE[t["framing"]], "duration": float(t["seconds"]),
            "start_mode": "first_last", "workflow": "flf2v", "prompt": storyboard.clip_prompt(story, panel, float(t["seconds"])),
            "first_frame": "", "last_frame": "", "ref_images": [],
            "first_prompt": "" if chained else storyboard.keyframe_prompt(story, panel, "start")[0], "last_prompt": storyboard.keyframe_prompt(story, panel, "end")[0],
            "state": "ready", "approved": False, "inherits_tail": False, "width": width, "height": height, "lora_choice": "4step", "folder_id": t["scene"],
            "take_id": t["id"], "plan_scene": t["scene"], "narration": t.get("narration", ""), "shows": t.get("shows", ""), "chained_from_previous": chained})
        prev = panel
    folders = [{"id": s["id"], "name": s["title"], "description": s["summary"], "path": "", "shot_indices": [c["shot_index"] for c in cards if c["plan_scene"] == s["id"]]} for s in plan["scenes"]]
    meta = {"slug": plan_slug(plan), "title": plan["title"], "takes": len(cards), "pictures": pictures_needed(plan), "join": "matched_pictures", "narration": plan["production"]["narration"],
            "music": plan["production"].get("music", ""), "format": plan["format"], "total_seconds": plan["production"]["total_seconds"]}
    screenplay = {"title": plan["title"], "duration": sum(c["duration"] for c in cards), "protagonist": {}, "anchor_images": {"plan": meta}, "parent_path": "", "folders": folders, "scenes": cards}
    return {"screenplay": screenplay, "warnings": warnings, "story": story}


# ------------------------------------------------------------------ workspace + picture job
def save_workspace(plan: dict[str, Any], root: Path = OUTPUT_ROOT) -> Path:
    """`<root>/<slug>/plan.json` and `story.json` (the same folder `tools/produce_video.py` works in, so its later stages can continue this plan)."""
    _require_valid(plan)
    ws = root / plan_slug(plan)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "plan.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    (ws / "story.json").write_text(plan_to_story(plan).model_dump_json(indent=1), encoding="utf-8")
    return ws


def load_story(ws: Path) -> OriginalStory:
    return OriginalStory.model_validate_json((ws / "story.json").read_text(encoding="utf-8"))


def new_job_state(slug: str, story: OriginalStory) -> dict[str, Any]:
    return {"slug": slug, "status": "idle", "message": "", "done_takes": 0, "total_takes": len(story.panels), "items": [], "error": ""}


async def run_pictures(story: OriginalStory, ws: Path, input_dir: Path, state: dict[str, Any], draw_fn: Callable[[Callable[[str], None]], dict]) -> None:
    """Run `draw_fn(progress)` (the real one calls `storyboard.draw`) in a worker thread. Finished pictures are copied into the ComfyUI input folder as
    `<slug>_<take>_start.png` / `_end.png` after every progress line, so the cards can show them while the rest is still being drawn."""
    slug, seen = state["slug"], {}
    state.update(status="running", message="Drawing the pictures...", error="")

    def sync() -> None:
        items, fd = [], film.film_dir(ws)
        for p in story.panels:
            item = {"take_id": p.id, "start": "", "end": "", "problems": []}
            for which, name in (("start", f"{p.id}.png"), ("end", f"{p.id}_end.png")):
                src = fd / "frames" / name
                if src.exists():
                    dst = f"{slug}_{p.id}_{which}.png"
                    if seen.get(src) != src.stat().st_mtime_ns:
                        shutil.copy2(src, input_dir / dst)
                        seen[src] = src.stat().st_mtime_ns
                    item[which] = dst
            items.append(item)
        state["items"], state["done_takes"] = items, sum(1 for i in items if i["start"] and i["end"])

    def progress(msg: str) -> None:
        state["message"] = str(msg).strip()
        sync()

    try:
        report = await asyncio.to_thread(draw_fn, progress)
        sync()
        for item in state["items"]:
            probs = report.get(item["take_id"], {}).get("problems", {})
            item["problems"] = [f"{w}: {m}" for w, msgs in probs.items() for m in ([msgs] if isinstance(msgs, str) else msgs)]
        state.update(status="done", message="All pictures are drawn. Look at them, then render the videos.")
    except Exception as exc:  # noqa: BLE001  (reported to the owner, never swallowed)
        state.update(status="failed", error=str(exc) or exc.__class__.__name__, message="Drawing the pictures failed.")
