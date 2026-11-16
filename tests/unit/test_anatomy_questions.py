from engine.original.anatomy.questions import (ENUM_PROMPT, TILE_FLAGS_PROMPT, WHOLE_FLAGS_PROMPT, Answer, parse_enum_reply, parse_flags_reply, parse_yes_no,
                                               pose_prompt)

FOUR_HANDS = """HAND 1: left side, resting on the left knee
HAND 2: right side, resting on the right knee
HAND 3: centre-left, between the legs
HAND 4: centre-right, between the legs
FOOT 1: left, on the floor
FOOT 2: right, on the floor"""


def test_hands_and_feet_are_counted_from_the_list_not_from_a_number():
    assert parse_enum_reply(FOUR_HANDS) == (4, 2)
    assert parse_enum_reply("HAND 1: a\nHAND 1: a again\nHAND 2: b") == (2, None)  # distinct numbers only


def test_no_hands_is_zero_and_nothing_usable_is_none():
    assert parse_enum_reply("NO HANDS\nNO FEET") == (0, 0)
    assert parse_enum_reply("I think it looks nice") == (None, None)
    assert parse_enum_reply("") == (None, None)


def test_an_echoed_template_is_not_an_answer():
    assert parse_enum_reply(ENUM_PROMPT) == (None, None)
    assert parse_flags_reply(WHOLE_FLAGS_PROMPT, "j", "whole").ok is False
    assert parse_flags_reply(TILE_FLAGS_PROMPT, "j", "upper").ok is False


def test_a_whole_flags_reply_parses_people_and_flags():
    a = parse_flags_reply("PEOPLE: 2\nTEXT: yes\nDOUBLE: no\nMERGED: yes\nEVIDENCE: bodies overlap", "judge-a", "whole")
    assert isinstance(a, Answer) and a.ok and (a.tile, a.judge) == ("whole", "judge-a")
    assert (a.people, a.text, a.double, a.merged, a.evidence) == (2, True, False, True, "bodies overlap")


def test_a_tile_flags_reply_has_no_people_or_merged():
    a = parse_flags_reply("TEXT: no\nDOUBLE: yes\nEVIDENCE: a second blade", "j", "upper")
    assert (a.people, a.merged, a.text, a.double) == (None, None, False, True)


def test_ambiguous_people_are_not_guessed():
    assert parse_flags_reply("PEOPLE: 2 or 3\nTEXT: no", "j", "whole").people is None


def test_empty_or_chatty_replies_are_not_answers():
    assert parse_flags_reply("", "j", "whole").ok is False
    assert parse_flags_reply("I think it looks nice", "j", "whole").ok is False


def test_yes_no_parsing():
    assert parse_yes_no("Yes, clearly") is True
    assert parse_yes_no("No") is False
    assert parse_yes_no("not really") is False
    assert parse_yes_no("unclear") is None
    assert parse_yes_no("yes or no") is None
    assert parse_yes_no("") is None


def test_pose_prompt_carries_the_question():
    assert "legs crossed" in pose_prompt("Is the person sitting with their legs crossed?")
