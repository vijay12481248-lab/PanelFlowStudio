"""Step 4 CRITIQUE, code rule checks: cheap, deterministic, and dependent on neighbouring lines."""
from __future__ import annotations

import difflib
import re

from engine.narration.artifacts import LineCheck, PanelFacts, ScriptIR, SeriesBible, check_script_ids

DEFAULT_BANNED = ("in this panel", "the image shows", "in the image", "we see", "this scene shows", "the panel shows")
WORDS_PER_SECOND = 2.75
_STOP = {"i", "i'm", "i've", "i'll", "i'd", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
         "sunday", "january", "february", "march", "april", "may", "june", "july", "august", "september",
         "october", "november", "december"}
_WORD = re.compile(r"[A-Za-z][A-Za-z'\u2019]*")
_UNKNOWN = re.compile(r"unknown_\d+")


def _known_words(facts: dict[str, PanelFacts], bible: SeriesBible) -> set[str]:
    names = [n for c in bible.characters for n in (c.name, *c.aliases)]
    names += [loc.name for loc in bible.locations] + list(bible.glossary)
    names += [d.text for f in facts.values() for d in f.dialogue]
    # names perceive read off the page are facts too; a name is invented only if no fact carries it
    names += [t for f in facts.values() for t in (f.action, f.setting, *f.sfx, *f.unknown_cues.values(), *f.names_mentioned)]
    return {w.lower() for text in names for w in _WORD.findall(text.replace("\u2019", "'"))} | _STOP


def _unknown_names(text: str, known: set[str]) -> list[str]:
    out = []
    for m in _WORD.finditer(text):
        w = m.group().replace("\u2019", "'")
        before = text[:m.start()].rstrip()
        if not w[0].isupper() or not before or before[-1] in ".!?\"\u201c\u2014":
            continue
        base = w[:-2] if w.lower().endswith("'s") else w
        if base.lower() not in known and w.lower() not in known:
            out.append(base)
    return out


def _warns(texts: list[str]) -> list[tuple[bool, bool]]:
    """Per line: (repeated_opener, similar_to_previous)."""
    first = [t.split()[0].lower() if t.split() else "" for t in texts]
    return [(any(first[j] == first[i] for j in range(max(0, i - 2), i)),
             i > 0 and difflib.SequenceMatcher(None, texts[i - 1], texts[i]).ratio() > 0.8)
            for i in range(len(texts))]


def rule_checks(script: ScriptIR, facts: dict[str, PanelFacts], story_ids: list[str],
                bible: SeriesBible) -> dict[str, list[LineCheck]]:
    order = check_script_ids(script, story_ids)
    banned = [p.lower() for p in (*DEFAULT_BANNED, *bible.narrator_voice.banned_phrases) if p.strip()]
    known = _known_words(facts, bible)
    texts = [ln.text for ln in script.lines]
    out: dict[str, list[LineCheck]] = {}
    for ln, (opener, similar) in zip(script.lines, _warns(texts)):
        n, low = len(ln.text.split()), ln.text.lower()
        hit = [p for p in banned if re.search(rf"\b{re.escape(p)}\b", low)]
        unknown = _unknown_names(ln.text, known)
        out[ln.line_id] = [
            LineCheck(rule="order", passed=not order, severity="block", reason="; ".join(order)),
            LineCheck(rule="word_budget", passed=4 <= n <= 12, severity="block", reason=f"{n} words, allowed 4-12"),
            LineCheck(rule="banned_phrase", passed=not hit, severity="block", reason=", ".join(hit)),
            LineCheck(rule="unknown_name", passed=not unknown, severity="block", reason=", ".join(unknown)),
            LineCheck(rule="raw_unknown_label", passed=not _UNKNOWN.search(ln.text), severity="block",
                      reason="raw unknown_<n> label in line"),
            LineCheck(rule="repeated_opener", passed=not opener, severity="warn", reason="same opener as a recent line"),
            LineCheck(rule="similar_to_previous", passed=not similar, severity="warn", reason="near-duplicate of previous line"),
        ]
    return out


def chapter_stats(script: ScriptIR) -> tuple[float, int]:
    """(pace_estimate in seconds per line, count of warn failures)."""
    texts = [ln.text for ln in script.lines]
    if not texts:
        return 0.0, 0
    pace = sum(len(t.split()) for t in texts) / len(texts) / WORDS_PER_SECOND
    return pace, sum(a + b for a, b in _warns(texts))
