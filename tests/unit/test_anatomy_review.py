import asyncio
import io

from PIL import Image

from engine.original.anatomy.questions import ENUM_PROMPT, TILE_FLAGS_PROMPT, WHOLE_FLAGS_PROMPT
from engine.original.anatomy.review import AnatomyReport, review_picture


def png():
    buf = io.BytesIO()
    Image.new("RGB", (768, 1344), "orange").save(buf, "PNG")
    return buf.getvalue()


def hands(n):
    return "\n".join([f"HAND {i + 1}: somewhere" for i in range(n)] + ["FOOT 1: left", "FOOT 2: right"])


class Fake:
    """whole_hands / tile_hands: how many hands this judge lists on the whole picture and on each tile."""

    def __init__(self, name, whole_hands=2, tile_hands=1, people=1, double=False, pose="Yes, clearly", usable=True):
        self.name, self.whole_hands, self.tile_hands, self.people, self.double, self.pose, self.usable = name, whole_hands, tile_hands, people, double, pose, usable
        self.calls, self.mode = 0, "whole"

    async def ask(self, image, prompt):
        self.calls += 1
        if not self.usable:
            return "I think it looks nice"
        if prompt == WHOLE_FLAGS_PROMPT:
            self.mode = "whole"
            return f"PEOPLE: {self.people}\nTEXT: no\nDOUBLE: {'yes' if self.double else 'no'}\nMERGED: no\nEVIDENCE: a person sitting"
        if prompt == TILE_FLAGS_PROMPT:
            self.mode = "tile"
            return f"TEXT: no\nDOUBLE: {'yes' if self.double else 'no'}\nEVIDENCE: a crop"
        if prompt == ENUM_PROMPT:
            return hands(self.whole_hands if self.mode == "whole" else self.tile_hands)
        return self.pose


def run(judges, prompt="", **kw):
    return asyncio.run(review_picture(judges, png(), prompt, **kw))


def test_one_judge_listing_four_hands_on_the_whole_picture_and_on_a_tile_confirms_extra_hands():
    r = run([Fake("a", whole_hands=4, tile_hands=4), Fake("b")])
    assert isinstance(r, AnatomyReport) and r.status == "defects" and {d.kind for d in r.confirmed} == {"extra_hands"} and r.judges == ["a", "b"]


def test_four_hands_seen_in_only_one_view_is_only_suspected():
    r = run([Fake("a", whole_hands=4, tile_hands=2), Fake("b")])
    assert r.status == "clean" and r.confirmed == [] and {d.kind for d in r.suspected} == {"extra_hands"}


def test_both_judges_seeing_the_same_extra_hands_confirm_it_even_in_one_view_each():
    r = run([Fake("a", whole_hands=4, tile_hands=2), Fake("b", whole_hands=4, tile_hands=2)])
    assert r.status == "defects" and {d.kind for d in r.confirmed} == {"extra_hands"}


def test_a_flag_defect_needs_both_judges_one_alone_is_suspected():
    r = run([Fake("a", double=True), Fake("b")])
    assert r.status == "clean" and r.confirmed == [] and {d.kind for d in r.suspected} == {"duplicate_object"}
    r = run([Fake("a", double=True), Fake("b", double=True)])
    assert r.status == "defects" and {d.kind for d in r.confirmed} == {"duplicate_object"}


def test_a_lone_judge_never_confirms_a_flag_defect():
    r = run([Fake("a", double=True)])
    assert r.status == "clean" and r.confirmed == [] and len(r.suspected) == 1


def test_judges_that_give_no_usable_answer_make_the_picture_unverified_not_clean():
    r = run([Fake("a", usable=False), Fake("b", usable=False)])
    assert r.status == "unverified" and r.judges == []


def test_a_missing_pose_confirmed_by_both_judges():
    r = run([Fake("a", pose="No, her hands are in her lap"), Fake("b", pose="No")], prompt="a woman sitting cross-legged, hands resting on her knees")
    assert r.status == "defects" and {d.pose for d in r.confirmed} == {"cross_legged", "hands_on_knees"}


def test_disagreeing_people_counts_skip_counts_but_not_pose_checks():
    r = run([Fake("a", whole_hands=4, tile_hands=4, pose="No"), Fake("b", whole_hands=4, tile_hands=4, people=2, pose="No")], prompt="sitting cross-legged")
    assert r.counts_skipped is True and r.people is None and {d.kind for d in r.confirmed} == {"pose_missing"}


def test_between_is_called_once_between_two_judges_and_pose_skips_are_reported():
    calls = []
    r = run([Fake("a"), Fake("b")], prompt="a cat on a table", between=lambda: calls.append(1))
    assert calls == [1] and r.pose_skipped == ["no pose word from the list"] and r.status == "clean"


def test_two_people_get_half_tiles_so_more_questions_are_asked():
    one, two = Fake("a"), Fake("a", people=2)
    run([one])
    run([two])
    assert two.calls == one.calls + 4  # two more tiles, two questions each
