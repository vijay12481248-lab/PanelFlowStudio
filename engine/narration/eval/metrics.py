"""Gold-set metrics: grounded, coverage, invented names, fallback share, preference vs the reference script."""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone

from engine.narration.artifacts import PanelFacts, _Strict
from engine.narration.eval import gold
from engine.narration.inputs import load_chapter_inputs_from_dir
from engine.narration.runtime.prompts import load_prompt
from engine.narration.steps._cached import cached_call
from engine.narration.steps.critique.judges import PairVerdict

PAIR_STEP = "eval_pair"
# (metric, higher is better, section 1.5 target)
TARGETS = {"grounded": 0.95, "coverage": 0.95, "preference": 0.55}


class ChapterMetrics(_Strict):
    slug: str = ""
    grounded: float
    coverage: float
    hallucinated_names: int
    fallback_share: float
    preference: float | None = None


class EvalReport(_Strict):
    created: str
    chapters: list[ChapterMetrics]
    totals: ChapterMetrics
    spotcheck: list[dict]


async def preference(result, reference: list[dict], compiler) -> float | None:
    """Per scene, compiler lines vs reference lines, judged in both orders. Win rate over all judgments."""
    prompt = load_prompt(PAIR_STEP, "v1")
    ours = {ln.panel_id: ln.text for ln in result.script.lines}
    ref = {}
    for r in reference:
        ref.setdefault(r["panel_id"], []).append(r["text"])
    items = []  # (compiler_is_A, rendered prompt)
    for sc in result.beat_sheet.scenes:
        ids = [p for b in sc.beats for p in b.panel_ids]
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


async def run_eval(slugs: list[str] | None, compiler_factory) -> EvalReport:
    root = gold.gold_root()
    slugs = slugs or sorted(p.name for p in root.iterdir() if (p / "meta.json").exists())
    chapters, pool = [], []
    for slug in slugs:
        d = root / slug
        facts = [PanelFacts.model_validate(f) for f in json.loads((d / "facts.json").read_text(encoding="utf-8"))]
        reference = json.loads((d / "reference.json").read_text(encoding="utf-8"))["lines"]
        compiler = compiler_factory()
        res = await compiler.run(load_chapter_inputs_from_dir(d), root / "_work" / slug, facts_override=facts)
        if res.script is None or res.critique is None:  # stopped before a script existed: worst case
            chapters.append(ChapterMetrics(slug=slug, grounded=0, coverage=0, hallucinated_names=0, fallback_share=1))
            continue
        n = len(res.script.lines)
        crit = {lc.line_id: lc for lc in res.critique.lines}
        verdict = {i: next((c for c in lc.checks if c.rule == "grounded"), None) for i, lc in crit.items()}
        for ln in res.script.lines:
            g = verdict.get(ln.line_id)
            pool.append({"slug": slug, "line_id": ln.line_id, "text": ln.text,
                         "grounded": bool(g and g.passed), "reason": g.reason if g else ""})
        chapters.append(ChapterMetrics(
            slug=slug,
            grounded=sum(bool(g and g.passed) for g in verdict.values()) / n,
            coverage=res.critique.coverage,
            hallucinated_names=sum(c.rule == "unknown_name" and not c.passed for lc in crit.values() for c in lc.checks),
            fallback_share=sum(ln.status == "fallback" for ln in res.script.lines) / n,
            preference=await preference(res, reference, compiler)))
    prefs = [c.preference for c in chapters if c.preference is not None]
    totals = ChapterMetrics(
        slug="ALL", grounded=_mean([c.grounded for c in chapters]), coverage=_mean([c.coverage for c in chapters]),
        hallucinated_names=sum(c.hallucinated_names for c in chapters),
        fallback_share=_mean([c.fallback_share for c in chapters]),
        preference=_mean(prefs) if prefs else None)
    spot = random.Random(0).sample(pool, min(20, len(pool)))
    return EvalReport(created=datetime.now(timezone.utc).isoformat(), chapters=chapters, totals=totals, spotcheck=spot)


def compare(current: EvalReport, baseline: EvalReport, tolerance: float = 0.02) -> list[str]:
    base = {c.slug: c for c in baseline.chapters}
    out = []
    for c in current.chapters:
        b = base.get(c.slug)
        if b is None:
            continue
        for name in ("grounded", "coverage", "preference"):
            cur, old = getattr(c, name), getattr(b, name)
            if cur is not None and old is not None and cur < old - tolerance:
                out.append(f"{c.slug}: {name} fell {old:.2f} -> {cur:.2f}")
        if c.fallback_share > b.fallback_share + tolerance:
            out.append(f"{c.slug}: fallback_share rose {b.fallback_share:.2f} -> {c.fallback_share:.2f}")
        if c.hallucinated_names > b.hallucinated_names:
            out.append(f"{c.slug}: hallucinated_names rose {b.hallucinated_names} -> {c.hallucinated_names}")
    return out
