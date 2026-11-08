"""Builds output/YouTube_Upload_Kit, split in two clearly named folders, plus 00_CHECKLIST.txt:

  1_TO_UPLOAD/Day_NN_.../LONG_.. and SHORT_..   full-quality video, thumbnail.jpg (long only), title_description_tags.txt
  2_ALREADY_UPLOADED/Day_NN_.../LONG_.. SHORT_..  the same, but the video is a small 720p copy (the original is deleted once the copy is checked)

A video moves from 1 to 2 by itself on the next run after it is on YouTube and scheduled. Safe to rerun.

    python stories/build_upload_kit.py"""
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from upload_all import PLAN, ROOT, STATE, clean_description, duration  # noqa: E402

KIT = ROOT.parent / "YouTube_Upload_Kit"
TODO, DONE = KIT / "1_TO_UPLOAD", KIT / "2_ALREADY_UPLOADED"
SEP = "=" * 70


def info_text(kind: str, when: datetime, pkg: dict, desc: str, st: dict, long_url: str) -> str:
    status = (f"ALREADY ON YOUTUBE (scheduled): {st['url']}\n  -> nothing to upload; the schedule is already set." if st.get("scheduled") else
              "NOT UPLOADED YET -> upload this one")
    lines = [f"{kind} VIDEO  -  {pkg['title']}", SEP, f"STATUS      : {status}",
             f"PUBLISH AT  : {when:%A %d %B %Y, %I:%M %p} (India time)  -> in Studio: Visibility > Schedule > that date and time",
             "VISIBILITY  : Schedule (private until the time above, then public)", "AUDIENCE    : No, it's not made for kids",
             "AI CONTENT  : Yes (altered or synthetic content)", "CATEGORY    : Film & Animation", SEP, "TITLE (copy this):", pkg["title"], "", SEP,
             "DESCRIPTION (copy everything below):", "", desc, "", SEP, "TAGS (paste into the Tags box, comma separated):", ", ".join(pkg.get("tags", [])), ""]
    if kind == "LONG":
        lines += [SEP, "THUMBNAIL: upload thumbnail.jpg from this folder (Customize > Thumbnail).", ""]
    else:
        lines += [SEP, "THUMBNAIL: Shorts have none - YouTube uses a frame of the video.",
                  f"RELATED VIDEO: in Studio set 'Related video' to the long video: {long_url or '(its link after it is uploaded)'}", ""]
    return "\n".join(lines)


def compress(src: Path, dst: Path) -> None:
    """720p (or 720 wide for a Short), CRF 30: a reference copy a fraction of the size. The caller deletes `src` only after this is checked."""
    tmp = dst.with_name("tmp_" + dst.name)
    vertical = duration(src) < 100
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale=720:-2" if vertical else "scale=-2:720",
                    "-c:v", "libx264", "-crf", "30", "-preset", "medium", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(tmp)], check=True)
    if abs(duration(tmp) - duration(src)) > 1.0:
        tmp.unlink()
        raise RuntimeError(f"compressed copy of {src} has the wrong length; original kept")
    tmp.replace(dst)


def main() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    days: dict[str, list[dict]] = {}
    for it in plan:
        days.setdefault(it["publish_at"][:10], []).append(it)
    for old in KIT.glob("Day_*"):  # the first layout had the Day folders at the top
        shutil.rmtree(old)
    TODO.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(exist_ok=True)
    rows = []
    for n, (day, items) in enumerate(sorted(days.items()), 1):
        d0 = datetime.fromisoformat(items[0]["publish_at"])
        dname = f"Day_{n:02d}_{d0:%a}_{day}"
        long_url = state.get(items[0]["slug"], {}).get("url", "")
        row = {"day": n, "date": f"{d0:%a %d %b %Y}"}
        for it in items:
            slug, when = it["slug"], datetime.fromisoformat(it["publish_at"])
            kind = "SHORT" if slug.endswith("_short") else "LONG"
            ws, st = ROOT / slug, state.get(slug, {})
            pkg = json.loads((ws / "youtube_package.json").read_text(encoding="utf-8"))
            uploaded = bool(st.get("scheduled"))
            leaf = f"{kind}_{when:%H-%M}_{slug.removeprefix('vox_').removesuffix('_short')}"
            sub, other = (DONE if uploaded else TODO) / dname / leaf, (TODO if uploaded else DONE) / dname / leaf
            if other.exists():  # a stale copy on the wrong side
                shutil.rmtree(other)
            sub.mkdir(parents=True, exist_ok=True)
            src = ws / "story_1080p.mp4"
            if uploaded:
                out = sub / "video_720p_archive.mp4"
                if src.exists() and not out.exists():
                    compress(src, out)
                if out.exists() and src.exists():
                    src.unlink()  # the copy is checked and the video is on YouTube: free the disk
                video = out
            else:
                video = sub / "story_1080p.mp4"
                if not video.exists() or video.stat().st_size != src.stat().st_size:
                    shutil.copy2(src, video)
            thumb = Path(pkg.get("thumbnail_path") or "")
            if kind == "LONG" and thumb.exists():
                shutil.copy2(thumb, sub / "thumbnail.jpg")
            (sub / "title_description_tags.txt").write_text(
                info_text(kind, when, pkg, clean_description(pkg["description"], duration(video)), st, long_url), encoding="utf-8-sig")
            row[kind] = {"title": pkg["title"], "when": f"{when:%I:%M %p}", "dir": sub, "state": st}
        rows.append(row)
    for d in (TODO, DONE):  # empty day folders left behind
        for day_dir in d.glob("Day_*"):
            if not any(day_dir.iterdir()):
                day_dir.rmdir()
    up = sum(1 for r in rows for k in ("LONG", "SHORT") if k in r and r[k]["state"].get("scheduled"))
    tot = sum(1 for r in rows for k in ("LONG", "SHORT") if k in r)
    out = ["YOUTUBE UPLOAD CHECKLIST  -  @ExplainItFlat", SEP, f"Kit folder : {KIT}",
           f"  1_TO_UPLOAD        : videos NOT on YouTube yet (upload these)   -> {TODO}",
           f"  2_ALREADY_UPLOADED : videos already on YouTube, small 720p copy -> {DONE}  (safe to delete whenever you like)",
           "Times are India time. Long video 6:00 PM, its Short 8:00 PM. All videos: Schedule, not made for kids, AI content = Yes.",
           "YouTube allows about 10 new uploads per 24 h on this channel, so upload in date order, 2-5 days ahead of each date.", "",
           f"ON YOUTUBE AND SCHEDULED: {up} of {tot}      STILL TO UPLOAD: {tot - up}", "", SEP, "REMAINING TO UPLOAD (in this order)", SEP]
    for r in rows:
        for k in ("LONG", "SHORT"):
            if k in r and not r[k]["state"].get("scheduled"):
                out += [f"  [ ] Day {r['day']:02d} {r['date']} {r[k]['when']} {k:<5} {r[k]['title']}", f"        {r[k]['dir']}"]
    out += ["", SEP, "ALREADY UPLOADED AND SCHEDULED", SEP]
    for r in rows:
        for k in ("LONG", "SHORT"):
            if k in r and r[k]["state"].get("scheduled"):
                out += [f"  [x] Day {r['day']:02d} {r['date']} {r[k]['when']} {k:<5} {r[k]['title']}", f"        link : {r[k]['state']['url']}",
                        f"        files: {r[k]['dir']}"]
    (KIT / "00_CHECKLIST.txt").write_text("\n".join(out) + "\n", encoding="utf-8-sig")
    print(f"{KIT}  uploaded {up}/{tot}")


if __name__ == "__main__":
    main()
