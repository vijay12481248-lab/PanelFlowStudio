"""Gold-set metrics: grounded (eval judge), pipeline pass rate, coverage, invented names, fallback share, preference."""
from __future__ import annotations

import json
import random
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from engine.narration.artifacts import PanelFacts, SeriesBible, _Strict
from engine.narration.bible.store import BibleStore, _check_key
from engine.narration.eval import gold
from engine.narration.inputs import load_chapter_inputs_from_dir
from engine.narration.runtime.client import StepModelError
from engine.narration.runtime.prompts import load_prompt
from engine.narration.steps._cached import cached_call
from engine.narration.steps.critique.judges import PairVerdict, Verdict
from engine.narration.steps.critique.rules import _WORD
from engine.narration.steps.factview import char_names, display_name, panel_line

PAIR_STEP = "eval_pair"
GROUNDED_STEP = "eval_grounded"
WINDOW = 30
# (metric, higher is better, section 1.5 target)
TARGETS = {"grounded": 0.95, "coverage": 0.95, "preference": 0.55}
_STOP = {w.lower() for w in "A An The He She They It His Her Their Then But And As When Now With In On At".split()}


class ChapterMetrics(_Strict):
    slug: str = ""
    gate: str = ""
    grounded: float  # eval judge over every final line, fallbacks included
    pipeline_pass: float = 0  # the pipeline's own grounded pass rate
    coverage: float  # equals 1 - fallback_share
    hallucinated_names: int
    fallback_share: float
    preference: float | None = None


class EvalReport(_Strict):
    created: str
    chapters: list[ChapterMetrics]
    totals: ChapterMetrics
    spotcheck: list[dict]


async def preference(result, reference: list[dict], compiler) -> float | None:
    """Per scene window (at most WINDOW panels), compiler lines vs reference lines, judged in both orders."""
    prompt = load_prompt(PAIR_STEP, "v1")
    ours = {ln.panel_id: ln.text for ln in result.script.lines}
    ref = {}
    for r in reference:
        ref.setdefault(r["panel_id"], []).append(r["text"])
    items = []  # (compiler_is_A, rendered prompt)
    for sc in result.beat_sheet.scenes:
        all_ids = [p for b in sc.beats for p in b.panel_ids]
        for w in range(0, len(all_ids), WINDOW):
            ids = all_ids[w:w + WINDOW]
            mine, theirs = " ".join(ours[p] for p in ids if p in ours), " ".join(t for p in ids for t in ref.get(p, []))
            if mine and theirs:
                items += [(True, prompt.render(goal=sc.goal, a=mine, b=theirs)),
                          (False, prompt.render(goal=sc.goal, a=theirs, b=mine))]
    if not items:
        return None

    async def one(item) -> PairVerdict:
        return await cached_call(compiler.client, compiler.cache, "judge", PAIR_STEP, prompt.sha256, item[1], PairVerdict)

    verdicts = await compiler.scheduler.map("judge", items, one)
    return sum((v.winner == "A") == mine_is_a for (mine_is_a, _), v in zip(items, verdicts)) / len(items)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _words(texts) -> set[str]:
    return {w.lower() for t in texts for w in _WORD.findall(t.replace("’", "'"))}


def _invented_names(text: str, known: set[str]) -> int:
    """Every capitalised word counts, the first word of a sentence included."""
    n = 0
    for m in _WORD.finditer(text.replace("’", "'")):
        w = m.group()
        base = w[:-2] if w.lower().endswith("'s") else w
        n += w[0].isupper() and w.lower() not in known and base.lower() not in known
    return n


def _known(bible: SeriesBible, inputs, facts: list[PanelFacts], names: dict[str, str]) -> set[str]:
    texts = [n for c in bible.characters for n in (c.name, *c.aliases)]
    texts += [loc.name for loc in bible.locations] + list(bible.glossary)
    texts += [r.text for p in inputs.panels for r in p.ocr] + [s for p in inputs.panels for s in p.sfx]
    texts += [display_name(c, names) for f in facts for c in (*f.characters_visible, *(d.speaker_id for d in f.dialogue if d.speaker_id))]
    texts += [t for f in facts for t in (f.action, f.setting, *f.names_mentioned, *f.unknown_cues.values())]  # same rule as the pipeline: a name in the gold facts is not invented
    return _words(texts) | _STOP


def _worst(slug: str, gate: str) -> ChapterMetrics:
    return ChapterMetrics(slug=slug, gate=gate, grounded=0, pipeline_pass=0, coverage=0, hallucinated_names=0,
                          fallback_share=1)


