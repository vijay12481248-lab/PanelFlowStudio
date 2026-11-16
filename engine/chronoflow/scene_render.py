"""Render one storyboard card in the mode it was planned for (see start_modes.py).

First-frame cards (and chained text cards) keep ChronoFlow's own graph builder; text, last-frame, first+last and reference cards run through
the registered `h3_modes` workflows. Nothing here changes a card's mode: a missing prompt, slot or file is a 400 that names it.
"""
from __future__ import annotations

import asyncio
import random
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from engine.chronoflow import start_modes
from engine.chronoflow.timeline_assemble import assemble_storyboard_sequence, resolve_scene_clip
from engine.original import h3_modes
from engine.original.film import snap_frames

PORTRAIT_SIZE = h3_modes.T2VA_SIZE[::-1]  # (544, 960) for 9:16
OFFICIAL_MARKERS = ("integrated_multimodal_description", "detailed_description:")  # a prompt already in the official layout is sent as written


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _frame(input_dir: Path, name: str, what: str) -> Path:
    if not name or name in (".", "..") or Path(name).name != name:
        raise _bad(f"{what}: '{name}' is not a picture name")
    path = input_dir / name
    if not path.exists():
        raise _bad(f"{what}: picture '{name}' is not in the ComfyUI input folder")
    return path


CAMERA = "exactly what the shot description says; if it describes no camera movement the camera stays still"  # h3_modes' default would contradict a written push-in
REF_STYLE = "The target video keeps the visual style of the reference pictures."  # h3_modes' default is "clean anime film style"


def _wrap(mode: str, prompt: str, seconds: float, n_refs: int) -> str:
    if any(m in prompt for m in OFFICIAL_MARKERS):
        return prompt
    if mode == "t2va":  # t2va_prompt() wants a scene + an action; the card holds one description
        return h3_modes._fields(h3_modes._body(prompt, CAMERA), h3_modes.QUIET, "none")
    if mode == "fl2va":
        return h3_modes.fl2va_prompt(prompt, seconds, camera=CAMERA)
    if mode == "l2va":
        return h3_modes.l2va_prompt(prompt, seconds, camera=CAMERA)
    subjects = [("the subject shown in the reference picture", n, "fully_preserved", "appearance, face and clothing") for n in range(1, n_refs + 1)]
    return h3_modes.ref2va_prompt(subjects, prompt, style=REF_STYLE, camera=CAMERA)


async def render_scene(pipeline, scene: dict[str, Any], index: int, *, width: int, height: int, steps: int, lora_name: str,
                       out_dir: Path, input_dir: Path, tail_name: str) -> tuple[Path, str | None]:
    """Returns (mp4 in out_dir, tail-frame filename written to input_dir or None)."""
    label = f"Shot {index + 1}"
    try:
        start_modes.slots_for(scene.get("start_mode"))
    except ValueError as e:
        raise _bad(f"{label}: {e}")
    mode = start_modes.effective_mode(scene, index)
    missing = start_modes.missing_inputs(scene, index)
    if missing:
        raise _bad(f"{label} cannot render in '{scene['start_mode']}' mode, it still needs: {', '.join(missing)}")
    prompt = scene["prompt"].strip()
    seconds = float(scene.get("duration") or start_modes.SEG_SECONDS)
    size = PORTRAIT_SIZE if height > width else h3_modes.T2VA_SIZE
    dest = out_dir / f"shot_{index + 1}_{uuid.uuid4().hex[:6]}.mp4"

    if mode == "first":
        first = scene.get("first_frame") or ""
        if first:
            _frame(input_dir, first, f"{label} first frame")
        else:  # chained card: continue from the previous approved clip
            first = scene.get("prev_tail") or ""
            if not first:
                raise _bad(f"{label} continues from the previous shot, but the previous shot has no tail frame yet (render and approve it first)")
            _frame(input_dir, first, f"{label} previous tail frame")
        graph = pipeline.build_h3_prompt(prompt=prompt, width=width, height=height, length=snap_frames(seconds), steps=steps, lora_name=lora_name,
                                         workflow_mode="sliding_window", first_frame_filename=first)
        shutil.copy2(await pipeline.execute_prompt(graph), dest)
    else:
        kw: dict[str, Any] = {"seed": random.randint(1, 1_000_000_000), "seconds": seconds}
        n_refs = 0
        if mode == "first_last":
            kw["first"], kw["last"] = _frame(input_dir, scene["first_frame"], f"{label} first frame"), _frame(input_dir, scene["last_frame"], f"{label} last frame")
        elif mode == "last":
            kw["last"] = _frame(input_dir, scene["last_frame"], f"{label} last frame")
        elif mode == "reference":
            refs = [r for r in scene.get("ref_images") or [] if r]
            if len(refs) > 2:
                raise _bad(f"{label}: reference mode takes 1 or 2 pictures (got {len(refs)})")
            kw["refs"], n_refs = [_frame(input_dir, r, f"{label} reference") for r in refs], len(refs)
            kw["size"] = size
        else:  # text
            kw["size"] = size
        api_mode = {"text": "t2va", "first_last": "fl2va", "last": "l2va", "reference": "ref2va"}[mode]
        raw = await asyncio.to_thread(h3_modes.make_clip, api_mode, _wrap(api_mode, prompt, seconds, n_refs), **kw)  # blocking: polls ComfyUI
        dest.write_bytes(raw)

    ok = await asyncio.to_thread(pipeline.extract_tail_frame, dest, input_dir / tail_name)
    return dest, (tail_name if ok else None)
