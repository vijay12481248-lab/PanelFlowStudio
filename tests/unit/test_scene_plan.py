"""Task 2 of the scene-director plan: the ScenePlan model, the per-scene-type playbooks and the plan validator."""
import pytest

from engine.original.scene_plan import (
    ActorPlan, CameraPlan, ContactPlan, LightPlan, ScenePlan, load_playbook, scene_types, validate_plan,
)


def _fight(**over) -> ScenePlan:
    base = dict(
        scene_type="fight", brief="the hero fights the villain",
        actors=[ActorPlan(id="hero", description="young swordsman", side="left", action_state="striking"),
                ActorPlan(id="villain", description="armoured warlord", side="right", action_state="blocking")],
        contacts=[ContactPlan(source="hero", target="villain", body_part="sword", direction="down-right")],
        camera=CameraPlan(angle="low", distance="medium"), light=LightPlan(direction="back"),
    )
    base.update(over)
    return ScenePlan(**base)


def test_valid_fight_plan_has_no_problems():
    assert validate_plan(_fight(), load_playbook("fight")) == []


def test_same_side_fighters_rejected():
    plan = _fight(actors=[ActorPlan(id="hero", description="x", side="left", action_state="striking"),
                          ActorPlan(id="villain", description="y", side="left", action_state="blocking")])
    problems = validate_plan(plan, load_playbook("fight"))
    assert len(problems) == 1 and "hero" in problems[0] and "villain" in problems[0]


def test_strike_direction_away_from_target_rejected():
    plan = _fight(contacts=[ContactPlan(source="hero", target="villain", direction="down-left")])
    problems = validate_plan(plan, load_playbook("fight"))
    assert len(problems) == 1 and "direction" in problems[0]


def test_unknown_action_state_rejected():
    plan = _fight(actors=[ActorPlan(id="hero", description="x", side="left", action_state="dancing"),
                          ActorPlan(id="villain", description="y", side="right", action_state="blocking")])
    problems = validate_plan(plan, load_playbook("fight"))
    assert len(problems) == 1 and "dancing" in problems[0]


def test_contact_to_unknown_actor_rejected():
    plan = _fight(contacts=[ContactPlan(source="hero", target="ghost", direction="right")])
    assert any("ghost" in p for p in validate_plan(plan, load_playbook("fight")))


def test_contact_to_self_rejected():
    plan = _fight(contacts=[ContactPlan(source="hero", target="hero")])
    assert any("itself" in p for p in validate_plan(plan, load_playbook("fight")))


def test_single_actor_portrait_valid():
    plan = ScenePlan(scene_type="emotion", brief="a girl who just lost her friend",
                     actors=[ActorPlan(id="girl", description="teenage girl", side="center", action_state="grieving")],
                     camera=CameraPlan(angle="eye_level", distance="close"), light=LightPlan(direction="left"))
    assert validate_plan(plan, load_playbook("emotion")) == []


def test_empty_landscape_concept_art_valid():
    plan = ScenePlan(scene_type="concept_art", brief="a floating city", actors=[],
                     camera=CameraPlan(angle="low", distance="wide"), light=LightPlan(direction="top"))
    assert validate_plan(plan, load_playbook("concept_art")) == []


def test_fight_with_a_single_actor_is_valid():
    plan = _fight(actors=[ActorPlan(id="hero", description="x", side="center", action_state="readying")], contacts=[])
    assert validate_plan(plan, load_playbook("fight")) == []


def test_load_playbook_unknown_raises():
    with pytest.raises(ValueError):
        load_playbook("cooking")


def test_every_shipped_playbook_loads():
    assert set(scene_types()) == {"fight", "emotion", "concept_art"}
    for t in scene_types():
        pb = load_playbook(t)
        assert pb.scene_type == t and pb.keywords and pb.high_impact and pb.questions
        assert all(k in pb.questions for k in pb.high_impact)


@pytest.mark.parametrize("direction,attacker_side,ok", [
    ("left to right", "left", True), ("from left to right", "left", True), ("right to left", "right", True),
    ("left to right", "right", False), ("down-right", "left", True), ("down-left", "left", False),
])
def test_direction_phrases_with_both_words_use_the_destination(direction, attacker_side, ok):
    # real planner output: "left to right" was rejected as pointing away from the target on the right
    target_side = "right" if attacker_side == "left" else "left"
    plan = _fight(actors=[ActorPlan(id="hero", description="x", side=attacker_side, action_state="striking"),
                          ActorPlan(id="villain", description="y", side=target_side, action_state="blocking")],
                  contacts=[ContactPlan(source="hero", target="villain", direction=direction)])
    assert (validate_plan(plan, load_playbook("fight")) == []) is ok


def test_state_groups_only_name_real_states_and_fight_has_none():
    for t in scene_types():
        pb = load_playbook(t)
        assert all(s in pb.action_states for g in pb.state_groups for s in g)
    assert load_playbook("fight").state_groups == []  # striking and blocking must never be confused
    assert load_playbook("emotion").state_groups


def test_duplicate_actor_ids_rejected():
    plan = _fight(actors=[ActorPlan(id="hero", description="x", side="left", action_state="striking"),
                          ActorPlan(id="hero", description="y", side="right", action_state="blocking")])
    problems = validate_plan(plan, load_playbook("fight"))
    assert any("duplicate" in p and "hero" in p for p in problems)


def test_two_fighters_on_one_side_are_rejected_even_without_a_contact():
    # review finding: {"actors.villain.side": "left"} was accepted when the plan had no contact
    same = _fight(actors=[ActorPlan(id="hero", description="x", side="left", action_state="striking"),
                          ActorPlan(id="villain", description="y", side="left", action_state="blocking")], contacts=[])
    assert any("opposite sides" in p for p in validate_plan(same, load_playbook("fight")))
    both_centre = _fight(actors=[ActorPlan(id="hero", description="x", side="center", action_state="striking"),
                                 ActorPlan(id="villain", description="y", side="center", action_state="blocking")], contacts=[])
    assert any("opposite sides" in p for p in validate_plan(both_centre, load_playbook("fight")))


def test_more_than_two_actors_are_rejected_until_the_compiler_can_draw_them():
    # review finding: a 3-actor plan compiled to 2 figures but demanded "exactly three", burning every attempt
    three = _fight(actors=[ActorPlan(id=i, description="x", side=sd, action_state="readying") for i, sd in (("a", "left"), ("b", "center"), ("c", "right"))], contacts=[])
    assert any("at most two" in p for p in validate_plan(three, load_playbook("fight")))
