"""Image reviewer: does this picture show what the narration says? Evidence, confidence and a decision - accept or redraw.

Why it exists: the first checker described the picture and asked one model whether "everything required" was visible. It
accepted a picture whose narration was "Elena turns her head upward, her eyes locking onto the single silver bell hanging high on
the wall" although the bell was a speck on her head and she looked sideways, because (a) the director's key-visual list had lost the
bell, and (b) the judge marked nearly everything missing and the loop kept the best of three anyway.

The reviewer therefore works from the NARRATION itself, independently of the shot director, and uses two separate witnesses:

1. claims   : an LLM lists the visible facts the narration asserts (who, what they do, where they look, objects with colour and
               position, count of people), each marked critical or not.
2. witness A: the vision model answers one numbered question per requirement with yes / partly / no and the visible evidence.
3. witness B: the same vision model writes a free description of the picture, and a text-only model says whether that description
               states each requirement.
4. verdict  : per requirement - both witnesses agree -> shown/missing with high confidence; they disagree -> partial with low confidence.
5. decision : accept (no critical miss, score >= 0.75, confidence >= 0.6), accept_low (no critical miss, score >= 0.6: kept but
               flagged), otherwise regenerate. After the last attempt a picture that still fails is never silently accepted: it is
               marked needs_review and listed in the report.
"""
from __future__ import annotations

import html
from pathlib import Path

from pydantic import BaseModel, Field

from engine.original.shotspec import ShotSpec
from engine.original.models import Character

ACCEPT_SCORE, ACCEPT_CONFIDENCE, LOW_SCORE = 0.75, 0.6, 0.6
VERDICT_SCORE = {"shown": 1.0, "partial": 0.5, "missing": 0.0}
RANK = {"accept": 2, "accept_low": 1, "regenerate": 0}


class Claim(BaseModel):
    text: str
    critical: bool = True


class _Claims(BaseModel):
    claims: list[Claim] = Field(description="the visible facts the narration asserts, at most 6")


class _QA(BaseModel):
    n: int
    answer: str = Field(description="yes, partly or no")
    evidence: str = Field(default="", description="what is visible that supports the answer, at most 12 words")


class _VQA(BaseModel):
    answers: list[_QA]


class _DescJudge(BaseModel):
    stated: list[bool] = Field(description="for each numbered requirement, whether the description states it, in order")


class ItemVerdict(BaseModel):
    item: str
    critical: bool
    verdict: str  # shown | partial | missing
    confidence: float
    vision: str  # yes | partly | no
    description_says: bool
    evidence: str = ""


class Review(BaseModel):
    items: list[ItemVerdict]
    score: float
    confidence: float
    decision: str  # accept | accept_low | regenerate
    reasons: list[str] = Field(default_factory=list)
    description: str = ""

    @property
    def missing_critical(self) -> list[str]:
        return [i.item for i in self.items if i.critical and i.verdict != "shown"]


STOP = {"the", "and", "that", "with", "from", "into", "this", "there", "their", "they", "them", "her", "his", "she", "for", "are", "was",
        "has", "have", "who", "what", "which", "while", "over", "onto", "than", "then", "its", "any", "all", "one", "single", "very"}
NEGATIVE_CLAIM = ("no visible", "not visible", "not visibly", "there is no", "is not ", "are not ", "cannot be seen")


def _content(text: str) -> set[str]:
    return {w.strip(".,;:!?'\"()").lower().rstrip("s") for w in text.split() if len(w) > 3 and w.lower() not in STOP}


def clean_claims(claims: list[Claim], narration: str) -> list[Claim]:
    """A claim must be a positive, visible statement that comes from THIS narration: no negations, no proper nouns (the cast is
    checked separately), and at least one content word the narration actually uses. A small model otherwise parrots the cast list."""
    said = _content(narration)
    seen, out = set(), []
    for c in claims:
        t = " ".join(c.text.split())
        words = t.split()
        proper = any(w[:1].isupper() and k > 0 for k, w in enumerate(words))
        if not t or t.lower() in seen or proper or any(n in t.lower() for n in NEGATIVE_CLAIM) or not (_content(t) & said):
            continue
        seen.add(t.lower())
        out.append(Claim(text=t[:140], critical=c.critical))
    return out[:6]