async def run_eval(slugs: list[str] | None, compiler_factory) -> EvalReport:
    """compiler_factory(bibles) builds a compiler on a fresh BibleStore seeded from the chapter's gold bible."""
    root = gold.gold_root()
    for s in slugs or []:
        _check_key(s)
    slugs = slugs or sorted(p.name for p in root.iterdir() if (p / "meta.json").exists())
    chapters, pool = [], []
    jprompt = load_prompt(GROUNDED_STEP, "v1")
    for slug in slugs:
        d = root / slug
        facts = [PanelFacts.model_validate(f) for f in json.loads((d / "facts.json").read_text(encoding="utf-8"))]
        reference = json.loads((d / "reference.json").read_text(encoding="utf-8"))["lines"]
        inputs = load_chapter_inputs_from_dir(d)
        with tempfile.TemporaryDirectory() as tmp:
            if (d / "bible.json").exists():
                (Path(tmp) / inputs.series_key).mkdir()
                shutil.copyfile(d / "bible.json", Path(tmp) / inputs.series_key / "bible.json")
            bibles = BibleStore(Path(tmp))
            bible = bibles.load(inputs.series_key)
            compiler = compiler_factory(bibles)
            res = await compiler.run(inputs, root / "_work" / slug, facts_override=facts)
        if res.gate == "failed" or res.script is None or res.critique is None:  # no usable script: worst case
            chapters.append(_worst(slug, res.gate))
            continue
        n = len(res.script.lines)
        by_id = {f.panel_id: f for f in facts}
        names = char_names(bible, res.beat_sheet)
        crit = {lc.line_id: lc for lc in res.critique.lines}
        items = [(ln, jprompt.render(panel=panel_line(1, by_id[ln.panel_id], names), line=ln.text))
                 for ln in res.script.lines]

        async def one(item) -> Verdict:
            return await cached_call(compiler.client, compiler.cache, "judge", GROUNDED_STEP, jprompt.sha256, item[1], Verdict)

        verdicts = await compiler.scheduler.map("judge", items, one)
        for (ln, _), v in zip(items, verdicts):
            pool.append({"slug": slug, "line_id": ln.line_id, "text": ln.text, "facts": panel_line(1, by_id[ln.panel_id], names),
                         "grounded": v.yes, "reason": v.reason})
        known = _known(bible, inputs, facts, names)
        try:
            pref = await preference(res, reference, compiler)
        except StepModelError:
            pref = None
        chapters.append(ChapterMetrics(
            slug=slug, gate=res.gate,
            grounded=sum(v.yes for v in verdicts) / n,
            pipeline_pass=sum(any(c.rule == "grounded" and c.passed for c in lc.checks) for lc in crit.values()) / n,
            coverage=res.critique.coverage,
            hallucinated_names=sum(_invented_names(ln.text, known) for ln in res.script.lines),
            fallback_share=sum(ln.status == "fallback" for ln in res.script.lines) / n,
            preference=pref))
    prefs = [c.preference for c in chapters if c.preference is not None]
    totals = ChapterMetrics(
        slug="ALL", grounded=_mean([c.grounded for c in chapters]), pipeline_pass=_mean([c.pipeline_pass for c in chapters]),
        coverage=_mean([c.coverage for c in chapters]),
        hallucinated_names=sum(c.hallucinated_names for c in chapters),
        fallback_share=_mean([c.fallback_share for c in chapters]),
        preference=_mean(prefs) if prefs else None)
    spot = random.Random(0).sample(pool, min(20, len(pool)))
    return EvalReport(created=datetime.now(timezone.utc).isoformat(), chapters=chapters, totals=totals, spotcheck=spot)


def _diff(label: str, c: ChapterMetrics, b: ChapterMetrics, tolerance: float) -> list[str]:
    out = []
    for name in ("grounded", "pipeline_pass", "coverage", "preference"):
        cur, old = getattr(c, name), getattr(b, name)
        if cur is None and old is not None:
            out.append(f"{label}: {name} went from {old:.2f} to None")
        elif cur is not None and old is not None and cur < old - tolerance:
            out.append(f"{label}: {name} fell {old:.2f} -> {cur:.2f}")
    if c.fallback_share > b.fallback_share + tolerance:
        out.append(f"{label}: fallback_share rose {b.fallback_share:.2f} -> {c.fallback_share:.2f}")
    if c.hallucinated_names > b.hallucinated_names:
        out.append(f"{label}: hallucinated_names rose {b.hallucinated_names} -> {c.hallucinated_names}")
    return out


def compare(current: EvalReport, baseline: EvalReport, tolerance: float = 0.02) -> list[str]:
    cur = {c.slug for c in current.chapters}
    out = [f"{b.slug}: missing from the current run" for b in baseline.chapters if b.slug not in cur]
    base = {c.slug: c for c in baseline.chapters}
    for c in current.chapters:
        if c.slug in base:
            out += _diff(c.slug, c, base[c.slug], tolerance)
    return out + _diff("ALL", current.totals, baseline.totals, tolerance)
