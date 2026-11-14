"""Task 2 of the review-page plan: the structured cross-check between two judges (scripted fake judges, no GPU)."""
import asyncio

from engine.original.crosscheck import cross_check
from engine.original.judges import JudgeAnswer

STATES = ["striking", "blocking", "readying", "grieving", "lost"]


def ans(judge, camera="level", people=2, actions=("striking", "blocking"), evidence="a clear view of both people", ok=True):
    return JudgeAnswer(judge=judge, ok=ok, camera=camera, people=people, actions=list(actions), evidence=evidence)


class Script:
    """A judge that returns a prepared first answer and prepared re-look answers, and records what it was asked."""

    def __init__(self, name, first, rereads=None, raises=False):
        self.name, self.first, self.rereads, self.raises = name, first, rereads or {}, raises
        self.reread_calls = []

    async def read(self, image, states):
        if self.raises:
            raise RuntimeError("judge exploded")
        return self.first

    async def reread(self, image, topic, index, other, states):
        self.reread_calls.append((topic, index, other.judge))
        return self.rereads.get((topic, index), JudgeAnswer(judge=self.name, ok=False))


def run(*a, **k):
    return asyncio.run(cross_check(*a, **k))


def item(cc, key):
    return next(i for i in cc.items if i.key == key)


def test_agreement_needs_no_second_round():
    a, b = Script("A", ans("A")), Script("B", ans("B"))
    cc = run([a, b], b"png", STATES)
    assert a.reread_calls == [] and b.reread_calls == []
    assert {i.key for i in cc.items} == {"camera", "people", "action:0", "action:1"}
    assert all(i.status == "agreed" and i.confidence == 0.9 for i in cc.items)
    assert item(cc, "camera").value == "level" and cc.judges == ["A", "B"] and not cc.single_judge


def test_a_disagreement_that_both_resolve():
    a = Script("A", ans("A", camera="level"), {("camera", None): ans("A", camera="looks_up", evidence="the faces are seen from below clearly")})
    b = Script("B", ans("B", camera="looks_up"), {("camera", None): ans("B", camera="looks_up", evidence="the horizon sits below the shoulders here")})
    cc = run([a, b], b"png", STATES)
    cam = item(cc, "camera")
    assert cam.status == "resolved" and cam.value == "looks_up" and cam.confidence == 0.7
    assert cam.answers["A"]["round1"] == "level" and cam.answers["A"]["round2"] == "looks_up" and cam.answers["B"]["round2"] == "looks_up"
    assert item(cc, "people").status == "agreed"


def test_a_disagreement_that_stays_is_disputed_with_no_value():
    a = Script("A", ans("A", camera="level"), {("camera", None): ans("A", camera="level", evidence="the horizon is flat across the picture")})
    b = Script("B", ans("B", camera="looks_up"), {("camera", None): ans("B", camera="looks_up", evidence="the faces are seen from below clearly")})
    cam = item(run([a, b], b"png", STATES), "camera")
    assert cam.status == "disputed" and cam.value is None and cam.confidence == 0.3


def test_only_the_disputed_item_is_reread_and_each_judge_sees_the_other_answer():
    a = Script("A", ans("A", camera="level"))
    b = Script("B", ans("B", camera="looks_up"))
    run([a, b], b"png", STATES)
    assert a.reread_calls == [("camera", None, "B")] and b.reread_calls == [("camera", None, "A")]


def test_suspect_flip_is_recorded_when_a_judge_gives_in_without_evidence():
    a = Script("A", ans("A", camera="level", evidence="flat horizon across the middle"), {("camera", None): ans("A", camera="looks_up", evidence="ok")})
    b = Script("B", ans("B", camera="looks_up"), {("camera", None): ans("B", camera="looks_up", evidence="faces seen from below with a low horizon")})
    cam = item(run([a, b], b"png", STATES), "camera")
    assert cam.status == "resolved" and cam.suspect_flips == ["A"]


def test_flip_with_new_evidence_is_not_suspect():
    a = Script("A", ans("A", camera="level", evidence="flat horizon across the middle"),
               {("camera", None): ans("A", camera="looks_up", evidence="looking again the chins are visible from underneath")})
    b = Script("B", ans("B", camera="looks_up"), {("camera", None): ans("B", camera="looks_up", evidence="faces seen from below with a low horizon")})
    assert item(run([a, b], b"png", STATES), "camera").suspect_flips == []


def test_one_judge_down_gives_single_judge_items():
    cc = run([Script("A", ans("A")), Script("B", ans("B", ok=False))], b"png", STATES)
    assert cc.single_judge and cc.judges == ["A"]
    assert all(i.status == "single" and i.confidence == 0.5 and i.value is not None for i in cc.items)


def test_both_judges_unusable_gives_unjudged_zero_confidence():
    cc = run([Script("A", ans("A", ok=False, camera=None, people=None, actions=())), Script("B", ans("B", ok=False, camera=None, people=None, actions=()))], b"png", STATES)
    assert cc.judges == [] and not cc.single_judge
    assert cc.items and all(i.status == "unjudged" and i.confidence == 0.0 and i.value is None for i in cc.items)


def test_a_judge_that_raises_is_dropped_not_fatal():
    cc = run([Script("A", ans("A"), raises=True), Script("B", ans("B"))], b"png", STATES)
    assert cc.judges == ["B"] and cc.single_judge


def test_actions_compare_with_state_groups():
    groups = [{"grieving", "lost"}]
    same = lambda x, y: x == y or any(x in g and y in g for g in groups)
    cc = run([Script("A", ans("A", people=1, actions=("grieving",))), Script("B", ans("B", people=1, actions=("lost",)))], b"png", STATES, same_state=same)
    assert item(cc, "action:0").status == "agreed"
    cc2 = run([Script("A", ans("A", people=1, actions=("grieving",))), Script("B", ans("B", people=1, actions=("striking",)))], b"png", STATES, same_state=same)
    assert item(cc2, "action:0").status in ("disputed", "resolved")


def test_people_count_mismatch_skips_action_items():
    cc = run([Script("A", ans("A", people=2, actions=("striking", "blocking"))), Script("B", ans("B", people=3, actions=("striking",)))], b"png", STATES)
    assert not any(i.key.startswith("action:") for i in cc.items)
    assert item(cc, "people").status in ("disputed", "resolved")


def test_between_is_called_between_judges_and_its_failure_is_ignored():
    calls = []

    def between():
        calls.append(1)
        raise RuntimeError("could not unload the model")

    cc = run([Script("A", ans("A")), Script("B", ans("B"))], b"png", STATES, between=between)
    assert len(calls) == 1 and cc.judges == ["A", "B"]
