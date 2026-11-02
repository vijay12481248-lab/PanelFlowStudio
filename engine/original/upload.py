"""Upload a finished episode to YouTube. Private by default; going public is always an explicit, confirmed choice."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from engine.original.series import SeriesStore
from engine.youtube.client import UploadMeta, YouTubeClient

MIN_LEAD = timedelta(minutes=20)  # YouTube needs a publish time safely in the future


class UploadRefused(ValueError):
    """The request is not allowed as asked (not finished, already uploaded, public without confirmation...)."""


def plan_upload(store: SeriesStore, series_id: str, number: int, made_for_kids: bool, privacy: str = "private",
                schedule: bool = False, confirm_public: bool = False, force: bool = False,
                now: datetime | None = None) -> tuple[UploadMeta, Path, Path | None]:
    ep = next((e for e in store.get(series_id).episodes if e.number == number), None)
    if ep is None:
        raise UploadRefused(f"episode {number} does not exist")
    if ep.status != "done" or not ep.video or not Path(ep.video).exists():
        raise UploadRefused(f"episode {number} is not finished (status {ep.status})")
    if ep.youtube_id and not force:
        raise UploadRefused(f"episode {number} is already on YouTube ({ep.youtube_url}); pass force to upload again")
    if ep.upload_status == "uploading" and not force:
        raise UploadRefused(f"episode {number} is already being uploaded")
    pkg_file = Path(ep.workspace) / "youtube_package.json"
    if not pkg_file.exists():
        raise UploadRefused("the episode has no YouTube package")
    pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
    publish_at = None
    if schedule:
        if not confirm_public:
            raise UploadRefused("a scheduled release will make the video public: set confirm_public to proceed")
        if not ep.publish_at:
            raise UploadRefused("the episode has no publish slot")
        publish_at = datetime.fromisoformat(ep.publish_at).astimezone()  # slots are stored as local time
        if publish_at - (now or datetime.now().astimezone()) < MIN_LEAD:
            raise UploadRefused(f"the publish slot {ep.publish_at} is in the past or less than 20 minutes away")
        privacy = "private"
    elif privacy == "public" and not confirm_public:
        raise UploadRefused("going public needs confirm_public")
    meta = UploadMeta(title=pkg["title"], description=pkg["description"], tags=pkg.get("tags", []), privacy=privacy,
                      made_for_kids=made_for_kids, publish_at=publish_at)
    thumb = Path(pkg["thumbnail_path"]) if pkg.get("thumbnail_path") and Path(pkg["thumbnail_path"]).exists() else None
    return meta, Path(ep.video), thumb


def upload_episode(store: SeriesStore, series_id: str, number: int, yt: YouTubeClient, **plan_kwargs) -> dict:
    meta, video, thumb = plan_upload(store, series_id, number, **plan_kwargs)
    ep = next(e for e in store.get(series_id).episodes if e.number == number)
    store.update_episode(series_id, ep.model_copy(update={"upload_status": "uploading", "upload_error": ""}))
    try:
        res = yt.upload(video, meta)
        warn = ""
        if thumb is not None:
            try:
                yt.set_thumbnail(res["id"], thumb)
            except Exception as e:  # the video is already up; a missing custom thumbnail must not undo that
                warn = f"thumbnail not set: {e}"
        ep = ep.model_copy(update={"upload_status": "uploaded", "upload_error": warn, "youtube_id": res["id"],
                                   "youtube_url": res["url"], "youtube_privacy": "scheduled" if res.get("publish_at") else res["privacy"],
                                   "uploaded_at": datetime.now().astimezone().isoformat()})
        store.update_episode(series_id, ep)
        return {**res, "warning": warn}
    except BaseException as e:
        store.update_episode(series_id, ep.model_copy(update={"upload_status": "failed", "upload_error": str(e)[:300]}))
        raise
