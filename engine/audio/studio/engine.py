"""AudioEngine: the one place that asks sound sources for candidates, measures them and records the choice."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from engine.audio.studio.measure import measure_take
from engine.audio.studio.plan import Candidate, Cue, PlanStore, SoundPlan, Take
from engine.audio.studio.sources.base import Availability, Provider


def _measured(c: Candidate) -> Candidate:
    m = measure_take(c.path)
    return c.model_copy(update=dict(onset_s=m.onset_s, peak_s=m.peak_s, duration_s=m.duration_s, peak_db=m.peak_db,
                                    rms_db=m.rms_db, clipped_samples=m.clipped_samples))


def _to_take(c: Candidate) -> Take:
    return Take(**{k: v for k, v in c.model_dump().items() if k in Take.model_fields})


def _key(c: Candidate | Take) -> str:
    p = c.provenance
    return p.url or f"{p.source}:{p.seed if p.seed is not None else c.id}"


def _auto_choice(cue: Cue, cands: list[Candidate], used: set[str] = frozenset()) -> Candidate:
    usable = [c for c in cands if c.peak_db > -30]
    clean = [c for c in usable if c.clipped_samples == 0] or usable or cands
    clean = [c for c in clean if _key(c) not in used] or clean  # a different clip than the other cues use, when there is one
    if cue.kind == "music":
        return clean[0]
    if cue.t_out is not None and cue.track == "ambience":  # a bed: closest to the span it must fill
        span = cue.t_out - cue.t_in
        return min(clean, key=lambda c: abs(c.duration_s - span))
    return min(clean, key=lambda c: c.duration_s)


class AudioEngine:
    def __init__(self, store: PlanStore, providers: list[Provider]):
        self.store, self.providers = store, providers

    def create_plan(
        self,
        video_path: Path | str,
        fps: float = 24.0,
        duration: float = 10.0,
        mode: Literal["auto", "ask"] = "auto",
        allow_cc_by: bool = False,
        dialogue_path: Path | str | None = None,
    ) -> SoundPlan:
        from engine.chronoflow.media_tools import probe
        v = Path(video_path)
        try:
            info = probe(v)
            fps = info.get("fps", fps)
            duration = info.get("duration", duration)
            if not dialogue_path and info.get("has_audio"):
                dialogue_path = str(v)
        except Exception:
            pass
        p = self.store.create(
            str(v),
            fps=fps,
            duration=duration,
            mode=mode,
            allow_cc_by=allow_cc_by,
            dialogue_path=str(dialogue_path) if dialogue_path else None,
        )
        return self.store.save(p, "created")

    def providers_report(self) -> dict[str, Availability]:
        return {p.name: p.availability() for p in self.providers}

    def source_cue(self, plan_id: str, cue_id: str, mode: Literal["auto", "ask"] | None = None) -> SoundPlan:
        plan = self.store.load(plan_id)
        cue = plan.cue(cue_id)
        mode = mode or cue.mode or plan.mode
        limit = 1 if (mode == "auto" and cue.kind == "music") else 3
        out_dir = self.store.take_dir(plan_id)
        cands: list[Candidate] = []
        for p in self.providers:  # slow (network, GPU): done without holding the plan lock
            cands = p.find(cue, out_dir, plan, limit=limit)
            if cands:
                break
        cands = [_measured(c) for c in cands]
        reasons = [f"{p.name}: {p.availability().reason or 'no match'}" for p in self.providers]
        with self.store.lock(plan_id):  # re-read: other calls may have changed the plan meanwhile
            plan = self.store.load(plan_id)
            cue = plan.cue(cue_id)
            cue.candidates, cue.chosen_take = [], None
            if not cands:
                cue.status, cue.reason = "failed", "; ".join(reasons) if reasons else f"no provider serves kind {cue.kind!r}"
            else:
                cue.reason = None
                if mode == "ask":
                    cue.status, cue.candidates = "needs_pick", cands
                else:
                    used = {_key(t) for other in plan.cues if other.id != cue.id for t in [other.chosen()] if t}
                    chosen = _auto_choice(cue, cands, used)
                    cue.takes.append(_to_take(chosen))
                    cue.chosen_take, cue.status = chosen.id, "ready"
            return self.store.save(plan, note=f"sourced {cue_id}")

    def pick(self, plan_id: str, cue_id: str, candidate_id: str) -> SoundPlan:
        with self.store.lock(plan_id):
            plan = self.store.load(plan_id)
            cue = plan.cue(cue_id)
            chosen = next((c for c in cue.candidates if c.id == candidate_id), None)
            if chosen is None:
                raise KeyError(f"cue {cue_id!r} has no candidate {candidate_id!r}")
            cue.takes.append(_to_take(chosen))
            cue.chosen_take, cue.candidates, cue.status, cue.reason = chosen.id, [], "ready", None
            return self.store.save(plan, note=f"picked {candidate_id} for {cue_id}")
