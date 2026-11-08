"""Uploads the finished batch to the connected YouTube channel and schedules it: one long video and its Short per day, public at the slot.

    python stories/upload_all.py            # uploads / schedules what is due, in slot order; stops at the daily upload limit
    python stories/upload_all.py --list     # the plan and its state

Every video is uploaded PRIVATE with a `publishAt` time (YouTube flips it to public then); nothing goes public early. The owner asked for
this on 2026-11-08 (1 long + 1 related Short per day, public); made_for_kids = False is also the owner's declaration.
The plan is frozen in _batch/schedule.json on the first run, results are kept in _batch/uploads.json; reruns are idempotent, so the
daily limit can be waited out by running this again (a Windows scheduled task does that)."""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.youtube.auth import YouTubeAuth  # noqa: E402
from engine.youtube.client import UploadMeta, YouTubeClient, YouTubeError  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "output" / "Original_Stories"
SPECS = Path(__file__).resolve().parent / "explainers"
STATE, PLAN, LOCK = ROOT / "_batch" / "uploads.json", ROOT / "_batch" / "schedule.json", ROOT / "_batch" / "upload.lock"
MADE_FOR_KIDS = False
FIRST_DAY = "2026-11-09"
LONG_AT, SHORT_AT = (18, 0), (20, 0)  # local time
MIN_LEAD = timedelta(minutes=30)  # YouTube needs the release time safely in the future
FIRST = ["vox_why_we_cry"]  # the channel run's first video (no Short); the rest follow in spec order, already-uploaded ones first


def duration(mp4: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)], capture_output=True, text=True)
    return float(out.stdout.strip())


def clean_description(desc: str, seconds: float) -> str:
    paras, seen = [], set()
    for p in desc.split("\n\n"):  # the hook can appear twice in a Short package
        if p.strip() and p.strip() not in seen:
            seen.add(p.strip())
            paras.append(p.strip())
    return re.sub(r"\b\d+ seconds\b", f"{round(seconds)} seconds", "\n\n".join(paras))


def make_plan(state: dict) -> list[dict]:
    slugs = [re.search(r"^slug:\s*(\S+)", p.read_text(encoding="utf-8"), re.M).group(1) for p in sorted(SPECS.glob("*.txt"))]
    rest = [s for s in slugs if s not in FIRST]
    rest.sort(key=lambda s: s not in state)  # stable: what is already on YouTube gets the earliest days
    day0 = datetime.fromisoformat(FIRST_DAY).astimezone()
    plan = []
    for i, slug in enumerate(FIRST + rest):
        d = day0 + timedelta(days=i)
        plan.append({"slug": slug, "publish_at": d.replace(hour=LONG_AT[0], minute=LONG_AT[1]).isoformat()})
        if (ROOT / f"{slug}_short" / "story_1080p.mp4").exists():
            plan.append({"slug": f"{slug}_short", "publish_at": d.replace(hour=SHORT_AT[0], minute=SHORT_AT[1]).isoformat()})
    return sorted(plan, key=lambda x: x["publish_at"])


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    if not PLAN.exists():
        PLAN.write_text(json.dumps(make_plan(state), indent=1), encoding="utf-8")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if "--list" in sys.argv:
        for it in plan:
            s = state.get(it["slug"], {})
            print(it["publish_at"][:16], it["slug"], s.get("url", "-"), "scheduled" if s.get("scheduled") else "")
        return
    if LOCK.exists() and datetime.now().timestamp() - LOCK.stat().st_mtime < 3 * 3600:
        print("another upload run is active")
        return
    LOCK.write_text("1")
    try:
        yt = YouTubeClient(YouTubeAuth())
        now = datetime.now().astimezone()
        blocked = False  # daily upload limit reached: videos already on YouTube are still scheduled, new uploads wait
        for it in plan:
            slug, when = it["slug"], datetime.fromisoformat(it["publish_at"])
            s = state.get(slug, {})
            if s.get("scheduled") == it["publish_at"]:
                continue
            if when - now < MIN_LEAD:
                print(f"SKIP {slug}: slot {it['publish_at'][:16]} is too close or past; not published early")
                continue
            if blocked and not s:
                continue
            ws = ROOT / slug
            try:
                if not s:
                    pkg = json.loads((ws / "youtube_package.json").read_text(encoding="utf-8"))
                    video = ws / "story_1080p.mp4"
                    meta = UploadMeta(title=pkg["title"], description=clean_description(pkg["description"], duration(video)), tags=pkg.get("tags", []),
                                      privacy="private", made_for_kids=MADE_FOR_KIDS, publish_at=when)
                    res = yt.upload(video, meta)
                    s = {"id": res["id"], "url": res["url"], "title": meta.title, "thumbnail": "-"}
                    thumb = Path(pkg["thumbnail_path"]) if not slug.endswith("_short") and pkg.get("thumbnail_path") else None
                    if thumb and thumb.exists():
                        try:
                            yt.set_thumbnail(res["id"], thumb)
                            s["thumbnail"] = "thumbnail set"
                        except Exception as e:  # the video is up; report instead of undoing it
                            s["thumbnail"] = f"thumbnail NOT set: {e}"[:200]
                else:
                    yt.schedule(s["id"], when, MADE_FOR_KIDS)
                s["scheduled"] = it["publish_at"]
                state[slug] = s
                STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")  # after every video, so a crash loses nothing
                print(slug, s["url"], "public at", it["publish_at"][:16], s["thumbnail"], flush=True)
            except YouTubeError as e:
                print(f"STOP at {slug}: {e}")
                if e.reason in ("uploadLimitExceeded", "quotaExceeded") or "exceeded the number of videos" in str(e):
                    blocked = True
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
