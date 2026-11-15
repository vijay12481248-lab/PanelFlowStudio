"""Rule checks on a Sound Plan, plus the rendered placement error (how far each hit lands from its frame)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel

from engine.audio.studio.measure import measure_take
from engine.audio.studio.plan import Cue, SoundPlan

ERROR_MS, WARN_MS = 40.0, 20.0


class Finding(BaseModel):
    cue_id: str
    rule: str
    severity: Literal["error", "warn"]
    value: float | None = None
    message: str


def _f(cue: Cue, rule: str, sev: str, msg: str, value: float | None = None) -> Finding:
    return Finding(cue_id=cue.id, rule=rule, severity=sev, value=value, message=msg)


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
    return out
