"""Does each character stay in the clip and keep its look? (Phase 5 of the H3 skill; docs/H3_CLIP_EVAL.md has the measurements.)

The local VLM (Ollama qwen3.5:9b) is a noisy judge, so it is only asked NARROW per-frame questions about ONE named character with its bible description, twice
in different wording; a frame counts only where both answers agree, and a flag is only ever `suspected` (never `confirmed`): the evaluator's rule that a VLM alone
does not confirm anything. Flags use the same shape as `clip_eval`: {axis, status, t, evidence}.

  object - a character visible in the first frame (both answers agree) is absent (both agree) in at least a quarter of the later sampled frames

MEASURED (docs/H3_CLIP_EVAL.md, 9 clips judged by eye): presence works - both clips where Pip leaves were flagged, none of the 5 clips where everyone stays were. The COLOUR
answer does not: it said "matches" for the washed-out outfits of Dawn Gate p070 and for the cat's hair turning blue (0 of 2), so it is reported as information
(`colours` string) and never raises a flag. Colour/lighting drift is still caught by clip_eval's histogram trigger.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2

from engine.original.clip_eval import sample_indices

FRAMES = 6  # sampled frames per clip: 2 questions x characters x frames VLM calls (about 3-4 s each)
WIDTH = 640  # the VLM sees the frame at this width (the evaluator's 384 px analysis size is too small for faces)
SCHEMA = {"type": "object", "properties": {"visible": {"type": "boolean"}, "colours_match": {"type": "boolean"}, "note": {"type": "string"}}, "required": ["visible", "colours_match", "note"]}
PROMPTS = (
    "Is the character called {name} visible in this picture? {name} is described as: {look}. Answer visible (true/false). If visible, also answer colours_match: "
    "true only if their hair colour and clothing colours match that description, otherwise false. note: one short reason.",
    "Check this picture for one character. Name: {name}. Description: {look}. visible = the character is clearly in the picture (not just a similar colour blob). "
    "colours_match = their hair and clothes have the colours in the description. If not visible, colours_match is false. note: what you see.",
)
OBJECT_PROMPTS = (  # the same two-witness question for a thing the shot needs visible (Panel.key_visuals); NOT calibrated on a clip where an object really vanishes (none was available)
    "Is this visible in the picture: {name}? ({look}) Answer visible (true/false). colours_match: true if what you see has the colours described, otherwise false. note: one short reason.",
    "Look for one object or thing in this picture: {name}. Description: {look}. visible = it is clearly in the picture. colours_match = its colours match the description. If not visible, colours_match is false. note: what you see.",
)


def frames_at(path: Path, idx: list[int], width: int = WIDTH) -> list[bytes]:
    cap = cv2.VideoCapture(str(path))
    out = []
    for i in idx:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = cap.read()
        if not ok:
            raise ValueError(f"{path}: cannot read frame {i}")
        h = round(f.shape[0] * width / f.shape[1])
        out.append(cv2.imencode(".png", cv2.resize(f, (width, h), interpolation=cv2.INTER_AREA))[1].tobytes())
    cap.release()
    return out


async def ask(provider, png: bytes, name: str, look: str, prompts: tuple = PROMPTS) -> list[dict | None]:
    answers = []
    for tpl in prompts:
        raw = await provider.analyze_vision(png, tpl.format(name=name, look=look[:240]), system_prompt="You are a strict visual QA inspector. Output only JSON.",
                                            format_schema=SCHEMA, max_tokens=300)
        try:
            answers.append(json.loads(raw))
        except Exception:
            answers.append(None)
    return answers


def agree(answers: list[dict | None], key: str) -> bool | None:
    """True/False when both witnesses give the same answer, None when they disagree or one failed."""
    vals = [a.get(key) for a in answers if isinstance(a, dict) and key in a]
    return vals[0] if len(vals) == 2 and vals[0] == vals[1] else None


def judge(name: str, series: list[dict], times: list[float]) -> tuple[list[dict], dict]:
    """Presence series -> flags (the look series is returned, not judged). `series[i]` = {"visible": bool|None, "match": bool|None} for sampled frame i."""
    flags = []
    vis = ["?" if s["visible"] is None else "P" if s["visible"] else "." for s in series]
    mat = ["?" if s["match"] is None else "M" if s["match"] else "x" for s in series]
    later = series[1:]
    gone = [i + 1 for i, s in enumerate(later) if s["visible"] is False]
    if series[0]["visible"] and len(gone) * 4 >= len(later):
        flags.append({"axis": "object", "status": "suspected", "t": times[gone[0]],
                      "evidence": f"{name} is in the first frame but absent from {len(gone)} of {len(later)} later sampled frames (first absent at {times[gone[0]]}s); both VLM answers agree"})
    return flags, {"presence": "".join(vis), "colours": "".join(mat)}  # colours: information only, see the module note


async def check(path: Path, characters: list[tuple[str, str]], provider, frames: int = FRAMES, fps: float = 24.0, objects: list[tuple[str, str]] = ()) -> dict:
    """`characters` = [(name, description)] expected in the shot (from the story bible). Returns {"characters": {name: {presence, colours}}, "flags": [...]}.
    Presence string: P visible, . absent, ? the two answers disagree; colours: M match, x mismatch, ? unknown."""
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or fps
    cap.release()
    idx = sample_indices(n, frames)
    times = [round(i / fps, 2) for i in idx]
    pngs = frames_at(path, idx)
    flags, detail, found = [], {}, {}
    for kind, items, prompts in (("characters", characters, PROMPTS), ("objects", objects, OBJECT_PROMPTS)):
        for name, look in items:
            series = []
            for png in pngs:
                ans = await ask(provider, png, name, look, prompts)
                series.append({"visible": agree(ans, "visible"), "match": agree(ans, "colours_match")})
            f, d = judge(name, series, times)
            flags += f
            (detail if kind == "characters" else found)[name] = d
    return {"characters": detail, "objects": found, "flags": flags, "times": times}


def shot_characters(story, panel) -> list[tuple[str, str]]:
    chars = {c.id: c for c in story.bible.characters}
    return [(chars[c].name, chars[c].look) for c in panel.character_ids if c in chars]


def shot_objects(panel) -> list[tuple[str, str]]:
    """What the shot says must be visible (`Panel.key_visuals`), as (name, description)."""
    return [(k, k) for k in panel.key_visuals]


def main() -> None:  # python -m engine.original.clip_identity <story.json> <shot> <clip.mp4>
    import asyncio
    import sys

    from engine.llm.registry import llm_registry
    from engine.original.models import OriginalStory

    story = OriginalStory.model_validate(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    panel = next(p for p in story.panels if p.id == sys.argv[2])
    print(json.dumps(asyncio.run(check(Path(sys.argv[3]), shot_characters(story, panel), llm_registry.get_ollama_provider(), objects=shot_objects(panel))), indent=1))


if __name__ == "__main__":
    main()


# ------------------------------------------------------------------ how many? (extra cats, a second woman)
COUNT_SCHEMA = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}
COUNT_PROMPTS = (
    "How many {things} are clearly visible in this picture? Count only the ones you can actually see. Reply as JSON {{\"count\": <number>}}.",
    "Count the {things} in this picture: whole {things} only, not parts of them and not pictures of them on objects. Reply as JSON {{\"count\": <number>}}.",
)
IRREGULAR = {"woman": "women", "man": "men", "child": "children", "person": "people"}


def plural(kind: str) -> str:
    return IRREGULAR.get(kind, kind if kind.endswith("s") else kind + "s")


async def count_png(provider, png: bytes, kind: str) -> int | None:
    """How many `kind` are in this picture: asked twice in different wording WITHOUT telling the model the expected number; a number only counts where both answers agree."""
    got = []
    for tpl in COUNT_PROMPTS:
        raw = await provider.analyze_vision(png, tpl.format(things=plural(kind)), system_prompt="You are a careful visual counter. Output only JSON.", format_schema=COUNT_SCHEMA,
                                            max_tokens=60, temperature=0.0)
        try:
            got.append(int(json.loads(raw)["count"]))
        except Exception:
            got.append(None)
    return got[0] if got[0] is not None and got[0] == got[1] else None


def judge_counts(kind: str, expected: int, counts: list[int | None], times: list[float]) -> list[dict]:
    """More of something than the shot allows, in at least a quarter of the frames where the two answers agreed, is a suspected extra (never `confirmed`: a VLM alone does not confirm)."""
    known = [(i, c) for i, c in enumerate(counts) if c is not None]
    over = [(i, c) for i, c in known if c > expected]
    if known and len(over) * 4 >= len(known):
        i, c = over[0]
        return [{"axis": "object", "status": "suspected", "t": times[i],
                 "evidence": f"{c} {plural(kind)} counted at {times[i]}s but the shot has {expected}; {len(over)} of {len(known)} agreed frames show more than {expected} (both VLM answers agree)"}]
    return []


async def count_check(path: Path, kinds: dict[str, int], provider, frames: int = FRAMES) -> dict:
    """`kinds` = {"woman": 1, "cat": 1}: the cast of the shot by kind (`film.cast_kinds`). Returns {"counts": {kind: [n|None per sampled frame]}, "flags": [...]}."""
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    cap.release()
    idx = sample_indices(n, frames)
    times = [round(i / fps, 2) for i in idx]
    pngs = frames_at(path, idx)
    out, flags = {}, []
    for kind, expected in kinds.items():
        counts = [await count_png(provider, png, kind) for png in pngs]
        out[kind] = counts
        flags += judge_counts(kind, expected, counts, times)
    return {"counts": out, "flags": flags, "times": times}
