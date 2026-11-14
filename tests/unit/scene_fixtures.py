"""Shared fixtures for the scene-director tests."""
from engine.original.scene_plan import ActorPlan, CameraPlan, ContactPlan, LightPlan, ScenePlan

HERO = "short black hair, scarred cheek, worn blue coat"
VILLAIN = "tall, black armour, long red cape"


def fight_plan(**over) -> ScenePlan:
    base = dict(
        scene_type="fight", brief="the hero fights the villain", mood="tense", setting="a stone courtyard at dusk",
        actors=[ActorPlan(id="hero", description=HERO, gender="male", side="left", action_state="striking"),
                ActorPlan(id="villain", description=VILLAIN, gender="male", side="right", action_state="blocking")],
        contacts=[ContactPlan(source="hero", target="villain", body_part="sword", direction="down-right")],
        camera=CameraPlan(angle="low", distance="medium"), light=LightPlan(direction="back", quality="hard rim light"),
        depth={"foreground": "flying sparks", "background": "the courtyard wall"},
    )
    base.update(over)
    return ScenePlan(**base)
