"""Openverse audio search: free recordings (Freesound, Wikimedia, Jamendo) filtered by licence, with hard download caps."""
from __future__ import annotations

import json
import re
import urllib.parse
import uuid
import urllib.request
from pathlib import Path
from typing import Callable

from engine.audio.studio.licence import licence_allowed
from engine.audio.studio.plan import Candidate, Cue, Provenance, SoundPlan
from engine.audio.studio.sources.base import Availability

API = "https://api.openverse.org/v1/audio/"
MAX_BYTES = 5 * 1024 * 1024
MAX_SFX_MS = 60_000
_UA = "audio-studio/1.0"


def _default_get(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(MAX_BYTES + 1), r.headers.get("Content-Type", "")


class OpenverseProvider:
    name = "openverse"

    def __init__(self, http_get: Callable[[str], tuple[bytes, str]] | None = None):
        self._get = http_get or _default_get
        self._error: str | None = None

    def availability(self) -> Availability:
        return Availability(self._error is None, self._error)

    def find(self, cue: Cue, out_dir: Path, plan: SoundPlan, limit: int = 3) -> list[Candidate]:
        if cue.kind in ("music", "narration"):   # music and spoken lines are never library searches
            return []
        q = {"q": cue.intent or cue.kind, "page_size": 10, "license_type": "commercial"}
        if not plan.allow_cc_by:
            q["license"] = "cc0"
        try:
            body, _ = self._get(f"{API}?{urllib.parse.urlencode(q)}")
            results = json.loads(body).get("results", [])
        except (OSError, ValueError) as e:
            self._error = f"Openverse unreachable: {e}"
            return []
        self._error = None
        out_dir = Path(out_dir)
        cands: list[Candidate] = []
        for r in results:
            if len(cands) >= limit:
                break
            lic = f"{r.get('license', '')} {r.get('license_version') or ''}".strip()
            if not licence_allowed(lic, plan.allow_cc_by):
                continue
            if cue.track != "ambience" and (r.get("duration") or 0) > MAX_SFX_MS:
                continue
            try:
                data, ctype = self._get(r["url"])
            except (OSError, KeyError) as e:
                self._error = f"Openverse download failed: {e}"
                continue
            if len(data) > MAX_BYTES or not str(ctype).lower().startswith("audio/"):
                continue
            rid = re.sub(r"[^A-Za-z0-9_-]", "", str(r.get("id", "")))[:12] or uuid.uuid4().hex[:10]
            ext = re.sub(r"[^A-Za-z0-9.]", "", Path(urllib.parse.urlparse(r["url"]).path).suffix) or ".mp3"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{cue.id}_ov_{rid[:8]}{ext}"
            path.write_bytes(data)
            cands.append(Candidate(id=rid, path=str(path), provider=self.name, label=str(r.get("title", "")),
                                   provenance=Provenance(source=f"openverse/{r.get('source', 'unknown')}", licence=lic.upper(),
                                                         url=r.get("foreign_landing_url"), author=r.get("creator"))))
        return cands
