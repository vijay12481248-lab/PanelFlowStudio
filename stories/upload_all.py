"""Upload the finished batch videos (full + Shorts) to the connected YouTube channel as PRIVATE, resumable and idempotent.

    python stories/upload_all.py            # uploads everything not yet uploaded, stops at the daily API quota
    python stories/upload_all.py --list     # shows the state

Results are kept in output/Original_Stories/_batch/uploads.json ({slug: {id, url, privacy, thumbnail}}). Privacy is always private;
made_for_kids is the owner's declaration (answered in chat: not made for kids). Public/scheduled release is never done here."""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.youtube.auth import YouTubeAuth  # noqa: E402
from engine.youtube.client import UploadMeta, YouTubeClient, YouTubeError  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "output" / "Original_Stories"
STATE = ROOT / "_batch" / "uploads.json"
MADE_FOR_KIDS = False  # owner's declaration, 2026-11-08
EXTRA_FULL = ["vox_why_we_cry"]  # the first video of the channel run, not part of the 25-video batch


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


def items() -> list[str]:
    ex = [p.parent.name for p in ROOT.glob("vox_*/story_1080p.mp4")]
    full = [s for s in sorted(ex) if not s.endswith("_short") and (ROOT / s / "approved.flag").exists() or s in EXTRA_FULL]
    full = [s for s in dict.fromkeys(EXTRA_FULL + full) if (ROOT / s / "youtube_package.json").exists() and (ROOT / s / "story_1080p.mp4").exists()]
    shorts = sorted(s for s in ex if s.endswith("_short"))
    return full + shorts


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    todo = items()
    if "--list" in sys.argv:
        for s in todo:
            print(s, state.get(s, {}).get("url", "-"))
        return
    yt = YouTubeClient(YouTubeAuth())
    for slug in todo:
        if slug in state:
            continue
        ws = ROOT / slug
        pkg = json.loads((ws / "youtube_package.json").read_text(encoding="utf-8"))
        video = ws / "story_1080p.mp4"
        meta = UploadMeta(title=pkg["title"], description=clean_description(pkg["description"], duration(video)), tags=pkg.get("tags", []),
                          privacy="private", made_for_kids=MADE_FOR_KIDS)
        try:
            res = yt.upload(video, meta)
        except YouTubeError as e:
            print(f"STOP at {slug}: {e}")
            break
        thumb = Path(pkg["thumbnail_path"]) if not slug.endswith("_short") and pkg.get("thumbnail_path") and Path(pkg["thumbnail_path"]).exists() else None
        note = "-"
        if thumb:
            try:
                yt.set_thumbnail(res["id"], thumb)
                note = "thumbnail set"
            except Exception as e:  # the video is up; report instead of undoing it
                note = f"thumbnail NOT set: {e}"[:200]
        state[slug] = {"id": res["id"], "url": res["url"], "privacy": res["privacy"], "thumbnail": note, "title": meta.title}
        STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")  # saved after every video so a crash loses nothing
        print(slug, res["url"], res["privacy"], note, flush=True)


if __name__ == "__main__":
    main()
