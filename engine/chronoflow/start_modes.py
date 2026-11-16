"""ChronoFlow "New Video": how a video starts, how long it is, and what each segment card still needs.

Pure planning logic (no GPU, no network). `scene_render.py` renders the cards, the router exposes the plan, `static/nle/newvideo.js` mirrors the tables.
"""
from __future__ import annotations

from typing import Any

START_MODES = ("text", "first", "first_last", "last", "reference", "from_video")
SEG_SECONDS = 5.17
MAX_LENGTH_SECONDS = 600
_SLOTS = {"text": (), "first": ("first",), "from_video": ("first",), "first_last": ("first", "last"), "last": ("last",), "reference": ("ref1", "ref2")}
_CHAINED = ("text", "first", "from_video")  # modes whose later segments continue from the previous clip's tail frame


def slots_for(mode: str) -> tuple[str, ...]:
    if mode not in _SLOTS:
        raise ValueError(f"unknown start mode {mode!r}; choose one of {START_MODES}")
    return _SLOTS[mode]


def segment_count(length_seconds: float) -> int:
    if not 1 <= length_seconds <= MAX_LENGTH_SECONDS:
        raise ValueError(f"length must be between 1 and {MAX_LENGTH_SECONDS} seconds (got {length_seconds})")
    return max(1, round(length_seconds / SEG_SECONDS))


def build_plan(mode: str, length_seconds: float, title: str = "Untitled Video") -> dict[str, Any]:
    """The screenplay dict `/screenplay/save` stores: N empty cards, each in `mode`."""
    slots_for(mode)
    n = segment_count(length_seconds)
    scenes = []
    for i in range(n):
        last_left = length_seconds - (n - 1) * SEG_SECONDS
        duration = round(min(SEG_SECONDS, max(1.0, last_left)), 2) if i == n - 1 else SEG_SECONDS  # 5.2 would snap up to 141 frames, 5.17 is the 124-frame clip
        scenes.append({
            "shot_index": i + 1, "title": f"Shot {i + 1}", "shot_type": "Medium Tracking", "duration": duration,
            "start_mode": mode, "workflow": {"reference": "reference", "first_last": "flf2v"}.get(mode, "sliding_window"),
            "prompt": "", "first_frame": "", "last_frame": "", "ref_images": [], "first_prompt": "", "last_prompt": "",
            "state": "empty", "approved": False, "inherits_tail": i >= 1 and mode in _CHAINED,
        })
    return {"title": title, "duration": round(sum(s["duration"] for s in scenes), 1), "protagonist": {}, "anchor_images": {}, "parent_path": "", "folders": [], "scenes": scenes}


def effective_mode(scene: dict[str, Any], index: int) -> str:
    """The mode a card really renders in: a chained text card continues from a tail frame, so it is `first`; `from_video` renders as `first`."""
    mode = scene["start_mode"]
    if mode == "from_video" or (mode == "text" and index >= 1 and scene.get("inherits_tail")):
        return "first"
    return mode


def missing_inputs(scene: dict[str, Any], index: int) -> list[str]:
    """Slots (and `prompt`) the card still needs before it can render. Never silently changes the mode."""
    mode = effective_mode(scene, index)
    refs = scene.get("ref_images") or []
    have = {"first": scene.get("first_frame"), "last": scene.get("last_frame"), "ref1": refs[0] if refs else ""}
    need = {"text": [], "first": ["first"], "first_last": ["first", "last"], "last": ["last"], "reference": ["ref1"]}[mode]
    out = [s for s in need if not have[s]]
    if "first" in out and scene.get("inherits_tail"):
        out.remove("first")  # the tail frame is supplied at render time
    if not (scene.get("prompt") or "").strip():
        out.append("prompt")
    return out


def invalidate_downstream(scenes: list[dict[str, Any]], modified_index: int) -> list[int]:
    """When a scene card at `modified_index` is redone, changed, or deleted, invalidate downstream chained cards.

    A downstream card is chained if it has `inherits_tail` set to True and does NOT have an explicit `first_frame` override.
    For each contiguous chained card:
    - `approved` is reset to False.
    - `state` is set to 'stale' (if previously rendered or approved) or 'ready'.
    - `prev_tail` is cleared.
    The chain stops at the first card that has its own explicit `first_frame` or does not inherit tail.
    Returns the list of scene indices that were invalidated.
    """
    invalidated: list[int] = []
    for j in range(modified_index + 1, len(scenes)):
        s = scenes[j]
        if s.get("inherits_tail") and not s.get("first_frame"):
            s["approved"] = False
            if s.get("rendered_video") or s.get("state") in ("approved", "review", "stale"):
                s["state"] = "stale"
            elif s.get("state") != "empty":
                s["state"] = "ready"
            s["prev_tail"] = ""
            invalidated.append(j)
        else:
            break
    return invalidated


def check_assembly_readiness(scenes: list[dict[str, Any]], approved_only: bool = False) -> tuple[bool, list[str]]:
    """Check if shots in `scenes` are ready for timeline concatenation.

    Returns (is_ready, problems).
    If `approved_only` is True, only evaluates cards where approved=True (at least 1 approved card required).
    Otherwise evaluates all scenes in the list.
    """
    problems: list[str] = []
    if not scenes:
        return False, ["Storyboard contains no shots to assemble."]

    target_scenes = [s for s in scenes if s.get("approved")] if approved_only else scenes
    if not target_scenes:
        return False, ["No approved shots found to assemble."]

    for idx, s in enumerate(target_scenes):
        shot_num = s.get("shot_index", idx + 1)
        video = (
            s.get("rendered_video_filename")
            or s.get("filename")
            or s.get("video_file")
            or s.get("rendered_video")
            or s.get("video_url")
        )
        if not video:
            problems.append(f"Shot {shot_num} has not been rendered yet.")
        elif not approved_only and s.get("state") == "stale":
            problems.append(f"Shot {shot_num} has stale video from an upstream redo.")

    return len(problems) == 0, problems



DRAFT_BATCH = 10  # a 2048-token reply holds about this many shot descriptions
DRAFT_SYSTEM = ("You write shot lists for an AI video generator. Each item is one plain-language description of what happens in ONE five-second shot: "
                "the subject, the setting, the motion and the camera. Items continue the story in order, never repeat each other, contain no dialogue and no numbering. "
                "Reply with only a JSON array of strings.")


def parse_draft(text: str, n: int) -> list[str]:
    """The model's reply as exactly `n` non-blank strings, or ValueError (never padded or trimmed)."""
    import json
    import re

    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        items = json.loads(body)
    except ValueError as e:
        raise ValueError(f"the model did not return a JSON list: {e}") from e
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        raise ValueError("the model did not return a list of strings")
    if len(items) != n:
        raise ValueError(f"expected {n} prompts, the model wrote {len(items)}")
    if any(not i.strip() for i in items):
        raise ValueError("the model wrote an empty prompt")
    return [i.strip() for i in items]


async def draft_prompts(idea: str, count: int, generate) -> list[str]:
    """`count` shot descriptions for `idea`, written in batches so the story carries forward. `generate(prompt, system) -> str` is the LLM call."""
    out: list[str] = []
    while len(out) < count:
        k = min(DRAFT_BATCH, count - len(out))
        before = f"The shot before these ended with: {out[-1]}\n" if out else ""
        prompt = (f"Story idea: {idea}\n{before}Write shots {len(out) + 1} to {len(out) + k} of a {count}-shot video. "
                  f"Return exactly {k} items as a JSON array of strings.")
        out += parse_draft(await generate(prompt, DRAFT_SYSTEM), k)
    return out
