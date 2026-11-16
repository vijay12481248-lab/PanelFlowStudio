"""Draw, check, redraw: the picture is reviewed after every draw and redrawn with a new seed while a defect is confirmed, within an attempt and time budget.

Blocking (callers in async code run it in a thread). The first picture that is clean wins; a picture the judges could not verify is delivered as `unverified` and never
redrawn (a redraw would be a coin flip); when every attempt has confirmed defects the one with the fewest is delivered as `best_effort`, with its report. Active
lessons are appended to the prompt, the first attempt's confirmed defects become lessons, and every attempt is appended to the knowledge records.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel

from engine.comfyui.art import ART_WORKFLOW_ID
from engine.creative.mistakes import MistakeLedger
from engine.original.anatomy.lessons import record_report, rules_for
from engine.original.anatomy.review import AnatomyReport, review_picture
from engine.original.anatomy.store import append_check

SEED_STEP = 7919  # the same step the Scene Director uses between attempts


class AnatomyBudget(BaseModel):
    max_attempts: int = 4
    max_seconds: float = 240.0  # no new attempt starts after this


@dataclass
class CheckedPicture:
    png: bytes
    report: AnatomyReport
    status: Literal["clean", "best_effort", "unverified"]
    seed: int
    prompt: str
    attempts: list[dict] = field(default_factory=list)  # per attempt: seed, status, confirmed kinds (no picture bytes)


def generate_checked(art_engine, judges, *, prompt: str, width: int, height: int, seed: int, prefix: str, workflow_id: str = ART_WORKFLOW_ID,
                     reference_images=None, budget: AnatomyBudget = AnatomyBudget(), ledger: MistakeLedger | None = None, record_path: Path | None = None,
                     between: Callable[[], None] | None = None) -> CheckedPicture:
    t0 = time.monotonic()
    rules = rules_for(ledger, workflow_id, prompt) if ledger else ""
    full_prompt = f"{prompt} Remember: {rules}" if rules else prompt
    kept: list[tuple[bytes, AnatomyReport, int]] = []
    attempts: list[dict] = []
    for i in range(budget.max_attempts):
        if i > 0 and time.monotonic() - t0 > budget.max_seconds:
            break
        s = seed + i * SEED_STEP
        try:
            extra = {"reference_images": reference_images} if reference_images else {}
            art = art_engine.generate(full_prompt, "", width, height, s, prefix, workflow_id=workflow_id, **extra)
        except Exception:
            if not kept:
                raise  # nothing was drawn yet: nothing to deliver
            break
        report = asyncio.run(review_picture(judges, art.png, prompt, between=between))
        kept.append((art.png, report, s))
        attempts.append({"attempt": i, "seed": s, "status": report.status, "confirmed": [d.kind for d in report.confirmed]})
        if record_path is not None:
            append_check(record_path, model=workflow_id, picture=f"{prefix}:{s}", prompt=full_prompt, rules_used=bool(rules), report=report.model_dump(mode="json"), attempt=i)
        if report.status != "defects":
            break
    if ledger:
        record_report(ledger, workflow_id, kept[0][1])
    last = kept[-1]
    if last[1].status == "clean":
        png, report, s = last
        return CheckedPicture(png=png, report=report, status="clean", seed=s, prompt=full_prompt, attempts=attempts)
    if last[1].status == "unverified":
        png, report, s = last
        return CheckedPicture(png=png, report=report, status="unverified", seed=s, prompt=full_prompt, attempts=attempts)
    png, report, s = min(kept, key=lambda k: len(k[1].confirmed))  # min keeps the earliest on ties
    return CheckedPicture(png=png, report=report, status="best_effort", seed=s, prompt=full_prompt, attempts=attempts)
