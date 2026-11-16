from engine.original.anatomy.questions import Answer, TILE_PROMPT, WHOLE_PROMPT, parse_reply, parse_yes_no, pose_prompt

WHOLE = """PEOPLE: 1
ARMS: 4
HANDS: 4
LEGS: 2
FEET: 2
TEXT: no
DOUBLE: no
MERGED: no
EVIDENCE: Two hands rest on the knees and two more are clasped in her lap."""

TILE = """ARMS: 2
HANDS: 2
LEGS: 0
FEET: 0
TEXT: yes
DOUBLE: yes
EVIDENCE: A second blade is drawn behind the first."""


def test_a_well_formed_whole_reply_parses_every_field():
    a = parse_reply(WHOLE, "judge-a", "whole")
    assert isinstance(a, Answer) and a.ok and (a.tile, a.judge) == ("whole", "judge-a")
    assert (a.people, a.arms, a.hands, a.legs, a.feet) == (1, 4, 4, 2, 2)
    assert (a.text, a.double, a.merged) == (False, False, False) and "clasped" in a.evidence


def test_a_tile_reply_parses_counts_and_yes_no_fields():
    a = parse_reply(TILE, "judge-b", "upper")
    assert (a.arms, a.hands, a.text, a.double, a.merged, a.people) == (2, 2, True, True, None, None)


def test_ambiguous_numbers_are_not_guessed():
    a = parse_reply("ARMS: 2 or 3\nHANDS: four arms and two legs\nLEGS: 2", "j", "whole")
    assert (a.arms, a.hands, a.legs) == (None, None, 2) and a.ok


def test_an_echoed_template_or_empty_reply_is_not_an_answer():
    assert parse_reply(WHOLE_PROMPT, "j", "whole").ok is False
    assert parse_reply(TILE_PROMPT, "j", "upper").ok is False
    assert parse_reply("", "j", "whole").ok is False
    assert parse_reply("I think it looks nice", "j", "whole").ok is False


def test_yes_no_parsing():
    assert parse_yes_no("Yes, clearly") is True
    assert parse_yes_no("No") is False
    assert parse_yes_no("not really") is False
    assert parse_yes_no("unclear") is None
    assert parse_yes_no("yes or no") is None
    assert parse_yes_no("") is None


def test_pose_prompt_carries_the_question():
    assert "legs crossed" in pose_prompt("Is the person sitting with their legs crossed?")
