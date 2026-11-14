"""Task 4 of the scene-director plan: a ScenePlan becomes a Qwen prompt (through the existing compiler) and a checklist of what the picture must show."""
from engine.original.scene_plan import ActorPlan, CameraPlan, ContactPlan, LightPlan, ScenePlan
from engine.original.scene_prompt import compile_scene_prompt, plan_requirements, plan_to_shotspec

from scene_fixtures import HERO, VILLAIN, fight_plan


def test_actor_defaults_are_adult_neutral_human():
    a = ActorPlan(id="x", description="d", side="center", action_state="standing")
    assert (a.species, a.gender, a.age_group) == ("human", "neutral", "adult")


def test_prompt_names_each_actor_side_and_action():
    positive, negative, dims = compile_scene_prompt(fight_plan())
    assert "striking" in positive.lower() and "blocking" in positive.lower()
    assert positive.index("scarred cheek") < positive.index("black armour")  # left actor is described first
    assert "low camera angle" in positive
    assert len(dims) == 2 and all(isinstance(v, int) and v > 0 for v in dims)
    assert negative  # Qwen negative guidance is not empty


def test_names_never_reach_the_prompt():
    positive, _, _ = compile_scene_prompt(fight_plan())
    assert "hero" not in positive.lower() and "villain" not in positive.lower()


def test_emphasis_is_stated_first():
    positive, _, _ = compile_scene_prompt(fight_plan(), emphasis=["the sword touches the black armour"])
    assert positive.startswith("Most important: the sword touches the black armour.")


def test_lessons_go_to_negative_only():
    positive, negative, _ = compile_scene_prompt(fight_plan(), lessons="both fighters on one side")
    assert "both fighters on one side" in negative and "both fighters on one side" not in positive


def test_no_actor_plan_compiles():
    plan = ScenePlan(scene_type="concept_art", brief="a floating city", actors=[], setting="a floating city above clouds",
                     camera=CameraPlan(angle="low", distance="wide"), light=LightPlan(direction="top"))
    positive, _, _ = compile_scene_prompt(plan)
    assert "no people" in positive.lower()


def test_creature_actor_gets_no_human_anatomy_sentence():
    plan = fight_plan(actors=[ActorPlan(id="dragon", description="red scales, huge wings", species="dragon", side="right", action_state="striking")],
                      contacts=[])
    positive, _, _ = compile_scene_prompt(plan)
    assert "dragon" in positive and "five distinct separated fingers" not in positive


def test_requirements_cover_count_sides_states_contacts_camera():
    reqs = plan_requirements(fight_plan())
    who_h = f"an adult man with {HERO}"
    who_v = f"an adult man with {VILLAIN}"
    got = [(c.text, c.critical, c.kind) for c in reqs]
    assert got[:8] == [
        ("exactly two figures are in the picture", True, "subject"),
        (f"{who_h} is on the left of the picture", True, "placement"),
        (f"{who_h} is striking", True, "pose"),
        (f"{who_v} is on the right of the picture", True, "placement"),
        (f"{who_v} is blocking", True, "pose"),
        (f"{who_h} reaches {who_v} with the sword, aimed down-right", True, "pose"),
        ("the camera looks up at the scene from a low angle", True, "camera"),
        ("the framing is a medium shot", False, "framing"),
    ]
    rest = {(c.text, c.critical) for c in reqs[8:]}
    assert ("the main light comes from behind the subjects", False) in rest
    assert ("the foreground shows flying sparks", False) in rest


def test_mood_is_not_a_requirement():
    assert not any("tense" in c.text for c in plan_requirements(fight_plan()))


def test_no_actor_requirements_say_no_people():
    plan = ScenePlan(scene_type="concept_art", brief="a floating city", actors=[], camera=CameraPlan(angle="low", distance="wide"),
                     light=LightPlan(direction="top"))
    texts = [c.text for c in plan_requirements(plan)]
    assert texts[0] == "there are no people in the picture"


def test_shotspec_maps_camera_distance_and_sides():
    story, spec, loc = plan_to_shotspec(fight_plan())
    assert spec.shot == "medium" and spec.camera == "low"
    assert [(c.id, c.side) for c in spec.characters] == [("hero", "left"), ("villain", "right")]
    assert loc in {x.id for x in story.bible.locations}
