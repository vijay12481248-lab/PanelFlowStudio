from engine.original.anatomy.questions import Answer
from engine.original.anatomy.rules import Defect, judge_defects, pose_asks, text_requested


def A(tile="whole", **kw):
    return Answer(tile=tile, judge="j1", ok=True, **kw)


def kinds(ds):
    return sorted(d.kind for d in ds)


def test_more_than_two_hands_per_person_is_an_extra_hand_defect_on_any_view():
    ds = judge_defects([A("whole", hands=4), A("lower", hands=4)], people=1, pose_answers={})
    assert kinds(ds) == ["extra_hands", "extra_hands"] and {d.tile for d in ds} == {"whole", "lower"} and all(isinstance(d, Defect) and d.judge == "j1" for d in ds)
    assert judge_defects([A(hands=2)], people=1, pose_answers={}) == []


def test_views_are_compared_with_two_per_person_and_never_summed():
    assert judge_defects([A("upper", hands=1), A("middle", hands=1)], people=1, pose_answers={}) == []  # overlapping bands: 1 + 1 is not 2 hands
    assert judge_defects([A("left", hands=4)], people=2, pose_answers={}) == []  # four hands are fine for two people
    assert kinds(judge_defects([A("left", hands=5)], people=2, pose_answers={})) == ["extra_hands"]


def test_unknown_people_means_no_count_is_judged():
    assert judge_defects([A("whole", hands=9)], people=None, pose_answers={}) == []


def test_text_double_and_merged_flags():
    assert kinds(judge_defects([A(text=True, double=True, merged=True)], people=2, pose_answers={})) == ["duplicate_object", "merged_bodies", "stray_text"]
    assert judge_defects([A(text=True)], people=1, pose_answers={}, text_asked=True) == []


def test_an_unusable_answer_produces_no_defects():
    assert judge_defects([Answer(tile="whole", judge="j1", ok=False, hands=9, text=True)], people=1, pose_answers={}) == []


def test_pose_answers_false_is_missing_none_is_nothing():
    ds = judge_defects([A()], people=1, pose_answers={"cross_legged": False, "hands_on_knees": None, "kick": True})
    assert [(d.kind, d.pose) for d in ds] == [("pose_missing", "cross_legged")]


def test_pose_asks_from_the_prompt():
    asks, skipped = pose_asks("A young woman sitting cross-legged on the floor, both hands resting on her knees, smiling.")
    assert [k for k, _ in asks] == ["cross_legged", "hands_on_knees"] and skipped == []
    asks, skipped = pose_asks("performing a high side kick on one leg")
    assert "kick" in [k for k, _ in asks]
    assert pose_asks("a cat on a table") == ([], ["no pose word from the list"])


def test_text_requested():
    assert text_requested("a sign that says OPEN") and text_requested("the word WATER in big letters")
    assert not text_requested("a girl running")


def test_two_hands_is_asked_only_for_a_grip_not_for_resting_hands():
    assert "two_hands" in [k for k, _ in pose_asks("gripping a long sword with both hands raised high above his head")[0]]
    assert "two_hands" not in [k for k, _ in pose_asks("both hands resting on her knees")[0]]
