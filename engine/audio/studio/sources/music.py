"""Music cues through the local ACE-Step 1.5 server (MIT). One GPU audio job at a time."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, Callable

from engine.audio.studio.plan import Candidate, Cue, Provenance, SoundPlan
from engine.audio.studio.sources.base import Availability

_ONE_AT_A_TIME = threading.Lock()


class ResourceSlot:
    """The engine's GPU admission (SystemResourceManager), callable from sync code."""

    def __init__(self):
        from engine.system.resources import SystemResourceManager
        self._rm = SystemResourceManager()

    def acquire(self, job_id: str) -> bool:
        return asyncio.run(self._rm.acquire_gpu_slot(job_id, required_vram_mb=0.0))

    def release(self, job_id: str) -> None:
        asyncio.run(self._rm.release_gpu_slot(job_id))


class MusicProvider:
    name = "ace-step"

    def __init__(self, generator: Callable[..., Any] | None = None, slot: Any = None, health: Callable[[], dict] | None = None):
        self._generator, self._slot, self._health = generator, slot, health
        self._error: str | None = None

    def _deps(self):
        from engine.audio.providers.ace_step import local_music_provider as p
        return (self._generator or p.generate_music_take, self._slot or ResourceSlot(),
                self._health or (lambda: p.check_health(timeout=2.0)))

    def availability(self) -> Availability:
        return Availability(self._error is None, self._error)

    def find(self, cue: Cue, out_dir: Path, plan: SoundPlan, limit: int = 1) -> list[Candidate]:
        if cue.kind != "music":
            return []
        generate, slot, health = self._deps()
        h = health()
        if not h.get("available"):
            self._error = f"ACE-Step is not reachable: {h.get('error') or h.get('detail') or 'health check failed'}"
            return []
        if not _ONE_AT_A_TIME.acquire(blocking=False):
            self._error = "GPU busy: another audio job is running"
            return []
        job_id = f"job_audiostudio_{cue.id}"
        try:
            if not slot.acquire(job_id):
                self._error = "GPU busy: the resource manager has no free slot"
                return []
            try:
                dur = float((cue.t_out if cue.t_out is not None else plan.duration) - cue.t_in)
                out_dir = Path(out_dir)
                out_dir.mkdir(parents=True, exist_ok=True)
                kw = {k: cue.hints[k] for k in ("bpm", "key_scale") if k in cue.hints}
                cands = []
                for i in range(1, limit + 1):
                    take = generate(project_id=plan.id, cue_id=cue.id, workspace_music_dir=out_dir, prompt=cue.intent,
                                    audio_duration=dur, take_index=i, **kw)
                    cands.append(Candidate(id=take.take_id, path=take.audio_file_path, provider=self.name, label=f"music take {i}",
                                           provenance=Provenance(source="ace-step", licence="MIT", model=take.model_id, seed=take.seed)))
                self._error = None
                return cands
            except Exception as e:  # a failed generation is reported, never replaced by another sound
                self._error = f"ACE-Step generation failed: {e}"
                return []
            finally:
                slot.release(job_id)
        finally:
            _ONE_AT_A_TIME.release()
