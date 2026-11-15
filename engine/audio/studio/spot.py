"""Spotting: find where the picture changes and draft the cues that belong there."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from engine.audio.studio.plan import Cue, SoundPlan, snap

_PTS = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def detect_cuts(video: Path, threshold: float = 0.3) -> list[float]:
    """Scene-change times (seconds) from ffmpeg's scene score; cuts closer than 0.15 s count once."""
    proc = subprocess.run(
        [shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-i", str(video), "-an",
         "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg scene detection failed: {proc.stderr.strip().splitlines()[-1:]}")
    cuts: list[float] = []
    for t in sorted(float(m) for m in _PTS.findall(proc.stderr)):
        if not cuts or t - cuts[-1] >= 0.15:
            cuts.append(t)
    return cuts


def draft_cues(plan: SoundPlan, cuts: list[float]) -> list[Cue]:
    """One transition whoosh per cut (its swell peaks on the cut) and one underscore for the whole video.
    Intents are placeholders: the agent or the owner rewrites them before sourcing."""
    cues = []
    for t in cuts:
        if not 0 < t <= plan.duration:
            continue
        hit = min(snap(t, plan.fps), plan.duration)
        cues.append(Cue(id=f"cut_{len(cues) + 1:02d}", track="sfx", kind="whoosh", anchor="peak", hit_t=hit,
                        t_in=max(0.0, hit - 0.5), intent=f"transition whoosh into the cut at {hit:.2f}s"))
    cues.append(Cue(id="music_1", track="music", kind="music", t_in=0.0, t_out=plan.duration, intent="instrumental underscore"))
    return cues
