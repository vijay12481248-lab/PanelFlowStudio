"""The anatomy review of one picture: zoomed tiles and pose questions to each judge, deterministic rules, and honest confidence.

Each judge LISTS the hands and feet it sees on the whole picture and on every tile (the code counts the lines) and answers a short flags question. A defect is
`confirmed` when two judges both report it. A count defect (extra hands or feet) is also confirmed when ONE judge reports it from two different views, the whole picture
and a zoomed tile: measured on real pictures, Qwen3-VL 8B undercounts extra hands while qwen3.5:9b finds them, so requiring both judges would confirm nothing. Anything
reported once is `suspected` (kept and flagged, never a reason to redraw), and a picture is `unverified` when no judge gave a usable whole-picture answer. `clean`
therefore always means "a judge looked and nothing was confirmed", never "nobody looked".
"""
from __future__ import annotations

import time
from typing import Callable, Literal

from pydantic import BaseModel, Field

from engine.original.anatomy.questions import (ENUM_PROMPT, TILE_FLAGS_PROMPT, WHOLE_FLAGS_PROMPT, Answer, parse_enum_reply, parse_flags_reply, parse_yes_no,
                                               pose_prompt)
from engine.original.anatomy.rules import COUNT_KINDS, Defect, judge_defects, pose_asks, text_requested
from engine.original.anatomy.tiles import make_tiles
from engine.original.judges import Judge


class AnatomyReport(BaseModel):
    status: Literal["clean", "defects", "unverified"]
    confirmed: list[Defect] = Field(default_factory=list)
    suspected: list[Defect] = Field(default_factory=list)
    people: int | None = None
    judges: list[str] = Field(default_factory=list)  # the judges that gave a usable whole-picture answer
    counts_skipped: bool = False  # the judges disagree on how many people there are: counts are not judged
    pose_skipped: list[str] = Field(default_factory=list)
    seconds: float = 0.0


async def _view(judge: Judge, png: bytes, tile: str, flags_prompt: str) -> Answer:
    answer = parse_flags_reply(await judge.ask(png, flags_prompt), judge.name, tile)
    answer.hands, answer.feet = parse_enum_reply(await judge.ask(png, ENUM_PROMPT))
    answer.ok = answer.ok or answer.hands is not None or answer.feet is not None
    return answer


async def _one_judge(judge: Judge, image: bytes, asks: list[tuple[str, str]]) -> tuple[list[Answer], dict[str, bool | None]]:
    whole_tile = make_tiles(image)[0]
    whole = await _view(judge, whole_tile.png, "whole", WHOLE_FLAGS_PROMPT)
    answers = [whole]
    for tile in make_tiles(image, people=whole.people)[1:]:
        answers.append(await _view(judge, tile.png, tile.name, TILE_FLAGS_PROMPT))
    poses = {key: parse_yes_no(await judge.ask(whole_tile.png, pose_prompt(question))) for key, question in asks}
    return answers, poses


def _key(d: Defect) -> tuple[str, str | None]:
    return d.kind, d.pose


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

    reports: dict[tuple[str, str | None], dict[str, list[Defect]]] = {}  # key -> judge -> defects
    for name, answers, poses in usable:
        defects = judge_defects(answers, None if counts_skipped else people, poses, text_asked=asked_text, judge=name)
        for d in defects:
            reports.setdefault(_key(d), {}).setdefault(name, []).append(d)
    confirmed: list[Defect] = []
    suspected: list[Defect] = []
    for key, by_judge in reports.items():
        first = next(iter(by_judge.values()))[0]
        two_judges = len(by_judge) >= 2
        two_views = key[0] in COUNT_KINDS and any(len({d.tile for d in ds}) >= 2 for ds in by_judge.values())
        (confirmed if two_judges or two_views else suspected).append(first)
    return AnatomyReport(status="defects" if confirmed else "clean", confirmed=confirmed, suspected=suspected, people=people, judges=[n for n, _, _ in usable],
                         counts_skipped=counts_skipped, pose_skipped=skipped, seconds=round(time.monotonic() - t0, 1))
