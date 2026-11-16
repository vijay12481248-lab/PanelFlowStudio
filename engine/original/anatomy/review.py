"""The anatomy review of one picture: zoomed tiles and pose questions to each judge, deterministic rules, and honest confidence.

A defect is `confirmed` only when two judges both report it; one judge alone makes it `suspected` (kept and flagged, never a reason to redraw); a picture is
`unverified` when no judge gave a usable whole-picture answer. `clean` therefore always means "a judge looked and nothing was confirmed", never "nobody looked".
"""
from __future__ import annotations

import time
from typing import Callable, Literal

from pydantic import BaseModel, Field

from engine.original.anatomy.questions import TILE_PROMPT, WHOLE_PROMPT, Answer, parse_reply, parse_yes_no, pose_prompt
from engine.original.anatomy.rules import Defect, judge_defects, pose_asks, text_requested
from engine.original.anatomy.tiles import make_tiles
from engine.original.judges import Judge


class AnatomyReport(BaseModel):
    status: Literal["clean", "defects", "unverified"]
    confirmed: list[Defect] = Field(default_factory=list)
    suspected: list[Defect] = Field(default_factory=list)
    people: int | None = None
    judges: list[str] = Field(default_factory=list)  # the judges that gave a usable whole-picture answer
    counts_skipped: bool = False  # the judges disagree on how many people there are: limb counts are not judged
    pose_skipped: list[str] = Field(default_factory=list)
    seconds: float = 0.0


async def _one_judge(judge: Judge, image: bytes, asks: list[tuple[str, str]]) -> tuple[list[Answer], dict[str, bool | None]]:
    whole_tile = make_tiles(image)[0]
    whole = parse_reply(await judge.ask(whole_tile.png, WHOLE_PROMPT), judge.name, "whole")
    answers = [whole]
    for tile in make_tiles(image, people=whole.people)[1:]:
        answers.append(parse_reply(await judge.ask(tile.png, TILE_PROMPT), judge.name, tile.name))
    poses = {key: parse_yes_no(await judge.ask(whole_tile.png, pose_prompt(question))) for key, question in asks}
    return answers, poses


async def review_picture(judges: list[Judge], image: bytes, prompt: str = "", *, between: Callable[[], None] | None = None) -> AnatomyReport:
    t0 = time.monotonic()
    asks, skipped = pose_asks(prompt)
    asked_text = text_requested(prompt)
    per_judge: list[tuple[str, list[Answer], dict[str, bool | None]]] = []
    for i, judge in enumerate(judges):
        answers, poses = await _one_judge(judge, image, asks)
        per_judge.append((judge.name, answers, poses))
        if between and i < len(judges) - 1:
            between()
    usable = [(n, a, p) for n, a, p in per_judge if a and a[0].ok]
    seen_people = {a[0].people for _, a, _ in usable if a[0].people is not None}
    counts_skipped = len(seen_people) > 1
    people = next(iter(seen_people)) if len(seen_people) == 1 else None
    if not usable:
        return AnatomyReport(status="unverified", pose_skipped=skipped, seconds=round(time.monotonic() - t0, 1))

    reported: dict[tuple[str, str | None], list[Defect]] = {}
    for name, answers, poses in usable:
        defects = judge_defects(answers, people, poses, text_asked=asked_text, judge=name)
        if counts_skipped:
            defects = [d for d in defects if not d.kind.startswith("extra_")]
        for key in {(d.kind, d.pose) for d in defects}:
            reported.setdefault(key, []).append(next(d for d in defects if (d.kind, d.pose) == key))
    confirmed = [ds[0] for ds in reported.values() if len(ds) >= 2]
    suspected = [ds[0] for ds in reported.values() if len(ds) < 2]
    return AnatomyReport(status="defects" if confirmed else "clean", confirmed=confirmed, suspected=suspected, people=people, judges=[n for n, _, _ in usable],
                         counts_skipped=counts_skipped, pose_skipped=skipped, seconds=round(time.monotonic() - t0, 1))
