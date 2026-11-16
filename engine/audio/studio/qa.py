"""Rule checks on a Sound Plan, plus the rendered placement error (how far each hit lands from its frame)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel

from engine.audio.studio.measure import measure_take
from engine.audio.studio.plan import Cue, SoundPlan

ERROR_MS, WARN_MS = 40.0, 20.0
OVERRUN_S, MAX_WORDS_PER_SECOND = 0.15, 4.2


class Finding(BaseModel):
    cue_id: str
    rule: str
    severity: Literal["error", "warn"]
    value: float | None = None
    message: str


def _f(cue: Cue, rule: str, sev: str, msg: str, value: float | None = None) -> Finding:
    return Finding(cue_id=cue.id, rule=rule, severity=sev, value=value, message=msg)


def _narration_findings(plan: SoundPlan) -> list[Finding]:
    """A spoken line must not run into the next one or past the end of the video, and should not be rushed. Running across a picture cut is normal."""
    lines = sorted((c for c in plan.cues if c.kind == "narration" and c.chosen() is not None), key=lambda c: c.t_in)
    out: list[Finding] = []
    for i, c in enumerate(lines):
        take = c.chosen()
        end = c.t_in + take.duration_s
        if i + 1 < len(lines) and end > lines[i + 1].t_in + OVERRUN_S:
            out.append(_f(c, "narration_overrun", "error", f"this line runs {end - lines[i + 1].t_in:.1f} s into the next line ({lines[i + 1].id})", end - lines[i + 1].t_in))
        elif end > plan.duration + OVERRUN_S:
            out.append(_f(c, "narration_past_end", "error", f"this line runs {end - plan.duration:.1f} s past the end of the video", end - plan.duration))
        words = len(c.text.split())
        if take.duration_s > 0 and words / take.duration_s > MAX_WORDS_PER_SECOND:
            out.append(_f(c, "narration_too_fast", "warn", f"{words / take.duration_s:.1f} words a second is rushed; slow it down or shorten the line", words / take.duration_s))
    return out


def check_plan(plan: SoundPlan, render_cue: Callable[[SoundPlan, Cue, Path], Path]) -> list[Finding]:
    """Draft cues are skipped. Sets cue.placement_error_ms on every hit cue it could measure."""
    out: list[Finding] = []
    with tempfile.TemporaryDirectory(prefix="audiostudio-qa-") as tmp:
        for cue in plan.cues:
            if cue.status == "draft":
                continue
            take = cue.chosen()
            if take is None:
                out.append(_f(cue, "no_take", "error", f"cue is {cue.status} and has no chosen take" + (f": {cue.reason}" if cue.reason else "")))
                continue
            if take.clipped_samples > 0:
                out.append(_f(cue, "clipping", "error", f"take clips on {take.clipped_samples} samples", take.clipped_samples))
            if take.peak_db < -60:
                out.append(_f(cue, "silent", "error", f"take is silent (peak {take.peak_db:.1f} dBFS)", take.peak_db))
            elif take.peak_db > -1.0:
                out.append(_f(cue, "too_loud_take", "warn", f"take peaks at {take.peak_db:.1f} dBFS", take.peak_db))
            if cue.hit_t is None:
                continue
            if cue.hit_t > plan.duration:
                out.append(_f(cue, "beyond_video", "warn", f"hit at {cue.hit_t:.2f}s is after the video ends ({plan.duration:.2f}s)", cue.hit_t))
                continue
            m = measure_take(render_cue(plan, cue, Path(tmp) / f"{cue.id}.wav"))
            err = abs((m.peak_s if cue.anchor == "peak" else m.onset_s) - cue.hit_t) * 1000
            cue.placement_error_ms = round(err, 2)
            if err > ERROR_MS:
                out.append(_f(cue, "placement_error", "error", f"hit lands {err:.0f} ms from its frame", err))
            elif err > WARN_MS:
                out.append(_f(cue, "placement_error", "warn", f"hit lands {err:.0f} ms from its frame", err))
    out += _narration_findings(plan)
    return out
