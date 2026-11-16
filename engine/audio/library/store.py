"""The sound library: one folder per sound with sound.json and one WAV per version (48 kHz float, so repeated edits lose nothing).

Edits write a new version; undo/redo move `current`; an edit after an undo drops the versions after it (as in every editor).
Delete marks the sound trashed (restorable); emptying the trash removes the folders.
"""
from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
from pydantic import BaseModel, Field

from engine.audio.library import ops
from engine.audio.studio.plan import Provenance, check_id
from engine.audio.studio.peaks import file_peaks
from engine.config.settings import settings

Kind = Literal["voice", "music", "effect"]
SR = ops.SR


class Version(BaseModel):
    n: int
    file: str
    op: str
    params: dict = Field(default_factory=dict)
    a: float | None = None
    b: float | None = None
    created: str
    duration_s: float
    peak_db: float
    channels: int = 1


class Sound(BaseModel):
    id: str
    name: str
    kind: Kind
    created: str
    provenance: Provenance
    versions: list[Version] = Field(default_factory=list)
    current: int = 1
    trashed: bool = False
    info: dict = Field(default_factory=dict)   # how it was made: text/voice/speed, music description, effect kind

    def version(self, n: int | None = None) -> Version:
        n = self.current if n is None else n
        for v in self.versions:
            if v.n == n:
                return v
        raise KeyError(f"sound {self.id} has no version {n}")

    @property
    def duration_s(self) -> float:
        return self.version().duration_s


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def decode(path: Path) -> np.ndarray:
    """Any file ffmpeg reads (audio, or the sound track of a video) as float32 (n, channels <= 2) at 48 kHz."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"file not found: {path}")
    with tempfile.TemporaryDirectory(prefix="pf-audio-in-") as tmp:
        wav = Path(tmp) / "x.wav"
        p = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", str(path), "-vn", "-ar", str(SR), "-c:a", "pcm_f32le", str(wav)],
                           capture_output=True, text=True, timeout=600)
        if p.returncode != 0 or not wav.is_file():
            raise ValueError(f"cannot read sound from {path.name}: {p.stderr.strip()[-200:] or 'no audio stream'}")
        x, _ = sf.read(str(wav), dtype="float32", always_2d=True)
    if x.shape[1] > 2:
        x = x[:, :2]
    if not len(x):
        raise ValueError(f"{path.name} has no sound")
    return x


class SoundStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else settings.app_data_dir / "audio_library"
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def lock(self, sid: str) -> threading.RLock:
        with self._guard:
            return self._locks.setdefault(check_id(sid), threading.RLock())

    def dir(self, sid: str) -> Path:
        return self.root / check_id(sid)

    def file(self, sid: str, n: int | None = None) -> Path:
        s = self.load(sid)
        return self.dir(sid) / s.version(n).file

    def load(self, sid: str) -> Sound:
        p = self.dir(sid) / "sound.json"
        if not p.is_file():
            raise FileNotFoundError(f"no sound {sid!r}")
        return Sound.model_validate_json(p.read_text(encoding="utf-8"))

    def save(self, s: Sound) -> Sound:
        d = self.dir(s.id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"sound.json.{secrets.token_hex(4)}.tmp"
        tmp.write_text(s.model_dump_json(indent=1), encoding="utf-8")
        for attempt in range(5):   # Windows refuses to replace a file another process holds open
            try:
                tmp.replace(d / "sound.json")
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.1)
        return s

    def list(self, kind: str | None = None, q: str = "", trash: bool = False) -> list[Sound]:
        out = []
        for p in self.root.glob("*/sound.json") if self.root.is_dir() else []:
            try:
                s = Sound.model_validate_json(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue   # a half-written file must not hide the others
            if s.trashed != trash or (kind and s.kind != kind) or (q and q.lower() not in s.name.lower()):
                continue
            out.append(s)
        return sorted(out, key=lambda s: s.created, reverse=True)

    def _write(self, d: Path, n: int, x: np.ndarray, op: str, params: dict, a=None, b=None) -> Version:
        if not len(x):
            raise ValueError("the result would be empty")
        name = f"v{n:03d}.wav"
        sf.write(str(d / name), x, SR, subtype="FLOAT")
        peak = float(np.abs(x).max())
        return Version(n=n, file=name, op=op, params=params, a=a, b=b, created=_now(), duration_s=round(len(x) / SR, 4),
                       peak_db=round(20 * np.log10(max(peak, 1e-6)), 2), channels=int(x.shape[1]))

    def create(self, samples: np.ndarray, name: str, kind: Kind, provenance: Provenance, info: dict | None = None, op: str = "created") -> Sound:
        sid = "snd_" + secrets.token_hex(5)
        d = self.dir(sid)
        d.mkdir(parents=True, exist_ok=True)
        x = np.asarray(samples, dtype=np.float32)
        x = x[:, None] if x.ndim == 1 else x
        v = self._write(d, 1, x, op, {})
        s = Sound(id=sid, name=(name or "Untitled").strip()[:120], kind=kind, created=_now(), provenance=provenance, versions=[v], current=1, info=info or {})
        return self.save(s)

    def create_from_file(self, path: Path, name: str, kind: Kind, provenance: Provenance, info: dict | None = None, op: str = "created") -> Sound:
        return self.create(decode(path), name, kind, provenance, info, op)

    def read(self, sid: str, n: int | None = None) -> np.ndarray:
        x, _ = sf.read(str(self.file(sid, n)), dtype="float32", always_2d=True)
        return x

    def _push(self, s: Sound, x: np.ndarray, op: str, params: dict, a=None, b=None) -> Sound:
        d = self.dir(s.id)
        for v in [v for v in s.versions if v.n > s.current]:   # an edit after an undo drops the redo branch
            (d / v.file).unlink(missing_ok=True)
        s.versions = [v for v in s.versions if v.n <= s.current]
        n = max(v.n for v in s.versions) + 1
        s.versions.append(self._write(d, n, x, op, params, a, b))
        s.current = n
        return self.save(s)

    def edit(self, sid: str, op: str, params: dict | None = None, a: float | None = None, b: float | None = None) -> Sound:
        with self.lock(sid):
            s = self.load(sid)
            p = ops.clean_params(op, params)
            y = ops.apply(op, self.read(sid), SR, p, a, b)
            return self._push(s, y, op, p, a, b)

    def undo(self, sid: str) -> Sound:
        with self.lock(sid):
            s = self.load(sid)
            older = [v.n for v in s.versions if v.n < s.current]
            if not older:
                raise ValueError("nothing to undo")
            s.current = max(older)
            return self.save(s)

    def redo(self, sid: str) -> Sound:
        with self.lock(sid):
            s = self.load(sid)
            newer = [v.n for v in s.versions if v.n > s.current]
            if not newer:
                raise ValueError("nothing to redo")
            s.current = min(newer)
            return self.save(s)

    def set_current(self, sid: str, n: int) -> Sound:
        with self.lock(sid):
            s = self.load(sid)
            s.version(n)
            s.current = n
            return self.save(s)

    def update(self, sid: str, name: str | None = None, kind: Kind | None = None) -> Sound:
        with self.lock(sid):
            s = self.load(sid)
            if name is not None:
                if not name.strip():
                    raise ValueError("a sound needs a name")
                s.name = name.strip()[:120]
            if kind is not None:
                s.kind = kind
            return self.save(s)

    def trash(self, sid: str, trashed: bool = True) -> Sound:
        with self.lock(sid):
            s = self.load(sid)
            s.trashed = trashed
            return self.save(s)

    def empty_trash(self) -> list[str]:
        gone = []
        for s in self.list(trash=True):
            with self.lock(s.id):
                shutil.rmtree(self.dir(s.id), ignore_errors=True)
                gone.append(s.id)
        return gone

    def split(self, sid: str, at: float) -> tuple[Sound, Sound]:
        """The sound keeps the part before `at` (as a new version); the part after becomes a new sound."""
        with self.lock(sid):
            s = self.load(sid)
            x = self.read(sid)
            i = int(round(at * SR))
            if not (0 < i < len(x)):
                raise ValueError("split inside the sound, not at its ends")
            tail = self.create(x[i:], f"{s.name} (2)", s.kind, s.provenance, dict(s.info), op=f"split from {s.id}")
            return self._push(s, x[:i].copy(), "split", {"at": round(at, 4)}), tail

    def duplicate(self, sid: str) -> Sound:
        s = self.load(sid)
        return self.create(self.read(sid), f"{s.name} copy", s.kind, s.provenance, dict(s.info), op=f"copy of {s.id}")

    def join(self, sid: str, other: str) -> Sound:
        """Append the other sound's current version to this one."""
        if check_id(sid) == check_id(other):
            raise ValueError("pick a different sound to join")
        y = self.read(other)
        with self.lock(sid):
            s = self.load(sid)
            x = self.read(sid)
            ch = max(x.shape[1], y.shape[1])
            x, y = (np.repeat(z, ch, axis=1) if z.shape[1] < ch else z for z in (x, y))
            return self._push(s, ops.join([x, y], SR), "join", {"other": other})

    def peaks(self, sid: str, n: int | None = None, bins: int = 1200) -> dict:
        s = self.load(sid)
        v = s.version(n)
        bins = max(50, min(int(bins), 8000))
        cache = self.dir(sid) / "peaks" / f"{Path(v.file).stem}_{bins}.json"
        if cache.is_file():
            return json.loads(cache.read_text(encoding="utf-8"))
        pk, dur = file_peaks(self.dir(sid) / v.file, bins)
        out = {"peaks": pk, "duration": round(dur, 4), "version": v.n}
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out
