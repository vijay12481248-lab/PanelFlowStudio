"""CLI: python -m engine.narration run <project_id> [--stop-after perceive|understand|write]"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from engine.database.models import ProjectRecord
from engine.database.session import SessionLocal
from engine.llm.registry import llm_registry
from engine.narration.bible.store import BibleStore
from engine.narration.cache import ArtifactCache
from engine.narration.compiler import NarrationCompiler
from engine.narration.inputs import load_chapter_inputs
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


def _make_compiler(provider, cache_dir: Path, bibles: BibleStore) -> NarrationCompiler:
    roles = load_roles()
    return NarrationCompiler(
        ProviderModelClient(provider, roles),
        ModelScheduler(roles, ollama_unloader(provider.endpoint_url)),
        ArtifactCache(cache_dir),
        bibles,
    )


async def _run(project_id: str, stop_after: str) -> int:
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
        print(f"bible version: {review.approve(run_dir, BibleStore()).version}")
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 1
    return 0


def _gold(args) -> int:
    from engine.narration.eval.gold import add_gold

    try:
        print(add_gold(args.project_id, args.slug))
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
    work = gold.gold_root() / "_work"  # own cache and bibles: never touches real series bibles
    report = await run_eval(args.slug, lambda: _make_compiler(provider, work / "cache", BibleStore(work / "bibles")))
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
    run.add_argument("--stop-after", choices=["perceive", "understand", "write"], default="write")
    rv = sub.add_parser("review").add_subparsers(dest="action", required=True)
    rv.add_parser("list")
    rv.add_parser("approve").add_argument("run_dir")
    gd = sub.add_parser("gold").add_subparsers(dest="action", required=True)
    add = gd.add_parser("add")
    add.add_argument("project_id")
    add.add_argument("slug")
    ev = sub.add_parser("eval")
    ev.add_argument("--slug", action="append")
    ev.add_argument("--baseline")
    ev.add_argument("--out")
    args = ap.parse_args(argv)
    if args.cmd == "gold":
        return _gold(args)
    if args.cmd == "eval":
        return asyncio.run(_eval(args))
    if args.cmd == "review":
        return _review(args)
    return asyncio.run(_run(args.project_id, args.stop_after))


if __name__ == "__main__":
    sys.exit(main())
