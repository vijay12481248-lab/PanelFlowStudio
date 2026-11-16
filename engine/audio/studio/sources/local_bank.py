"""Local audio provider: search user-supplied sound library and import custom audio files."""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import List

from engine.audio.studio.plan import Candidate, Cue, Provenance, SoundPlan
from engine.audio.studio.sources.base import Availability
from engine.config.settings import settings

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a"}


def _match_score(query: str, filename: str) -> float:
    """Token-overlap match score between cue intent and file stem (splitting on non-alphanumeric)."""
    q_tokens = set(re.findall(r"[a-zA-Z0-9]+", query.lower()))
    f_tokens = set(re.findall(r"[a-zA-Z0-9]+", filename.lower()))
    if not q_tokens or not f_tokens:
        return 0.0
    overlap = len(q_tokens & f_tokens)
    return overlap / len(q_tokens)


class LocalBankProvider:
    name = "local"

    def __init__(self, library_dir: Path | None = None):
        self.library_dir = Path(library_dir) if library_dir else (settings.app_data_dir / "audio_studio" / "user_library")

    def availability(self) -> Availability:
        return Availability(True)

    def scan_library(self) -> List[Path]:
        """List all valid audio files in user library."""
        if not self.library_dir.exists():
            return []
        files = []
        for p in self.library_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS:
                files.append(p)
        return files

    def find(self, cue: Cue, out_dir: Path, plan: SoundPlan, limit: int = 3) -> list[Candidate]:
        """Search user library for matching sounds by intent or kind."""
        query = (cue.intent or cue.kind).strip()
        if not query:
            return []
        files = self.scan_library()
        if not files:
            return []

        scored = []
        for f in files:
            score = _match_score(query, f.stem)
            if score > 0:
                scored.append((score, f))

        scored.sort(key=lambda x: x[0], reverse=True)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        cands = []
        for _, src in scored[:limit]:
            cid = uuid.uuid4().hex[:10]
            dst = out_dir / f"{cue.id}_local_{cid}{src.suffix.lower()}"
            shutil.copyfile(src, dst)
            cands.append(
                Candidate(
                    id=cid,
                    path=str(dst),
                    provider=self.name,
                    label=src.stem.replace("_", " ").title(),
                    provenance=Provenance(
                        source="local_library",
                        licence="User-Supplied",
                        author="Local User",
                        url=str(src)
                    )
                )
            )
        return cands

    def import_take(self, file_path: Path, cue: Cue, out_dir: Path, label: str = "") -> Candidate:
        """Import a specific local file as a candidate take for the given cue."""
        src = Path(file_path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"audio file not found: {file_path}")
        if src.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError(f"unsupported audio file format: {src.suffix}")

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        cid = uuid.uuid4().hex[:10]
        dst = out_dir / f"{cue.id}_import_{cid}{src.suffix.lower()}"
        shutil.copyfile(src, dst)

        return Candidate(
            id=cid,
            path=str(dst),
            provider=self.name,
            label=label or src.stem.replace("_", " ").title(),
            provenance=Provenance(
                source="user_import",
                licence="User-Supplied",
                author="Local User",
                url=str(src)
            )
        )