async def extract_claims(provider, narration: str) -> list[Claim]:
    prompt = ("Narration that will be read aloud over a picture:\n\"" + narration + "\"\n\n"
              "List the facts in it that can be SEEN in a single picture: which people or creatures, what each is doing, which way they "
              "look, objects with their colour and position, the place. Use only what the narration says. Skip ideas, feelings, names of "
              "places or people, and anything not visible. Mark a claim critical if the picture is wrong without it (a named object, an "
              "action, a gaze direction). Write each claim as a short positive statement, e.g. 'a silver bell hangs high on the wall'.")
    out = await provider.generate_structured(prompt, _Claims, system_prompt="You extract visual requirements precisely.", temperature=0.0,
                                             max_tokens=500, num_ctx=8192)
    return clean_claims(out.claims, narration)


def requirements(claims: list[Claim], spec: ShotSpec | None, chars: dict[str, Character]) -> list[tuple[str, bool]]:
    """Narration claims first (critical as judged), then what the shot director added: who is visible, how many, the place."""
    reqs: list[tuple[str, bool]] = [(c.text, c.critical) for c in claims]
    if spec is not None:
        n = len(spec.characters)
        reqs.append(("there are no people in the picture" if n == 0 else f"exactly {n} {'person or creature is' if n == 1 else 'people or creatures are'} visible", True))
        for c in spec.characters:
            ch = chars.get(c.id)
            if ch:
                reqs.append((f"{ch.look.split(',')[0].strip()} {('(' + ch.species + ')') if ch.species != 'human' else 'character'} is visible", False))
        if spec.setting:
            reqs.append((spec.setting.split(".")[0].split(":")[-1].strip()[:90], False))
    out, seen = [], set()
    for t, crit in reqs:
        key = " ".join(sorted(set(t.lower().split())))
        if t and key not in seen:
            seen.add(key)
            out.append((t, crit))
    return out[:10]


async def _vqa(provider, image: Path, reqs: list[tuple[str, bool]]) -> list[_QA]:
    qs = "\n".join(f"{i + 1}. Is this true of the picture: {t}?" for i, (t, _) in enumerate(reqs))
    prompt = ("Look carefully at this illustration and answer each question with yes, partly or no. 'yes' only if it is clearly visible; "
              "'partly' if it is there but small, hidden or different; 'no' if it is absent or contradicted. Give the visible evidence.\n" + qs)
    raw = await provider.analyze_vision(image, prompt, format_schema=_VQA.model_json_schema(), max_tokens=900, temperature=0.0)
    try:
        by_n = {a.n: a for a in _VQA.model_validate_json(raw).answers}
    except Exception:
        by_n = {}
    return [by_n.get(i + 1, _QA(n=i + 1, answer="partly", evidence="no answer")) for i in range(len(reqs))]


async def _describe(provider, image: Path) -> str:
    return (await provider.analyze_vision(
        image, "Describe this illustration literally for someone who cannot see it: each character (kind, hair, clothes), body pose, "
        "face, where they look, what they hold or do, objects and where they are, the place and the light. Do not guess. At most 110 words.",
        max_tokens=1100, temperature=0.0)).strip()


async def _description_states(provider, description: str, reqs: list[tuple[str, bool]]) -> list[bool]:
    lst = "\n".join(f"{i + 1}. {t}" for i, (t, _) in enumerate(reqs))
    prompt = (f"DESCRIPTION OF A PICTURE:\n{description}\n\nREQUIREMENTS:\n{lst}\n\nFor each numbered requirement say whether the description "
              "states it or clearly implies it (different wording counts). Answer with one true/false per requirement, in order.")
    out = await provider.generate_structured(prompt, _DescJudge, system_prompt="You are a strict, literal reader.", temperature=0.0,
                                             max_tokens=300, num_ctx=8192)
    flags = list(out.stated)[:len(reqs)]
    return flags + [False] * (len(reqs) - len(flags))


