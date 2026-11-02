"""YouTube Data API v3 uploads: resumable video upload, custom thumbnail, metadata validation.

Safety defaults: a video is uploaded PRIVATE unless the caller explicitly asks for something else; a scheduled release is a
private upload with `publishAt`. Whether to go public is always a deliberate, separate decision made by the caller.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx
from pydantic import BaseModel, Field, field_validator

from engine.youtube.auth import AuthError, YouTubeAuth

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
CHUNK = 8 * 1024 * 1024  # must be a multiple of 256 KiB
MAX_FAILURES = 6
MAX_THUMB_BYTES = 2 * 1024 * 1024
PRIVACY = {"private", "unlisted", "public"}


class YouTubeError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, reason: str = ""):
        super().__init__(message)
        self.status, self.reason = status, reason


class UploadMeta(BaseModel):
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    category_id: str = "1"  # Film & Animation
    privacy: str = "private"
    made_for_kids: bool  # no default on purpose: it is a legal declaration the channel owner must make
    synthetic: bool = True  # "altered or synthetic content" disclosure
    publish_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v) <= 100 or "<" in v or ">" in v:
            raise ValueError("title must be 1-100 characters without < or >")
        return v

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 5000 or "<" in v or ">" in v:
            raise ValueError("description must be at most 5000 bytes without < or >")
        return v

    @field_validator("privacy")
    @classmethod
    def _privacy(cls, v: str) -> str:
        if v not in PRIVACY:
            raise ValueError(f"privacy must be one of {sorted(PRIVACY)}")
        return v

    def body(self) -> dict:
        status: dict = {"privacyStatus": self.privacy, "selfDeclaredMadeForKids": self.made_for_kids,
                        "containsSyntheticMedia": self.synthetic}
        if self.publish_at is not None:
            if self.privacy != "private":
                raise ValueError("a scheduled release needs privacy 'private' until the publish time")
            if self.publish_at.tzinfo is None:
                raise ValueError("publish_at must include a time zone")
            status["publishAt"] = self.publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"snippet": {"title": self.title, "description": self.description, "tags": fit_tags(self.tags),
                            "categoryId": self.category_id}, "status": status}


def fit_tags(tags: list[str], limit: int = 500) -> list[str]:
    """YouTube allows about 500 characters of tags in total (quoted when they contain spaces); keep what fits, in order."""
    out, used = [], 0
    for t in dict.fromkeys(x.strip() for x in tags if x.strip()):
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)
        if used + cost > limit:
            break
        out.append(t)
        used += cost
    return out


class YouTubeClient:
    def __init__(self, auth: YouTubeAuth, http: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep):
        self.auth = auth
        self.http = http or httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0))
        self.sleep = sleep

    def _headers(self, extra: dict | None = None) -> dict:
        return {"Authorization": f"Bearer {self.auth.access_token()}", **(extra or {})}

    @staticmethod
    def _error(r: httpx.Response) -> YouTubeError:
        try:
            e = r.json()["error"]
            reason = (e.get("errors") or [{}])[0].get("reason", "")
            msg = e.get("message", r.text[:200])
        except Exception:
            reason, msg = "", r.text[:200]
        hint = {"quotaExceeded": " (daily API quota used up; it resets at midnight Pacific)",
                "uploadLimitExceeded": " (the channel hit its daily upload limit)",
                "forbidden": " (check that the YouTube Data API is enabled and the channel may upload)"}.get(reason, "")
        return YouTubeError(f"YouTube API {r.status_code}: {msg}{hint}", r.status_code, reason)

    def upload(self, video: Path, meta: UploadMeta, progress: Callable[[float], None] = lambda p: None) -> dict:
        size = video.stat().st_size
        if size == 0:
            raise ValueError("video file is empty")
        init = self.http.post(UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                              headers=self._headers({"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}),
                              json=meta.body())
        if init.status_code == 401:
            raise AuthError("YouTube rejected the access token; connect YouTube again")
        if init.status_code != 200 or "location" not in init.headers:
            raise self._error(init)
        session = init.headers["location"]
        sent, failures = 0, 0
        with video.open("rb") as f:
            while True:
                f.seek(sent)
                chunk = f.read(CHUNK)
                end = sent + len(chunk) - 1
                try:
                    r = self.http.put(session, content=chunk, headers={"Content-Range": f"bytes {sent}-{end}/{size}",
                                                                      "Content-Type": "video/mp4"})
                except httpx.HTTPError:
                    r = None
                if r is not None and r.status_code in (200, 201):
                    progress(1.0)
                    body = r.json()
                    return {"id": body["id"], "url": f"https://www.youtube.com/watch?v={body['id']}", "privacy": meta.privacy,
                            "publish_at": meta.body()["status"].get("publishAt")}
                if r is not None and r.status_code == 308:
                    failures = 0
                    sent = self._received(r)
                    progress(min(sent / size, 0.99))
                    continue
                if r is not None and r.status_code < 500 and r.status_code != 429:
                    raise self._error(r)
                failures += 1  # network error, 429 or 5xx: ask the server how much it has, then carry on
                if failures > MAX_FAILURES:
                    raise YouTubeError("upload failed after repeated errors; run it again to resume", r.status_code if r is not None else None)
                self.sleep(min(2 ** failures, 30))
                probe = None
                try:
                    probe = self.http.put(session, content=b"", headers={"Content-Range": f"bytes */{size}"})
                except httpx.HTTPError:
                    continue
                if probe.status_code in (200, 201):
                    body = probe.json()
                    return {"id": body["id"], "url": f"https://www.youtube.com/watch?v={body['id']}", "privacy": meta.privacy,
                            "publish_at": meta.body()["status"].get("publishAt")}
                if probe.status_code == 308:
                    sent = self._received(probe)

    @staticmethod
    def _received(r: httpx.Response) -> int:
        rng = r.headers.get("range", "")  # "bytes=0-1048575": the last byte the server has
        return int(rng.split("-")[-1]) + 1 if rng else 0

    def set_thumbnail(self, video_id: str, image: Path) -> None:
        data = image.read_bytes()
        if len(data) > MAX_THUMB_BYTES:
            raise ValueError("thumbnail must be 2 MB or smaller")
        r = self.http.post(THUMB_URL, params={"videoId": video_id, "uploadType": "media"}, content=data,
                           headers=self._headers({"Content-Type": "image/png" if image.suffix.lower() == ".png" else "image/jpeg"}))
        if r.status_code != 200:
            raise self._error(r)
