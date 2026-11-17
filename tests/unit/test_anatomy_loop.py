import json
import time
from types import SimpleNamespace

import pytest

from engine.creative.mistakes import MistakeLedger
from engine.original.anatomy import loop
from engine.original.anatomy.lessons import domain, record_report, rules_for
from engine.original.anatomy.review import AnatomyReport
from engine.original.anatomy.rules import Defect

CLEAN = AnatomyReport(status="clean", judges=["a", "b"])
UNVERIFIED = AnatomyReport(status="unverified")


def defects(n=1, pose=None):
    ds = [Defect(kind="extra_hands", judge="a", tile="whole", detail="x") for _ in range(n)]
    return AnatomyReport(status="defects", confirmed=ds, judges=["a", "b"])


class Art:
    def __init__(self, fail_on=None):
        self.calls, self.fail_on = [], fail_on

    def generate(self, prompt, negative, width, height, seed, prefix, **kw):
        self.calls.append({"prompt": prompt, "seed": seed, **kw})
        if self.fail_on == len(self.calls):
            raise RuntimeError("ComfyUI down")
        return SimpleNamespace(png=f"png{seed}".encode(), width=width, height=height)


@pytest.fixture
def script(monkeypatch):
    def install(*reports):
        queue = list(reports)

        async def fake_review(judges, image, prompt="", **kw):
            return queue.pop(0)

        monkeypatch.setattr(loop, "review_picture", fake_review)
    return install


def go(art, **kw):
    return loop.generate_checked(art, [object()], prompt="a girl sitting", width=768, height=1344, seed=100, prefix="t", **kw)


def test_a_clean_first_picture_is_delivered_after_one_attempt(script):
    script(CLEAN)
    art = Art()
    r = go(art)
    assert r.status == "clean" and len(art.calls) == 1 and r.seed == 100 and r.png == b"png100"


def test_a_confirmed_defect_redraws_with_the_next_seed_until_clean(script):
    script(defects(), CLEAN)
    art = Art()
    r = go(art)
    assert r.status == "clean" and [c["seed"] for c in art.calls] == [100, 100 + 7919] and r.png == b"png8019"


def test_all_attempts_defective_delivers_the_one_with_fewest_confirmed_defects(script):
    script(defects(3), defects(1), defects(2), defects(2))
    r = go(Art())
    assert r.status == "best_effort" and r.png == f"png{100 + 7919}".encode() and len(r.attempts) == 4


def test_an_unverified_picture_is_delivered_as_unverified_and_never_redrawn(script):
    script(UNVERIFIED)
    art = Art()
    r = go(art)
    assert r.status == "unverified" and len(art.calls) == 1


def test_a_draw_failure_after_a_reviewed_picture_still_delivers_it(script):
    script(defects())
    r = go(Art(fail_on=2))
    assert r.status == "best_effort" and r.png == b"png100"


def test_a_draw_failure_on_the_first_attempt_raises(script):
    script()
    with pytest.raises(RuntimeError):
        go(Art(fail_on=1))


def test_the_time_budget_stops_new_attempts(script):
    script(defects(), CLEAN)
    art = Art()
    r = go(art, budget=loop.AnatomyBudget(max_attempts=4, max_seconds=0.0))
    assert len(art.calls) == 1 and r.status == "best_effort"


def test_active_rules_are_appended_to_the_prompt_and_every_attempt_is_recorded(script, tmp_path):
    ledger = MistakeLedger(file_path=tmp_path / "l.json")
    for _ in range(2):
        record_report(ledger, "hidream_i1_fast", defects())
    script(CLEAN)
    art, rec = Art(), tmp_path / "c.jsonl"
    r = go(art, ledger=ledger, record_path=rec)
    assert art.calls[0]["prompt"].startswith("a girl sitting") and " Remember: " in art.calls[0]["prompt"] and "two arms" in art.calls[0]["prompt"]
    lines = [json.loads(x) for x in rec.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1 and lines[0]["rules_used"] is True and lines[0]["status"] == "clean" and r.prompt == art.calls[0]["prompt"]


def test_the_first_attempts_confirmed_defects_become_lessons(script, tmp_path):
    ledger = MistakeLedger(file_path=tmp_path / "l.json")
    script(defects(), CLEAN)
    go(Art(), ledger=ledger)
    assert ledger.load_mistakes(domain("hidream_i1_fast"))[0].recurrence_count == 1


def test_no_ledger_means_the_prompt_is_unchanged(script):
    script(CLEAN)
    art = Art()
    go(art)
    assert art.calls[0]["prompt"] == "a girl sitting"
