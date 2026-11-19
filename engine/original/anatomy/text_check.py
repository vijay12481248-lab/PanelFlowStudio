"""Stray-text check and redraw for pictures that must carry no writing (HiDream prints poster headlines made of prompt words, measured 2026-11-17).

One blind question to ONE judge (qwen3.5:9b through Ollama), asked on the whole picture and on a zoomed top band, where the headlines sit. Any "yes" counts as text. The judge is
never told what to expect; a reply that is not a clear yes/no is `None` (unverified), never a guess. The picture is redrawn with a new seed while text is found. This is a lighter
cousin of the anatomy review (`review.py`, two judges, about a minute a picture): a headline is large and obvious, so one judge on two views is enough, and it is measured below.
"""
from __future__ import annotations

import asyncio
import io
import time
from dataclasses import dataclass, field

from PIL import Image

from engine.comfyui.art import _drop_text_negations
from engine.original.anatomy.loop import SEED_STEP
from engine.original.anatomy.questions import parse_yes_no
from engine.original.anatomy.rules import text_requested

TEXT_PROMPT = ("Look at this picture. Is there any text in it: letters, words, numbers, a title, a caption, a speech bubble with writing, a sign with writing, a signature "
               "or a watermark? Answer with the single word yes or no first, then one short sentence naming what you can see.")


def top_band(png: bytes, share: float = 0.4, target_side: int = 1280) -> bytes:
    """The top `share` of the picture, upscaled: that is where the large headlines are drawn."""
    with Image.open(io.BytesIO(png)) as opened:
        img = opened.convert("RGB")
    band = img.crop((0, 0, img.width, max(1, int(img.height * share))))
    scale = target_side / max(band.size)
    band = band.resize((max(1, round(band.width * scale)), max(1, round(band.height * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    band.save(buf, "PNG")
    return buf.getvalue()


async def has_stray_text(judge, png: bytes) -> bool | None:
    """True when the judge sees text on the whole picture or the top band, False when it answers no to both, None when it gave no clear answer."""
    answers = [parse_yes_no(await judge.ask(view, TEXT_PROMPT)) for view in (png, top_band(png))]
    if True in answers:
        return True
    return False if all(a is False for a in answers) else None


@dataclass
class TextCheckedPicture:
    png: bytes
    status: str  # "clean" | "best_effort" (text on every attempt) | "unverified" (the judge gave no answer)
    seed: int
    attempts: list[dict] = field(default_factory=list)


def free_comfyui(base: str = "http://127.0.0.1:8188") -> None:
    """Ask ComfyUI to unload its models so the Ollama judge fits in VRAM next to it (they do not fit together). Never raises: a ComfyUI that is gone needs no freeing."""
    import json
    import urllib.request

    try:
        req = urllib.request.Request(base + "/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode(), headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception:
        pass


def generate_text_free(art_engine, judge, *, prompt: str, width: int, height: int, seed: int, prefix: str, workflow_id: str, max_attempts: int = 4,
                       max_seconds: float = 300.0, before_judge=None, before_draw=None, fallback_workflow_id: str | None = None,
                       fallback_after: int = 2) -> TextCheckedPicture:
    """Draw, ask the judge, redraw with seed + 7919 while text is found. A prompt that asks for writing is not checked.
    `before_judge` runs before each judge call (free ComfyUI's VRAM), `before_draw` before each draw (free the judge's).
    `fallback_workflow_id`: from attempt `fallback_after` on, draw with that model instead (a prompt that makes HiDream print its words did so on every seed: measured 4/4)."""
    t0 = time.monotonic()
    if before_draw:
        before_draw()
    first = art_engine.generate(prompt, "", width, height, seed, prefix, workflow_id=workflow_id)
    if text_requested(_drop_text_negations(prompt)):  # "no text, no letters" is the opposite of asking for writing
        return TextCheckedPicture(png=first.png, status="unverified", seed=seed, attempts=[{"seed": seed, "text": None, "note": "prompt asks for text"}])
    art, attempts = first, []
    for i in range(max_attempts):
        s = seed + i * SEED_STEP
        if i > 0:
            if time.monotonic() - t0 > max_seconds:
                break
            if before_draw:
                before_draw()
            use = fallback_workflow_id if fallback_workflow_id and i >= fallback_after else workflow_id
            art = art_engine.generate(prompt, "", width, height, s, prefix, workflow_id=use)
        if before_judge:
            before_judge()
        found = asyncio.run(has_stray_text(judge, art.png))
        attempts.append({"seed": s, "text": found, "workflow": fallback_workflow_id if fallback_workflow_id and i >= fallback_after else workflow_id})
        if found is False:
            return TextCheckedPicture(png=art.png, status="clean", seed=s, attempts=attempts)
        if found is None:  # the judge gave nothing usable: a redraw would be a coin flip
            return TextCheckedPicture(png=art.png, status="unverified", seed=s, attempts=attempts)
    return TextCheckedPicture(png=art.png, status="best_effort", seed=attempts[-1]["seed"], attempts=attempts)
