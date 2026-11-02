"""Fact-check: story claims in the narration must be backed by the episode's own evidence.

Two layers, because a 9B judge alone proved unreliable on real data (it echoed the evidence back as "unsupported" claims
and flagged plain paraphrases):

1. Deterministic lexical check - invented names, kinship words (sister, father...), quotations that are not in the dialogue
   and numbers must literally occur in the evidence. This is what catches "her missing sister, Scales".
2. LLM judge for invented events - its findings only count if they quote the narration itself (echoes of the evidence are
   discarded).

A failing paragraph is rewritten (max 2 rounds). If it still fails it is dropped when optional, or kept with `flags` for a
human when the structure needs it (hook, critique, verdict, cta). Opinions, mood and cinematography are never claims.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from engine.anime.review.models import EpisodeAnalysis, ReviewScript, ScriptSegment, Understanding
from engine.anime.review.script import problems

REQUIRED_ROLES = {"hook", "critique", "verdict", "cta"}
MAX_ROUNDS = 2
MAX_DIALOGUE_CHARS = 9000
KINSHIP = {"sister", "brother", "father", "mother", "dad", "mom", "daughter", "son", "wife", "husband", "girlfriend",
           "boyfriend", "family", "parents", "siblings", "uncle", "aunt", "grandfather", "grandmother", "lover", "fiance", "twin", "orphan"}
SYSTEM = "You are a strict, literal fact checker. You never guess."


class _Judgement(BaseModel):
    invented: list[str] = Field(default_factory=list,
                                description="short phrases copied from the NARRATION that state a plot event or "
                                            "relationship not found in the evidence")


class _Rewrite(BaseModel):
    text: str


def dialogue_evidence(a: EpisodeAnalysis | None) -> str:
    return "\n".join(s.text for s in a.transcript)[:MAX_DIALOGUE_CHARS] if a and a.transcript else ""


def beat_evidence(u: Understanding) -> str:
    return "\n".join(f"- {b.kind} ({b.start:.0f}-{b.end:.0f}s): {b.label}. {b.why} "
                     f"{('On screen: ' + b.visual) if b.visual else ''}" for b in u.beats)


def evidence_pack(u: Understanding, a: EpisodeAnalysis | None, with_summary: bool = True) -> str:
    return ((f"Summary: {u.summary}\n" if with_summary else "") + f"Characters: {', '.join(u.characters)}\n"
            f"Moments:\n{beat_evidence(u)}\nDialogue:\n{dialogue_evidence(a)}")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower().replace("'", "").replace("’", "")).strip()  # newlines separate words


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def lexical_issues(text: str, evidence: str, dialogue: str, check_numbers: bool = True) -> list[str]:
    ev_words = {_stem(w) for w in _norm(evidence).split()}
    ev_norm, dlg_norm = _norm(evidence), _norm(dialogue)
    issues: list[str] = []
    for w in re.findall(r"[A-Za-z]+", text):
        if w.lower() in KINSHIP and _stem(w.lower()) not in ev_words:
            issues.append(f"'{w}' is not in the evidence")
    for q in re.findall(r"[\"“]([^\"”]{6,})[\"”]|(?<![A-Za-z])'([^']{6,})'(?![A-Za-z])", text):
        q = _norm(q[0] or q[1])
        if len(q.split()) >= 2 and q not in dlg_norm:
            issues.append(f"quoted line '{q}' is not in the dialogue")
    for sent in re.split(r"(?<=[.!?])\s+", text):  # capitalised words inside a sentence are names
        for w in re.findall(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-z]{2,}\b", sent):
            if _stem(w.lower()) not in ev_words:
                issues.append(f"name '{w}' is not in the evidence")
    if check_numbers:
        for n in re.findall(r"\b\d+\b", text):
            if n not in ev_norm.split():
                issues.append(f"number {n} is not in the evidence")
    return list(dict.fromkeys(issues))


def _in_text(claim: str, text: str) -> bool:
    ct, tt = set(_norm(claim).split()), set(_norm(text).split())
    return bool(ct) and len(ct & tt) / len(ct) >= 0.85


async def judge(provider, evidence: str, text: str) -> list[str]:
    prompt = (f"EVIDENCE:\n{evidence}\n\nNARRATION:\n{text}\n\nCopy the short phrases of the NARRATION that state a plot "
              "event, who someone is, or a relationship that the evidence does not contain or contradicts. Paraphrases of "
              "the dialogue or moments, mood, lighting, feelings and opinions are fine. If there are none, return an "
              "empty list.")
    out = await provider.generate_structured(prompt, _Judgement, system_prompt=SYSTEM, temperature=0.0, max_tokens=400,
                                             num_ctx=16384)
    return [c.strip() for c in out.invented if c.strip() and _in_text(c, text)]  # drop echoes of the evidence


async def _rewrite(provider, evidence: str, text: str, bad: list[str], role: str) -> str | None:
    prompt = (f"EVIDENCE:\n{evidence}\n\nYour {role} paragraph:\n{text}\n\nProblems: " + "; ".join(bad) +
              "\nRewrite the paragraph in the same voice and about the same length. Keep the opinions and mood, remove "
              "every invented name, relationship, quote or event, and use only what the evidence says. Return only the "
              "paragraph.")
    out = await provider.generate_structured(prompt, _Rewrite, system_prompt=SYSTEM, temperature=0.4, max_tokens=500,
                                             num_ctx=16384)
    t = out.text.strip()
    return t if not problems([t], 4, 90) else None


async def _issues(provider, evidence: str, dialogue: str, text: str, role: str) -> list[str]:
    found = lexical_issues(text, evidence, dialogue, check_numbers=role not in {"verdict", "cta"})
    return found or await judge(provider, evidence, text)  # the LLM only runs on text the lexical layer passed


async def check_text(provider, evidence: str, dialogue: str, text: str, role: str) -> tuple[str, list[str]]:
    """(final text, issues that remain). Empty issues means the text is clean."""
    bad = await _issues(provider, evidence, dialogue, text, role)
    for _ in range(MAX_ROUNDS):
        if not bad:
            return text, []
        new = await _rewrite(provider, evidence, text, bad, role)
        if new is None:
            break
        text, bad = new, await _issues(provider, evidence, dialogue, new, role)
    return text, bad


async def ground_summary(u: Understanding, a: EpisodeAnalysis | None, provider) -> Understanding:
    """The summary feeds every later prompt, so it is checked first (against dialogue and moments only)."""
    evidence, dialogue = evidence_pack(u, a, with_summary=False), dialogue_evidence(a)
    text, bad = await check_text(provider, evidence, dialogue, u.summary, "summary")
    if bad:  # last resort: a literal list of the moments beats an unverifiable story
        text = " ".join(f"{b.label.rstrip('.')}." for b in u.beats if b.label != "Intense moment")[:600]
    return u.model_copy(update={"summary": text})


async def verify_script(script: ReviewScript, u: Understanding, a: EpisodeAnalysis | None, provider) -> ReviewScript:
    evidence, dialogue = evidence_pack(u, a), dialogue_evidence(a)
    out: list[ScriptSegment] = []
    for seg in script.segments:
        text, bad = await check_text(provider, evidence, dialogue, seg.text, seg.role)
        if bad and seg.role not in REQUIRED_ROLES:
            continue  # optional paragraph we cannot ground: leave it out
        out.append(seg.model_copy(update={"text": text, "flags": [f"unsupported: {c}" for c in bad]}))
    return script.model_copy(update={"segments": [s.model_copy(update={"id": f"s{i}"}) for i, s in enumerate(out, 1)]})
