"""Review script: human-voiced narration, every segment bound to a clip, validated and repaired once."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from engine.anime.review.models import ClipPlan, ReviewScript, ScriptSegment, Understanding

ROLES = {"hook", "recap", "highlight", "smooth", "funny", "critique", "verdict", "cta"}
MIN_WORDS, MAX_WORDS = 12, 70
# phrases that make narration read as machine-written
AI_ISMS = ["delve", "tapestry", "testament to", "in conclusion", "it's worth noting", "ultimately,", "rich tapestry",
           "stunning turning point", "as an ai", "buckle up", "dive into", "a whole new tier"]


class _SegOut(BaseModel):
    clip_id: str
    role: str
    text: str


class _ScriptOut(BaseModel):
    title_hook: str = Field(description="a curiosity-driven video title line, no clickbait lies")
    rating: float = Field(description="verdict score out of 10")
    segments: list[_SegOut]


def validate(out: _ScriptOut, plan: ClipPlan, has_funny: bool = True) -> list[str]:
    """Problems that make a script unusable; empty list means ship it."""
    issues: list[str] = []
    ids = {c.id for c in plan.clips}
    segs = out.segments
    if not segs:
        return ["no segments"]
    if segs[0].role != "hook":
        issues.append("first segment must have role hook")
    if segs[-1].role != "cta":
        issues.append("last segment must have role cta (ask to subscribe/comment)")
    if not any(s.role == "verdict" for s in segs):
        issues.append("missing a verdict segment that states the rating")
    if not any(s.role == "critique" for s in segs):
        issues.append("missing a critique segment (something that did not work)")
    if not 0 <= out.rating <= 10:
        issues.append("rating must be between 0 and 10")
    for i, s in enumerate(segs, 1):
        if s.role == "funny" and not has_funny:
            issues.append(f"segment {i}: no funny moment exists in this episode; remove the funny segment")
        n = len(s.text.split())
        if s.clip_id not in ids:
            issues.append(f"segment {i}: unknown clip_id {s.clip_id!r}; use one of {sorted(ids)}")
        if s.role not in ROLES:
            issues.append(f"segment {i}: role {s.role!r} not in {sorted(ROLES)}")
        if not MIN_WORDS <= n <= MAX_WORDS:
            issues.append(f"segment {i}: {n} words, need {MIN_WORDS}-{MAX_WORDS}")
        bad = [p for p in AI_ISMS if p in s.text.lower()]
        if bad:
            issues.append(f"segment {i}: avoid stock phrases {bad}")
    missing = ids - {s.clip_id for s in segs}
    if missing:
        issues.append(f"clips never narrated: {sorted(missing)}")
    return issues


def _prompt(title: str, u: Understanding, plan: ClipPlan, tone: str, language: str, feedback: list[str]) -> str:
    beats = {b.id: b for b in u.beats}
    clip_lines = "\n".join(
        f"- {c.id} ({c.duration:.0f}s): {beats[c.beat_id].kind.upper()} - {c.purpose}. {beats[c.beat_id].why}"
        for c in plan.clips)
    p = (
        f'Write the narration for a YouTube review video of "{title}", language: {language}. Voice: {tone}.\n'
        "Sound like one real person talking to viewers: contractions, opinions, short sentences, a joke where it fits. "
        "No lists, no headings, no emojis, no filler like 'in conclusion'.\n\n"
        f"Episode summary (facts you may use, nothing else): {u.summary}\n"
        f"Characters: {', '.join(u.characters)}\n\n"
        f"Clips you can show (each segment is spoken over exactly one clip):\n{clip_lines}\n\n"
        "Structure, in order. The FIRST segment must have role hook: one gripping spoken opening line that makes people stay "
        "(title_hook is separate and is not spoken). Then a spoiler-light recap of what happens (recap), then segments for "
        "what was highlighted (highlight), what was smooth/great (smooth), what was funny (funny, ONLY if a clip above is marked FUNNY; never invent jokes about events), at least one honest criticism (critique), a verdict that says the rating out of 10 (verdict), and a "
        "closing call to action (cta). Every clip above must be used by at least one segment; a clip may be reused "
        f"for the recap/verdict. Each segment is {MIN_WORDS}-{MAX_WORDS} words. Do not invent events or names."
    )
    if feedback:
        p += "\n\nYour previous draft had these problems, fix them:\n- " + "\n- ".join(feedback)
    return p


async def write_script(title: str, u: Understanding, plan: ClipPlan, provider, tone: str = "warm, witty, honest fan reviewer",
                       language: str = "English", max_attempts: int = 3) -> ReviewScript:
    if not plan.clips:
        raise ValueError("clip plan is empty; nothing to narrate over")
    feedback: list[str] = []
    for _ in range(max_attempts):
        out = await provider.generate_structured(
            _prompt(title, u, plan, tone, language, feedback), _ScriptOut,
            system_prompt="You are a charismatic anime YouTuber writing your own voiceover.",
            temperature=0.7, max_tokens=3500, num_ctx=16384)
        feedback = validate(out, plan, any(b.kind == "funny" for b in u.beats))
        if not feedback:
            break
    else:
        raise ValueError("script failed validation after retries: " + "; ".join(feedback))
    segs = [ScriptSegment(id=f"s{i}", clip_id=s.clip_id, role=s.role, text=re.sub(r"\s+", " ", s.text).strip())
            for i, s in enumerate(out.segments, 1)]
    return ReviewScript(title_hook=out.title_hook.strip(), rating=round(out.rating, 1), segments=segs, tone=tone)
