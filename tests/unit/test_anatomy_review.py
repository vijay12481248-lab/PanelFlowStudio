import asyncio
import io

from PIL import Image

from engine.original.anatomy.questions import TILE_PROMPT, WHOLE_PROMPT
from engine.original.anatomy.review import AnatomyReport, review_picture

CLEAN_WHOLE = "PEOPLE: 1\nARMS: 2\nHANDS: 2\nLEGS: 2\nFEET: 2\nTEXT: no\nDOUBLE: no\nMERGED: no\nEVIDENCE: two hands on the knees"
FOUR_HANDS_WHOLE = CLEAN_WHOLE.replace("ARMS: 2", "ARMS: 4").replace("HANDS: 2", "HANDS: 4")
CLEAN_TILE = "ARMS: 1\nHANDS: 1\nLEGS: 0\nFEET: 0\nTEXT: no\nDOUBLE: no\nEVIDENCE: a hand on a knee"


def png():
    buf = io.BytesIO()
    Image.new("RGB", (768, 1344), "orange").save(buf, "PNG")
    return buf.getvalue()


class Fake:
    def __init__(self, name, whole=CLEAN_WHOLE, tile=CLEAN_TILE, pose="Yes, clearly"):
        self.name, self.whole, self.tile, self.pose = name, whole, tile, pose
        self.calls = 0

    async def ask(self, image, prompt):
        self.calls += 1
        if prompt == WHOLE_PROMPT:
            return self.whole
        if prompt == TILE_PROMPT:
            return self.tile
        return self.pose


def run(judges, prompt="", **kw):
    return asyncio.run(review_picture(judges, png(), prompt, **kw))


def test_both_judges_reporting_four_hands_confirm_the_defect():
    r = run([Fake("a", whole=FOUR_HANDS_WHOLE), Fake("b", whole=FOUR_HANDS_WHOLE)])
    assert isinstance(r, AnatomyReport) and r.status == "defects"
    assert {d.kind for d in r.confirmed} == {"extra_arms", "extra_hands"} and r.suspected == [] and r.judges == ["a", "b"]


def test_one_judge_only_suspects_and_the_picture_stays_clean():
    r = run([Fake("a", whole=FOUR_HANDS_WHOLE), Fake("b")])
    assert r.status == "clean" and r.confirmed == [] and {d.kind for d in r.suspected} == {"extra_arms", "extra_hands"}


def test_a_lone_judge_never_confirms():
    r = run([Fake("a", whole=FOUR_HANDS_WHOLE)])
    assert r.status == "clean" and r.confirmed == [] and len(r.suspected) == 2


def test_judges_that_give_no_usable_answer_make_the_picture_unverified_not_clean():
    r = run([Fake("a", whole="I think it looks nice", tile="hmm", pose="maybe"), Fake("b", whole="", tile="", pose="")])
    assert r.status == "unverified" and r.judges == []


def test_a_missing_pose_confirmed_by_both_judges():
    r = run([Fake("a", pose="No, her hands are in her lap"), Fake("b", pose="No")], prompt="a woman sitting cross-legged, hands resting on her knees")
    assert r.status == "defects" and {d.pose for d in r.confirmed} == {"cross_legged", "hands_on_knees"}


def test_disagreeing_people_counts_skip_count_rules_but_not_pose_checks():
    r = run([Fake("a", whole=FOUR_HANDS_WHOLE, pose="No"), Fake("b", whole=FOUR_HANDS_WHOLE.replace("PEOPLE: 1", "PEOPLE: 2"), pose="No")],
            prompt="sitting cross-legged")
    assert r.counts_skipped is True and r.people is None
    assert {d.kind for d in r.confirmed} == {"pose_missing"}


def test_between_is_called_once_between_two_judges_and_pose_skips_are_reported():
    calls = []
    r = run([Fake("a"), Fake("b")], prompt="a cat on a table", between=lambda: calls.append(1))
    assert calls == [1] and r.pose_skipped == ["no pose word from the list"] and r.status == "clean"


def test_two_people_get_half_tiles_so_more_questions_are_asked():
    one, two = Fake("a"), Fake("a", whole=CLEAN_WHOLE.replace("PEOPLE: 1", "PEOPLE: 2"))
    run([one])
    run([two])
    assert two.calls == one.calls + 2
