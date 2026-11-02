"""YouTube package for a review: title, description with valid chapters, tags and a thumbnail."""
from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel

from engine.acquisition.rights.models import RightsDeclaration
from engine.anime.review.models import ClipPlan, ReviewScript, Timeline, Understanding

MIN_CHAPTER_SEC = 10.0  # YouTube ignores chapters shorter than this, and needs 3+ starting at 0:00
CHAPTER_LABELS = {"hook": "Intro", "recap": "What happens", "highlight": "Highlights", "smooth": "What worked",
                  "funny": "Funny moments", "critique": "What didn't work", "verdict": "Verdict", "cta": "Verdict"}
IMPACT = Path("C:/Windows/Fonts/impact.ttf")


class YouTubePackage(BaseModel):
    title: str
    description: str
    tags: list[str]
    chapters: list[tuple[str, str]]  # (timestamp, label)
    thumbnail_path: str | None = None


def _stamp(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def chapters(script: ReviewScript, tl: Timeline) -> list[tuple[str, str]]:
    out: list[tuple[float, str]] = []
    for seg, e in zip(script.segments, tl.entries):
        label = CHAPTER_LABELS.get(seg.role, seg.role.title())
        if out and out[-1][1] == label:
            continue
        if out and e.timeline_start - out[-1][0] < MIN_CHAPTER_SEC:
            continue  # too close to the previous chapter: fold into it
        out.append((e.timeline_start, label))
    if len(out) < 3:
        return []  # YouTube would not render them; better none than broken ones
    return [(_stamp(t), l) for t, l in out]


def thumbnail(source: Path, plan: ClipPlan, text: str, out: Path) -> Path | None:
    from PIL import Image, ImageDraw, ImageFont

    if not plan.clips:
        return None
    clip = max(plan.clips, key=lambda c: c.duration)
    frame = out.with_suffix(".frame.jpg")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{clip.start + clip.duration / 2}", "-i", str(source),
                        "-frames:v", "1", "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
                        str(frame)])
    if r.returncode != 0 or not frame.exists():
        return None
    img = Image.open(frame).convert("RGB")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(IMPACT), 92) if IMPACT.exists() else ImageFont.load_default()
    lines, cur = [], ""
    for w in text.upper().split():
        if cur and d.textlength(cur + " " + w, font=font) > 1150:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    y = 720 - 40 - 105 * len(lines[:3])
    for ln in lines[:3]:
        d.text((60, y), ln, font=font, fill="white", stroke_width=6, stroke_fill="black")
        y += 105
    img.save(out, quality=92)
    frame.unlink(missing_ok=True)
    return out


def build_package(series: str, script: ReviewScript, u: Understanding, tl: Timeline, plan: ClipPlan, source: Path,
                  rights: RightsDeclaration, ws: Path, extra_tags: list[str] | None = None,
                  footer: str = "") -> YouTubePackage:
    ch = chapters(script, tl)
    desc = [script.title_hook, "", u.summary, "", f"My rating: {script.rating:g}/10", ""]
    if ch:
        desc += ["Chapters:"] + [f"{t} {l}" for t, l in ch] + [""]
    desc += ["This is an independent review with my own commentary. Short clips are used for criticism and discussion; "
             f"all rights belong to their owners. Rights basis: {rights.status.value}."]
    if footer:
        desc += ["", footer]
    tags = [series, f"{series} review", "anime review", "episode review", "anime recap"] + u.characters[:5] + (extra_tags or [])
    pkg = YouTubePackage(title=f"{series} Review - {script.title_hook}"[:100], description="\n".join(desc), tags=tags,
                         chapters=ch)
    thumb = thumbnail(source, plan, script.title_hook, ws / "thumbnail.jpg")
    pkg.thumbnail_path = str(thumb) if thumb else None
    (ws / "youtube_package.json").write_text(pkg.model_dump_json(indent=2), encoding="utf-8")
    return pkg
