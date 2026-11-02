"""Review script, written section by section so length, order and clip binding are controlled by code.

A single-shot LLM script (hook..cta in one JSON) failed on real data: a 9B model returns ~300 words when ~1000 are
needed and mixes up roles. Here the structure is fixed in code (hook, recap, one block per clip in time order, critique,
verdict, cta); the model only writes the sentences of one small section per call, and each call is validated/retried.
"""
from __future__ import annotations

import math
import re

from pydantic import BaseModel, Field

from engine.anime.review.models import Beat, ClipPlan, EpisodeAnalysis, ReviewScript, ScriptSegment, Understanding

MIN_WORDS, MAX_WORDS = 12, 70
WORDS_PER_SEC = 2.4  # Kokoro at speed 1.0, including pauses
FIXED_WORDS = 280    # hook + recap + critique + verdict + cta
BEAT_ROLE = {"opening": "recap", "highlight": "highlight", "emotional": "highlight", "funny": "funny",
             "smooth": "smooth", "weak": "critique", "ending": "recap"}
# phrases that make narration read as machine-written
AI_ISMS = ["delve", "tapestry", "testament to", "in conclusion", "it's worth noting", "ultimately,", "rich tapestry",
           "stunning turning point", "as an ai", "buckle up", "dive into", "a whole new tier", "smash that",
           "masterpiece"]


class _Lines(BaseModel):
    segments: list[str] = Field(description="narration paragraphs, spoken aloud, plain sentences")


class _Intro(BaseModel):
    hook: str = Field(description="one gripping spoken opening line, under 30 words")
    recap: list[str] = Field(description="2-3 paragraphs recapping what happens, spoiler-light")


class _Verdict(BaseModel):
    title_hook: str = Field(description="curiosity-driven video title line, no lies")
    rating: float = Field(description="score out of 10")
    verdict: str = Field(description="spoken verdict that states the rating out of 10")
    cta: str = Field(description="short call to action: subscribe, comment a specific question")


def problems(texts: list[str], lo: int = MIN_WORDS, hi: int = MAX_WORDS) -> list[str]:
    out = []
    for i, t in enumerate(texts, 1):
        n = len(t.split())
        if not lo <= n <= hi:
            out.append(f"paragraph {i} has {n} words, need {lo}-{hi}")
        bad = [p for p in AI_ISMS if p in t.lower()]
        if bad:
            out.append(f"paragraph {i}: avoid stock phrases {bad}")
    return out


async def _ask(provider, prompt: str, model, check, system: str, attempts: int = 3):
    feedback: list[str] = []
    for _ in range(attempts):
        text = prompt + ("\n\nFix these problems from your last answer:\n- " + "\n- ".join(feedback) if feedback else "")
        out = await provider.generate_structured(text, model, system_prompt=system, temperature=0.7, max_tokens=1500,
                                                 num_ctx=8192)
        feedback = check(out)
        if not feedback:
            return out
    raise ValueError("script section failed validation after retries: " + "; ".join(feedback))


def _context(title: str, u: Understanding, tone: str, language: str) -> str:
    return (f'You are narrating your own YouTube review of "{title}". Language: {language}. Voice: {tone}.\n'
            "Sound like one real person talking: contractions, opinions, short sentences. No lists, headings, emojis or "
            "stock phrases. Only use facts from the notes below; never invent plot, names or quotes.\n"
            f"Episode summary: {u.summary}\nCharacters: {', '.join(u.characters)}\n")


def _dialogue(a: EpisodeAnalysis | None, b: Beat) -> str:
    if not a:
        return ""
    lines = [s.text for s in a.transcript if s.end >= b.start - 2 and s.start <= b.end + 2][:6]
    return "Dialogue in this moment: " + " / ".join(lines) + "\n" if lines else ""


