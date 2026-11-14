"""Step 4 CRITIQUE, code rule checks: cheap, deterministic, and dependent on neighbouring lines."""
from __future__ import annotations

import difflib
import re

from engine.narration.artifacts import (
    LineCheck, NARRATOR_ID, PanelFacts, ScriptIR, SeriesBible, check_script_ids,
)

DEFAULT_BANNED = ("in this panel", "the image shows", "in the image", "we see", "this scene shows", "the panel shows",
                  # narration about the narration, seen in real runs ("...no action or dialogue occurring")
                  "no action", "no dialogue", "nothing happens", "the narrative", "the story continues")
NEARBY = 3  # a character seen this many panels away is still in the scene
_SHE = re.compile(r"\b(she|her|hers|herself)\b", re.I)
_HE = re.compile(r"\b(he|him|his|himself)\b", re.I)
WORDS_PER_SECOND = 2.75
MIN_WORDS, MAX_WORDS = 4, 18  # a story line (event + meaning + feeling) needs more room than a caption
_STOP = {"the", "a", "an", "i", "i'm", "i've", "i'll", "i'd", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
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


def _name_forms(bible: SeriesBible) -> dict[str, list[str]]:
    """id -> ways the narration may name a character: full name, aliases, and the given name ("Jingwei")."""
    forms = {c.id: [n for n in (c.name, *c.aliases) if n.strip()] for c in bible.characters}
    last = {c.id: c.name.split()[-1] for c in bible.characters if len(c.name.split()) > 1}
    shared = {w for w in last.values() if list(last.values()).count(w) > 1}
    for cid, w in last.items():
        if len(w) >= 4 and w not in shared:
            forms[cid].append(w)
    return forms


def _names_in(text: str, forms: dict[str, list[str]], case: bool) -> set[str]:
    flags = 0 if case else re.I
    return {cid for cid, fs in forms.items() if any(re.search(rf"\b{re.escape(f)}\b", text, flags) for f in fs)}


def _absent_and_pronoun(ln, facts: dict[str, PanelFacts], story_ids: list[str], bible: SeriesBible,
                        forms: dict[str, list[str]]) -> tuple[list[str], str]:
    """Bible characters the line names who are neither nearby nor mentioned here; and a pronoun clash, if any."""
    if ln.panel_id not in facts:
        return [], ""
    named = _names_in(ln.text, forms, case=True)
    at = story_ids.index(ln.panel_id) if ln.panel_id in story_ids else -1
    near = [facts[p] for p in story_ids[max(0, at - NEARBY):at + NEARBY + 1] if p in facts] if at >= 0 else [facts[ln.panel_id]]
    here = facts[ln.panel_id]
    present = {c for f in near for c in [*f.characters_visible, *(d.speaker_id for d in f.dialogue if d.speaker_id)]}
    spoken = " ".join([*(d.text for d in here.dialogue), *here.names_mentioned])
    present |= _names_in(spoken, forms, case=False)
    names = {c.id: c.name for c in bible.characters}
    absent = [names[c] for c in sorted(named - present)]
    pron = {c.id: c.pronouns for c in bible.characters if c.pronouns}
    involved = {pron[c] for c in named | set(here.characters_visible) if c in pron}
    clash = ""
    if involved == {"he"} and _SHE.search(ln.text):
        clash = "uses she/her, but every character here is he"
    elif involved == {"she"} and _HE.search(ln.text):
        clash = "uses he/him, but every character here is she"
    return absent, clash


def _warns(texts: list[str]) -> list[tuple[bool, bool]]:
    """Per line: (repeated_opener, similar_to_previous)."""
    first = [t.split()[0].lower() if t.split() else "" for t in texts]
    words = [set(re.findall(r"[a-z']{4,}", t.lower())) for t in texts]  # re-told lines share their content words

    def similar(i: int) -> bool:
        if i == 0:
            return False
        shared = len(words[i] & words[i - 1]) / max(1, len(words[i] | words[i - 1]))
        return difflib.SequenceMatcher(None, texts[i - 1], texts[i]).ratio() > 0.8 or shared >= 0.5

    return [(any(first[j] == first[i] for j in range(max(0, i - 2), i)), similar(i)) for i in range(len(texts))]


def _speaker_check(ln, facts: dict[str, PanelFacts], story_ids: list[str], bible: SeriesBible) -> tuple[bool, str]:
    """A line may be read by the narrator, or by a character it quotes who is present in the scene."""
    if ln.speaker_id == NARRATOR_ID:
        return True, ""
    if ln.speaker_id not in {c.id for c in bible.characters}:
        return False, f"speaker {ln.speaker_id!r} is not a character in the bible"
    if "dialogue" not in ln.facts_used:
        return False, f"speaker {ln.speaker_id!r} does not quote any dialogue"
    if ln.panel_id not in facts:
        return True, ""
    at = story_ids.index(ln.panel_id) if ln.panel_id in story_ids else -1
    near = [facts[p] for p in story_ids[max(0, at - NEARBY):at + NEARBY + 1] if p in facts] if at >= 0 else [facts[ln.panel_id]]
    here = facts[ln.panel_id]
    present = {c for f in near for c in [*f.characters_visible, *(d.speaker_id for d in f.dialogue if d.speaker_id)]}
    if ln.speaker_id not in present:
        return False, f"speaker {ln.speaker_id!r} is not in this scene"
    return True, ""


def rule_checks(script: ScriptIR, facts: dict[str, PanelFacts], story_ids: list[str],
                bible: SeriesBible) -> dict[str, list[LineCheck]]:
    order = check_script_ids(script, story_ids)
    banned = [p.lower() for p in (*DEFAULT_BANNED, *bible.narrator_voice.banned_phrases) if p.strip()]
    known = _known_words(facts, bible)
    texts = [ln.text for ln in script.lines]
    forms = _name_forms(bible)
    out: dict[str, list[LineCheck]] = {}
    for ln, (opener, similar) in zip(script.lines, _warns(texts)):
        n, low = len(ln.text.split()), ln.text.lower()
        hit = [p for p in banned if re.search(rf"\b{re.escape(p)}\b", low)]
        unknown = _unknown_names(ln.text, known)
        absent, clash = _absent_and_pronoun(ln, facts, story_ids, bible, forms)
        speaker_ok, speaker_reason = _speaker_check(ln, facts, story_ids, bible)
        out[ln.line_id] = [
            LineCheck(rule="absent_character", passed=not absent, severity="block",
                      reason=f"{', '.join(absent)} is not in this scene and not mentioned here"),
            LineCheck(rule="pronoun", passed=not clash, severity="block", reason=clash),
            LineCheck(rule="order", passed=not order, severity="block", reason="; ".join(order)),
            LineCheck(rule="word_budget", passed=MIN_WORDS <= n <= MAX_WORDS, severity="block",
                      reason=f"{n} words, allowed {MIN_WORDS}-{MAX_WORDS}"),
            LineCheck(rule="banned_phrase", passed=not hit, severity="block", reason=", ".join(hit)),
            LineCheck(rule="unknown_name", passed=not unknown, severity="block", reason=", ".join(unknown)),
            LineCheck(rule="raw_unknown_label", passed=not _UNKNOWN.search(ln.text), severity="block",
                      reason="raw unknown_<n> label in line"),
            LineCheck(rule="speaker", passed=speaker_ok, severity="block", reason=speaker_reason),
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
