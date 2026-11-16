"""Narration from a script: split pasted text into lines and place them on the timeline as draft narration cues."""
from __future__ import annotations

import re
from typing import Literal

from engine.audio.studio.plan import Cue, SoundPlan
from engine.audio.studio.sources.narration import estimate_seconds

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def split_script(text: str) -> list[str]:
    """Paragraphs (blank-line separated) are lines; a single paragraph is split into sentences."""
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(paras) == 1:
        return [s.strip() for s in _SENTENCE.split(paras[0]) if s.strip()]
    return paras


def place_lines(lines: list[str], *, mode: Literal["sequential", "per_cut"], start: float, gap: float, cuts: list[float], speed: float) -> list[tuple[str, float]]:
    """(line, start time) pairs. sequential: back to back from `start`. per_cut: line i starts on picture cut i, and any lines beyond the cuts follow the last one."""
    out: list[tuple[str, float]] = []
    anchors = [start] + sorted(c for c in cuts if c > start) if mode == "per_cut" else [start]
    t = start
    for i, line in enumerate(lines):
        if mode == "per_cut" and i < len(anchors):
            t = anchors[i]
        out.append((line, round(t, 3)))
        t = t + estimate_seconds(line, speed) + gap
    return out


def add_script(plan: SoundPlan, text: str, *, mode: Literal["sequential", "per_cut"] = "sequential", start: float = 0.0, gap: float = 0.4, voice: str = "", provider: str = "",
               speed: float = 1.0) -> list[Cue]:
    """Draft narration cues for the script (ids vo_NN not used yet). The caller saves them; sourcing makes the speech."""
    taken = {c.id for c in plan.cues}
    n = 0
    cues: list[Cue] = []
    for line, t_in in place_lines(split_script(text), mode=mode, start=start, gap=gap, cuts=plan.cuts, speed=speed):
        while True:
            n += 1
            cid = f"vo_{n:02d}"
            if cid not in taken:
                break
        taken.add(cid)
        cues.append(Cue(id=cid, track="dialogue", kind="narration", text=line, voice=voice, provider=provider, speed=speed, t_in=t_in, intent=line[:60]))
    return cues