async def write_script(title: str, u: Understanding, plan: ClipPlan, provider, tone: str = "warm, witty, honest fan reviewer",
                       language: str = "English", target_sec: float = 0, analysis: EpisodeAnalysis | None = None,
                       **_ignored) -> ReviewScript:
    if not plan.clips:
        raise ValueError("clip plan is empty; nothing to narrate over")
    system = "You are a charismatic anime YouTuber writing your own voiceover."
    ctx = _context(title, u, tone, language)
    beats = {b.id: b for b in u.beats}
    clips = sorted(plan.clips, key=lambda c: c.start)
    segs: list[tuple[str, str, str]] = []  # (clip_id, role, text)

    intro = await _ask(provider, ctx + "Write the hook (one line) and a spoiler-light recap of what happens in this episode "
                       f"(2-3 paragraphs of {MIN_WORDS + 8}-{MAX_WORDS - 15} words each).", _Intro,
                       lambda o: problems([o.hook], 4, 40) + problems(o.recap), system)
    first = next((c for c in clips if beats[c.beat_id].kind == "opening"), clips[0])
    segs.append((first.id, "hook", intro.hook.strip()))
    for i, t in enumerate(intro.recap):
        segs.append((clips[min(i, len(clips) - 1)].id, "recap", t.strip()))

    per_clip = max(35, (int(target_sec * WORDS_PER_SEC) - FIXED_WORDS) // len(clips)) if target_sec else 45
    k = max(1, min(3, math.ceil(per_clip / 60)))
    each = max(MIN_WORDS + 3, min(MAX_WORDS - 10, per_clip // k))
    for c in clips:
        b = beats[c.beat_id]
        what = (f"Moment: {b.label}. Why it matters: {b.why}\n" + (f"On screen: {b.visual}\n" if b.visual else "")
                + _dialogue(analysis, b))
        role = BEAT_ROLE.get(b.kind, "highlight")
        ask = (ctx + f"Now talk about this {b.kind} moment while the viewer watches it.\n{what}"
               f"Write {k} paragraph(s) of about {each} words each, in a {role} tone"
               + (": explain what happens and why it matters" if role == "recap" else
                  ": say what worked or landed and why" if role in ("highlight", "smooth") else
                  ": point to what was funny, only if it truly was" if role == "funny" else
                  ": be honest about what dragged or fell flat") + ".")
        out = await _ask(provider, ask, _Lines, lambda o: problems(o.segments) if o.segments else ["no paragraphs"], system)
        segs += [(c.id, role, t.strip()) for t in out.segments[:k]]

    weak = next((c for c in clips if beats[c.beat_id].kind == "weak"), clips[len(clips) // 2])
    crit = await _ask(provider, ctx + "Write one honest, specific criticism or reservation (pacing, a flat scene, "
                      "predictability, clarity) that is consistent with the notes and adds no new plot. "
                      f"One paragraph of {MIN_WORDS + 18}-{MAX_WORDS - 10} words.", _Lines,
                      lambda o: problems(o.segments[:1]) if o.segments else ["no paragraphs"], system)
    segs.append((weak.id, "critique", crit.segments[0].strip()))

    ver = await _ask(provider, ctx + "Write the verdict (it must say your rating out of 10 in words or digits, and one "
                     "reason), the title line, and a short call to action asking viewers a specific question.", _Verdict,
                     lambda o: (problems([o.verdict, o.cta], 8, MAX_WORDS) +
                                ([] if 0 <= o.rating <= 10 else ["rating must be 0-10"])), system)
    last = clips[-1].id
    segs += [(last, "verdict", ver.verdict.strip()), (last, "cta", ver.cta.strip())]
    return ReviewScript(title_hook=ver.title_hook.strip(), rating=round(ver.rating, 1), tone=tone, segments=[
        ScriptSegment(id=f"s{i}", clip_id=cid, role=role, text=re.sub(r"\s+", " ", t))
        for i, (cid, role, t) in enumerate(segs, 1)])
