"""CLI: python -m engine.narration run <project_id> [--stop-after perceive|understand|write|perform|voice|timeline] [--apply]"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from engine.database.models import ProjectRecord
from engine.database.session import SessionLocal
from engine.llm.providers.openai_compatible import OpenAICompatibleProvider
from engine.llm.registry import llm_registry
from engine.narration.bible.store import BibleStore
from engine.narration.cache import ArtifactCache
from engine.narration.compiler import NarrationCompiler
from engine.narration.inputs import load_chapter_inputs
from engine.narration.project import apply_to_project
from engine.narration.runtime.client import ProviderModelClient
from engine.narration.runtime.roles import load_roles
from engine.narration.runtime.scheduler import ModelScheduler, ollama_unloader

_EXIT = {"pass": 0, "review": 2, "failed": 1}


async def _local_provider():
    provider = llm_registry.get_ollama_provider()  # local-only: never falls through to cloud or mock
    if not await provider.health_check():
        print(f"Ollama is not reachable at {provider.endpoint_url}")
        return None
    return provider


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai"


def _hosted_providers(roles) -> dict:
    """Roles the user switched to provider: gemini. Needs an AI Studio / Vertex API key in GEMINI_API_KEY."""
    wanted = {name: r for name, r in roles.items() if r.provider == "gemini"}
    if not wanted:
        return {}
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(f"roles {', '.join(wanted)} use Gemini but GEMINI_API_KEY is not set")
    return {name: OpenAICompatibleProvider(GEMINI_ENDPOINT, r.model, key, timeout=r.timeout_s, provider_id="gemini",
                                           display_name="Google Gemini API") for name, r in wanted.items()}


def _make_compiler(provider, cache_dir: Path, bibles: BibleStore) -> NarrationCompiler:
    roles = load_roles()
    return NarrationCompiler(
        ProviderModelClient(provider, roles, overrides=_hosted_providers(roles)),
        ModelScheduler(roles, ollama_unloader(provider.endpoint_url)),
        ArtifactCache(cache_dir),
        bibles,
    )


async def _run(project_id: str, stop_after: str, apply: bool = False) -> int:
    try:
        with SessionLocal() as db:
            inputs = load_chapter_inputs(db, project_id)
            workspace = Path(db.get(ProjectRecord, project_id).workspace_path)
    except KeyError:
        print(f"project not found: {project_id}")
        return 1
    except ValueError as exc:
        print(str(exc))
        return 1
    provider = await _local_provider()
    if provider is None:
        return 1
    compiler = _make_compiler(provider, workspace / "narration" / "cache", BibleStore())
    res = await compiler.run(inputs, workspace, stop_after=stop_after)
    print(f"gate: {res.gate}")
    for r in res.reasons:
        print(f"reason: {r}")
    print(f"run_dir: {res.run_dir}")
    if res.facts is not None:
        print(f"story panels: {sum(f.is_story for f in res.facts)}")
        print(f"needs-review panels: {sum(f.needs_review for f in res.facts)}")
    if res.beat_sheet is not None:
        print(f"scenes: {len(res.beat_sheet.scenes)}")
    if res.script is not None:
        print(f"lines: {len(res.script.lines)}")
        print(f"fallbacks: {sum(ln.status == 'fallback' for ln in res.script.lines)}")
    if res.critique is not None:
        print(f"coverage: {res.critique.coverage:.2f}")
    if res.sync is not None:
        met = res.sync["targets_met"]
        for k, v in res.sync.items():
            if k != "targets_met":
                print(f"sync {k}: {v:.3g}")
        for k, ok in met.items():
            print(f"target {k}: {'met' if ok else 'not met'}")
    if apply and res.gate == "pass":
        with SessionLocal() as db:
            print(f"video script: {apply_to_project(db, project_id, res.timeline, res.script, res.beat_sheet, res.takes, workspace, res.plan)}")
    if res.readiness is not None:
        print(f"readiness: {'ready' if res.readiness.ready else 'not ready'}")
        for issue in res.readiness.issues:
            print(f"  {issue.severity}: {issue.detail}")
    return _EXIT[res.gate]


def _review(args) -> int:
    from engine.narration import review

    with SessionLocal() as db:
        spaces = {Path(p.workspace_path).resolve() for p in db.query(ProjectRecord)}
    if args.action == "list":
        for root in sorted({w.parent for w in spaces}):
            for i in review.list_pending(root):
                print(f"{i.run_dir}\t{i.project_id}\t{'; '.join(i.reasons)}")
        return 0
    run_dir = Path(args.run_dir).resolve()
    if not any(w in run_dir.parents for w in spaces):
        print(f"not inside a known project workspace: {args.run_dir}")
        return 1
    try:
        item = review.ReviewItem.model_validate_json((run_dir / "review.json").read_text(encoding="utf-8"))
        if item.status == "approved" and not (run_dir / "continued.json").exists():
            approval = review.Approval(BibleStore().load(item.series_key), True)  # stranded approve: only continue is missing
        else:
            approval = review.approve(run_dir, BibleStore())
        print(f"bible version: {approval.bible.version}")
        if approval.needs_continue:
            print(f"video script: {asyncio.run(review.continue_after_approval(item.project_id, run_dir.name))}")
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        print(str(exc))
        return 1
    return 0


def _gold(args) -> int:
    from engine.narration.eval.gold import add_gold

    try:
        print(add_gold(args.project_id, args.slug, args.kind))
    except (KeyError, ValueError, FileExistsError) as exc:
        print(str(exc))
        return 1
    return 0


async def _eval(args) -> int:
    from datetime import datetime

    from engine.narration.eval import gold
    from engine.narration.eval.metrics import EvalReport, compare, run_eval
    from engine.narration.eval.report import write_report

    provider = await _local_provider()
    if provider is None:
        return 1
    work = gold.gold_root() / "_work"  # own cache; run_eval hands each chapter a fresh temporary bible store
    try:
        report = await run_eval(args.slug, lambda bibles: _make_compiler(provider, work / "cache", bibles))
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc))
        return 1
    out = Path(args.out) if args.out else gold.gold_root() / "_reports" / datetime.now().strftime("%Y%m%dT%H%M%S")
    print(f"report: {write_report(report, out)[1]}")
    if not args.baseline:
        return 0
    regressions = compare(report, EvalReport.model_validate_json(Path(args.baseline).read_text(encoding="utf-8")))
    for r in regressions:
        print(f"regression: {r}")
    return 2 if regressions else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m engine.narration")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("project_id")
    run.add_argument("--stop-after", choices=["perceive", "understand", "write", "perform", "voice", "timeline"])
    run.add_argument("--apply", action="store_true", help="project the locked timeline into the project (runs to timeline)")
    rv = sub.add_parser("review").add_subparsers(dest="action", required=True)
    rv.add_parser("list")
    rv.add_parser("approve").add_argument("run_dir")
    fs = sub.add_parser("fewshot").add_subparsers(dest="action", required=True)
    fr = fs.add_parser("refresh")
    fr.add_argument("series_key", nargs="?")
    fr.add_argument("--all", action="store_true", help="refresh every series that has recorded pairs")
    gd = sub.add_parser("gold").add_subparsers(dest="action", required=True)
    add = gd.add_parser("add")
    add.add_argument("project_id")
    add.add_argument("slug")
    add.add_argument("--kind", choices=["manhua", "manhwa", "webtoon"], default="manhwa")
    ev = sub.add_parser("eval")
    ev.add_argument("--slug", action="append")
    ev.add_argument("--baseline")
    ev.add_argument("--out")
    args = ap.parse_args(argv)
    if args.cmd == "fewshot":
        from engine.narration import learning

        keys = learning._series_keys() if args.all else [args.series_key]
        if not keys or keys == [None]:
            print("give a series_key or --all")
            return 1
        for key in keys:
            try:
                path = learning.refresh_fewshot(key)
            except ValueError as exc:
                print(str(exc))
                return 1
            print(path if path else f"{key}: not enough edits yet ({len(learning._usable_pairs(key))}/5)")
        return 0
    if args.cmd == "gold":
        return _gold(args)
    if args.cmd == "eval":
        return asyncio.run(_eval(args))
    if args.cmd == "review":
        return _review(args)
    if args.apply and args.stop_after not in (None, "timeline"):
        print("--apply needs the full run: use --stop-after timeline or leave it out")
        return 1
    return asyncio.run(_run(args.project_id, "timeline" if args.apply else args.stop_after or "write", args.apply))


if __name__ == "__main__":
    sys.exit(main())
