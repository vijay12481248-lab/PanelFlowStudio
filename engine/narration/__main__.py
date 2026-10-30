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
    provider = llm_registry.get_ollama_provider()  # local-only: never falls through to cloud or mock
    if not await provider.health_check():
        print(f"Ollama is not reachable at {provider.endpoint_url}")
        return 1
    roles = load_roles()
    compiler = NarrationCompiler(
        ProviderModelClient(provider, roles),
        ModelScheduler(roles, ollama_unloader(provider.endpoint_url)),
        ArtifactCache(workspace / "narration" / "cache"),
        BibleStore(),
    )
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

    if args.action == "list":
        with SessionLocal() as db:
            roots = {Path(p.workspace_path).parent for p in db.query(ProjectRecord)}
        for root in sorted(roots):
            for i in review.list_pending(root):
                print(f"{i.run_dir}\t{i.project_id}\t{'; '.join(i.reasons)}")
        return 0
    try:
        print(f"bible version: {review.approve(Path(args.run_dir), BibleStore()).version}")
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m engine.narration")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("project_id")
    run.add_argument("--stop-after", choices=["perceive", "understand", "write"], default="write")
    rv = sub.add_parser("review").add_subparsers(dest="action", required=True)
    rv.add_parser("list")
    rv.add_parser("approve").add_argument("run_dir")
    args = ap.parse_args(argv)
    if args.cmd == "review":
        return _review(args)
    return asyncio.run(_run(args.project_id, args.stop_after))


if __name__ == "__main__":
    sys.exit(main())
