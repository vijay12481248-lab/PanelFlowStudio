"""The Sound Plan (cue sheet): the one document the UI, REST and MCP all read and write."""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from engine.config.settings import settings

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
Role = Literal["dialogue", "music", "sfx", "ambience", "foley"]


def snap(t: float, fps: float) -> float:
    """Nearest frame time."""
    return round(t * fps) / fps


class Provenance(BaseModel):
    source: str
    licence: str
    url: str | None = None
    model: str | None = None
    seed: int | None = None
    author: str | None = None


class Take(BaseModel):
    id: str
    path: str
    provenance: Provenance
    label: str = ""
    onset_s: float = 0.0
    peak_s: float = 0.0
    duration_s: float = 0.0
    peak_db: float = -120.0
    rms_db: float = -120.0
    clipped_samples: int = 0


class Candidate(Take):
    """A take offered for the owner or the engine to pick; the file already exists."""
    provider: str = ""
    label: str = ""


class Cue(BaseModel):
    id: str
    track: Role
    kind: str
    intent: str = ""
    t_in: float = 0.0
    t_out: float | None = None
    hit_t: float | None = None
    anchor: Literal["onset", "peak"] = "onset"
    mode: Literal["auto", "ask"] | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    takes: list[Take] = Field(default_factory=list)
    chosen_take: str | None = None
    gain_db: float = 0.0
    pan: float = 0.0  # -1.0 (left) to 1.0 (right)
    pitch_semitones: float = 0.0  # -12.0 to 12.0 semitones
    hpf_hz: float | None = None  # high-pass filter cutoff in Hz (e.g. 80.0)
    lpf_hz: float | None = None  # low-pass filter cutoff in Hz (e.g. 6000.0)
    fade_in: float = 0.0
    fade_out: float = 0.0
    hints: dict = Field(default_factory=dict)  # optional music hints: bpm, key_scale
    status: Literal["draft", "needs_pick", "ready", "failed"] = "draft"
    reason: str | None = None
    placement_error_ms: float | None = None

    def chosen(self) -> Take | None:
        return next((t for t in self.takes if t.id == self.chosen_take), None)


class Track(BaseModel):
    id: Role
    role: Role
    gain_db: float = 0.0
    duck_under: str | None = None
    ducking_depth_db: float | None = None  # e.g. -8.0 dB
    ducking_attack_ms: int | None = None  # e.g. 20 ms
    ducking_release_ms: int | None = None  # e.g. 300 ms
    pan: float = 0.0  # -1.0 to 1.0
    hpf_hz: float | None = None  # e.g. 80.0 Hz for dialogue low-cut
    mute: bool = False
    solo: bool = False


class SoundPlan(BaseModel):
    id: str
    video_path: str
    fps: float
    duration: float
    dialogue_path: str | None = None
    mode: Literal["auto", "ask"] = "auto"
    allow_cc_by: bool = False
    tracks: list[Track] = Field(default_factory=list)
    cues: list[Cue] = Field(default_factory=list)
    version: int = 0
    note: str = ""

    def cue(self, cue_id: str) -> Cue:
        for c in self.cues:
            if c.id == cue_id:
                return c
        raise KeyError(f"no cue {cue_id!r} in plan {self.id}")


def check_id(value: str) -> str:
    if not isinstance(value, str) or not _ID.match(value):
        raise ValueError("ids may only contain letters, digits, '-' and '_' (max 64)")
    return value


class PlanStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else settings.app_data_dir / "audio_studio" / "plans"
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def lock(self, plan_id: str) -> threading.RLock:
        """Hold it around load-modify-save so parallel REST/MCP calls on one plan do not overwrite each other."""
        with self._guard:
            return self._locks.setdefault(check_id(plan_id), threading.RLock())

    def _dir(self, plan_id: str) -> Path:
        return self.root / check_id(plan_id)

    def plan_dir(self, plan_id: str) -> Path:
        return self._dir(plan_id)

    def take_dir(self, plan_id: str) -> Path:
        d = self._dir(plan_id) / "takes"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create(self, video_path: str, fps: float, duration: float, **kw) -> SoundPlan:
        tracks = [Track(id=r, role=r, duck_under="dialogue" if r == "music" else None)
                  for r in ("dialogue", "music", "sfx", "ambience", "foley")]
        plan = SoundPlan(id=kw.pop("id", "ap_" + secrets.token_hex(4)), video_path=str(video_path), fps=fps,
                         duration=duration, tracks=tracks, **kw)
        self._dir(plan.id).mkdir(parents=True, exist_ok=True)
        return plan

    def load(self, plan_id: str) -> SoundPlan:
        p = self._dir(plan_id) / "plan.json"
        if not p.is_file():
            raise FileNotFoundError(f"no sound plan {plan_id!r}")
        return SoundPlan.model_validate_json(p.read_text(encoding="utf-8"))

    def save(self, plan: SoundPlan, note: str = "") -> SoundPlan:
        saved = plan.model_copy(update={"version": plan.version + 1, "note": note or plan.note})
        d = self._dir(saved.id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"plan.json.{secrets.token_hex(4)}.tmp"
        tmp.write_text(saved.model_dump_json(indent=1), encoding="utf-8")
        for attempt in range(5):  # Windows refuses to replace a file another process holds open
            try:
                tmp.replace(d / "plan.json")
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.1)
        return saved
