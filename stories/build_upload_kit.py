"""Builds output/YouTube_Upload_Kit: one folder per release day (long video + thumbnail + info text, and its Short + info text),
plus 00_CHECKLIST.txt (what is on YouTube, what is left, exact paths). Safe to rerun: it refreshes the status lines.

    python stories/build_upload_kit.py"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from upload_all import PLAN, ROOT, STATE, clean_description, duration  # noqa: E402

KIT = ROOT.parent / "YouTube_Upload_Kit"
SEP = "=" * 70


def info_text(kind: str, slug: str, when: datetime, pkg: dict, desc: str, st: dict, long_url: str, has_thumb: bool) -> str:
    status = (f"ALREADY ON YOUTUBE (private, scheduled): {st['url']}\n  -> nothing to upload; the schedule is already set." if st.get("scheduled") else
              "NOT UPLOADED YET -> upload this one")
    lines = [f"{kind} VIDEO  -  {pkg['title']}", SEP,
             f"STATUS      : {status}",
             f"PUBLISH AT  : {when:%A %d %B %Y, %I:%M %p} (India time)  -> in Studio: Visibility > Schedule > that date and time",
             "VISIBILITY  : Schedule (private until the time above, then public)",
             "AUDIENCE    : No, it's not made for kids",
             "AI CONTENT  : Yes (altered or synthetic content)",
             "CATEGORY    : Film & Animation", SEP, "TITLE (copy this):", pkg["title"], "", SEP, "DESCRIPTION (copy everything below):", "", desc, "", SEP,
             "TAGS (paste into the Tags box, comma separated):", ", ".join(pkg.get("tags", [])), ""]
    if kind == "LONG":
        lines += [SEP, "THUMBNAIL: upload thumbnail.jpg from this folder (Customize > Thumbnail).", ""]
    else:
        lines += [SEP, "THUMBNAIL: Shorts have none - YouTube uses a frame of the video.",
                  f"RELATED VIDEO: in Studio set 'Related video' to the long video: {long_url or '(its link after it is uploaded)'}", ""]
    return "\n".join(lines)


def main() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    days: dict[str, list[dict]] = {}
    for it in plan:
        days.setdefault(it["publish_at"][:10], []).append(it)
    KIT.mkdir(exist_ok=True)
    rows = []
    for n, (day, items) in enumerate(sorted(days.items()), 1):
        d0 = datetime.fromisoformat(items[0]["publish_at"])
        folder = KIT / f"Day_{n:02d}_{d0:%a}_{day}"
        folder.mkdir(exist_ok=True)
        long_url = state.get(items[0]["slug"], {}).get("url", "")
        row = {"day": n, "date": f"{d0:%a %d %b %Y}", "folder": folder}
        for it in items:
            slug, when = it["slug"], datetime.fromisoformat(it["publish_at"])
            kind = "SHORT" if slug.endswith("_short") else "LONG"
            ws = ROOT / slug
            pkg = json.loads((ws / "youtube_package.json").read_text(encoding="utf-8"))
            video = ws / "story_1080p.mp4"
            sub = folder / f"{kind}_{when:%H-%M}_{slug.removeprefix('vox_').removesuffix('_short')}"
            if state.get(slug, {}).get("scheduled"):  # already on YouTube: nothing to upload, so the kit keeps no files for it
                if sub.exists() and KIT in sub.parents:
                    shutil.rmtree(sub)
                row[kind] = {"title": pkg["title"], "when": f"{when:%I:%M %p}", "dir": None, "state": state[slug]}
                continue
            sub.mkdir(exist_ok=True)
            if not (sub / video.name).exists() or (sub / video.name).stat().st_size != video.stat().st_size:
                shutil.copy2(video, sub / video.name)
            thumb = Path(pkg.get("thumbnail_path") or "")
            has_thumb = kind == "LONG" and thumb.exists()
            if has_thumb:
                shutil.copy2(thumb, sub / "thumbnail.jpg")
            desc = clean_description(pkg["description"], duration(video))
            (sub / "title_description_tags.txt").write_text(
                info_text(kind, slug, when, pkg, desc, state.get(slug, {}), long_url, has_thumb), encoding="utf-8-sig")
            row[kind] = {"title": pkg["title"], "when": f"{when:%I:%M %p}", "dir": sub, "state": state.get(slug, {})}
        if not any(folder.iterdir()):
            folder.rmdir()
            row["folder"] = None
        rows.append(row)
    out = ["YOUTUBE UPLOAD CHECKLIST  -  @ExplainItFlat", SEP,
           f"Kit folder : {KIT}", "Only videos NOT yet on YouTube have files here. Each Day_NN folder = one release day: a LONG folder (video, thumbnail.jpg, title_description_tags.txt) and a SHORT folder.",
           "Times are India time. Long video 6:00 PM, its Short 8:00 PM. All videos: Schedule, not made for kids, AI content = Yes.",
           "YouTube allows about 10 new uploads per 24 h on this channel, so upload in date order, 2-5 days ahead of each date.", ""]
    up = sum(1 for r in rows for k in ("LONG", "SHORT") if k in r and r[k]["state"].get("scheduled"))
    tot = sum(1 for r in rows for k in ("LONG", "SHORT") if k in r)
    out += [f"UPLOADED AND SCHEDULED: {up} of {tot}      REMAINING: {tot - up}", "", SEP, "DAY-BY-DAY  ([x] = on YouTube and scheduled, [ ] = still to upload)", SEP]
    for r in rows:
        out.append(f"\nDay {r['day']:02d} - {r['date']}   folder: {r['folder']}")
        for k in ("LONG", "SHORT"):
            if k in r:
                x = r[k]
                out.append(f"  [{'x' if x['state'].get('scheduled') else ' '}] {k:<5} {x['when']}  {x['title']}")
                if x["dir"]:
                    out.append(f"        files: {x['dir']}")
                if x["state"].get("url"):
                    out.append(f"        link : {x['state']['url']}")
    out += ["", SEP, "REMAINING TO UPLOAD (in this order)", SEP]
    for r in rows:
        for k in ("LONG", "SHORT"):
            if k in r and not r[k]["state"].get("scheduled"):
                out.append(f"  Day {r['day']:02d} {r['date']} {r[k]['when']} {k:<5} {r[k]['dir']}")
    (KIT / "00_CHECKLIST.txt").write_text("\n".join(out) + "\n", encoding="utf-8-sig")
    print(f"{KIT}  uploaded {up}/{tot}")


if __name__ == "__main__":
    main()
