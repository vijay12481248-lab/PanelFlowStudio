"""What every sound source (provider) looks like. The AudioEngine is the only caller of `find`."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from engine.audio.studio.plan import Candidate, Cue, SoundPlan


@dataclass(frozen=True)
class Availability:
    ok: bool
    reason: str | None = None


class Provider(Protocol):
    name: str

    def availability(self) -> Availability: ...

    def find(self, cue: Cue, out_dir: Path, plan: SoundPlan, limit: int = 3) -> list[Candidate]:
        """Candidates whose files are already written under out_dir. "No result" is []; a down provider says why in availability()."""
        ...


__all__ = ["Availability", "Provider", "Candidate"]