def combine(reqs: list[tuple[str, bool]], qa: list[_QA], stated: list[bool], description: str = "") -> Review:
    """Pure decision logic: two witnesses per requirement -> verdict, confidence, score and accept/regenerate."""
    items: list[ItemVerdict] = []
    for (text, crit), a, said in zip(reqs, qa, stated):
        v = a.answer.strip().lower()
        v = "yes" if v.startswith("y") else "no" if v.startswith("n") else "partly"
        if v == "yes" and said:
            verdict, conf = "shown", 0.9
        elif v == "no" and not said:
            verdict, conf = "missing", 0.9
        elif v == "yes":
            verdict, conf = "shown", 0.5  # only the vision answer says so: believed, but not twice
        elif v == "no":
            verdict, conf = "partial", 0.4  # the description mentions it, the question says no: unclear
        else:
            verdict, conf = "partial", 0.6
        items.append(ItemVerdict(item=text, critical=crit, verdict=verdict, confidence=conf, vision=v, description_says=said, evidence=a.evidence))
    if not items:
        return Review(items=[], score=1.0, confidence=0.0, decision="accept_low", reasons=["nothing to check"], description=description)
    w = [2.0 if i.critical else 1.0 for i in items]
    score = sum(wi * VERDICT_SCORE[i.verdict] for wi, i in zip(w, items)) / sum(w)
    confidence = sum(wi * i.confidence for wi, i in zip(w, items)) / sum(w)
    crit_missing = [i.item for i in items if i.critical and i.verdict == "missing"]
    crit_partial = [i.item for i in items if i.critical and i.verdict == "partial"]
    reasons = [f"critical item not shown: {t}" for t in crit_missing] + [f"critical item unclear: {t}" for t in crit_partial]
    if not crit_missing and not crit_partial and score >= ACCEPT_SCORE and confidence >= ACCEPT_CONFIDENCE:
        decision = "accept"
    elif not crit_missing and score >= LOW_SCORE:
        decision = "accept_low"
        reasons.append(f"score {score:.2f} / confidence {confidence:.2f} is below the accept bar")
    else:
        decision = "regenerate"
    return Review(items=items, score=round(score, 3), confidence=round(confidence, 3), decision=decision, reasons=reasons, description=description)


async def review_image(provider, image: Path, claims: list[Claim], spec: ShotSpec | None, chars: dict[str, Character]) -> Review:
    reqs = requirements(claims, spec, chars)
    if not reqs:
        return combine([], [], [], "")
    description = await _describe(provider, image)
    qa = await _vqa(provider, image, reqs)
    stated = await _description_states(provider, description, reqs)
    return combine(reqs, qa, stated, description)


def write_report(story_panels: list, ws: Path, records: list[dict]) -> Path:
    """review_report.html: each picture beside its narration, the decision and every requirement with both witnesses' answers."""
    by_id = {r["panel_id"]: r for r in records}
    rows = []
    for p in story_panels:
        r = by_id.get(p.id)
        if not r:
            continue
        rev = r.get("review") or {}
        status = r.get("status", "")
        items = "".join(
            f"<tr class='{html.escape(i['verdict'])}'><td>{'★ ' if i['critical'] else ''}{html.escape(i['item'])}</td><td>{html.escape(i['verdict'])}</td>"
            f"<td>{i['confidence']:.1f}</td><td>{html.escape(i['vision'])}: {html.escape(i.get('evidence', ''))}</td></tr>" for i in rev.get("items", []))
        rows.append(
            f"<section class='{html.escape(status)}'><img src='panels/{html.escape(p.id)}.png' width='480'><div><h3>{html.escape(p.id)} "
            f"<span class='b'>{html.escape(status)}</span> score {rev.get('score', '-')} confidence {rev.get('confidence', '-')} "
            f"attempts {r.get('attempts')}</h3><p>{html.escape(p.caption)}</p><table>{items}</table>"
            f"<p class='desc'>{html.escape(rev.get('description', ''))}</p></div></section>")
    css = ("body{font-family:sans-serif;max-width:1100px;margin:20px auto;background:#111;color:#eee}section{display:flex;gap:16px;margin:18px 0;"
           "padding:12px;border-radius:8px;background:#1b1b1f}h3{margin:0 0 6px}.b{padding:2px 8px;border-radius:10px;background:#444;font-size:12px}"
           "section.accept .b{background:#1c6b3a}section.accept_low .b{background:#8a6d12}section.needs_review .b{background:#8b2b2b}"
           "table{border-collapse:collapse;font-size:12px}td{border-bottom:1px solid #333;padding:3px 8px}tr.missing td{color:#f08080}"
           "tr.partial td{color:#e6c35c}.desc{font-size:12px;color:#aaa}")
    out = ws / "review_report.html"
    out.write_text(f"<!doctype html><meta charset='utf-8'><title>Picture review</title><style>{css}</style><h1>Picture review</h1>" + "".join(rows),
                   encoding="utf-8")
    return out
