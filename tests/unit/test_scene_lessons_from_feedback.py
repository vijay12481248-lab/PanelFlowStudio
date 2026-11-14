"""Task 10 of the review-page plan: the owner's feedback becomes lessons for the Scene Director, and a report of how the judges fare (temp database)."""
import uuid

import pytest

from engine.database.models import Base, ProjectRecord
from engine.database.session import SessionLocal, ensure_scene_fts, engine as db_engine
from engine.original import scene_store as store
from engine.original.scene_lessons import lessons_from_feedback
from engine.original.scene_plan import CameraPlan
from scene_fixtures import fight_plan

RESULT = {"status": "accept", "unmet": [], "unverified": False, "seconds": 10.0, "iterations": [{"kind": "generate"}], "review": None}


@pytest.fixture
def db():
    Base.metadata.create_all(db_engine)
    ensure_scene_fts(db_engine)
    session = SessionLocal()
    pid = f"proj-{uuid.uuid4().hex[:8]}"
    session.add(ProjectRecord(id=pid, title="Scene Director", source_type="CHRONOFLOW_AI", rights_status="USER_OWNED", workspace_path="x"))
    session.commit()
    session.project_id = pid
    yield session
    session.rollback()
    project = session.get(ProjectRecord, pid)
    if project:
        session.delete(project)
        session.commit()
    session.close()


def reviewed(db, plan, liked, wrong_tags, scene_type=None):
    p = plan.model_dump(mode="json")
    if scene_type:
        p["scene_type"] = scene_type
    run = store.create_run(db, project_id=db.project_id, job_id=None, brief=plan.brief, plan=p, image_path="panels/a.png", result=RESULT)
    store.submit_feedback(db, run["id"], liked=liked, agrees_with_ai=False, good_tags=[], wrong_tags=wrong_tags)
    return run


def scene(db):
    # these tests share one temp database with others: count against a unique scene type so earlier rows cannot leak in
    return f"fight_{uuid.uuid4().hex[:6]}"


def test_two_owner_camera_complaints_make_a_camera_lesson_for_that_angle_only(db):
    st = scene(db)
    low, high = fight_plan(), fight_plan(camera=CameraPlan(angle="high", distance="medium"))
    for _ in range(2):
        reviewed(db, low, 30, ["camera"], st)
    plan = fight_plan()
    plan.scene_type = st
    assert "steeply upward" in lessons_from_feedback(db, st, plan)
    high_plan = high
    high_plan.scene_type = st
    assert "steeply upward" not in lessons_from_feedback(db, st, high_plan)


def test_a_complaint_the_owner_still_liked_does_not_count(db):
    st = scene(db)
    for _ in range(3):
        reviewed(db, fight_plan(), 85, ["camera"], st)  # complained but liked it: not a lesson
    plan = fight_plan()
    plan.scene_type = st
    assert lessons_from_feedback(db, st, plan) == ""


def test_one_complaint_is_not_enough(db):
    st = scene(db)
    reviewed(db, fight_plan(), 20, ["camera"], st)
    plan = fight_plan()
    plan.scene_type = st
    assert lessons_from_feedback(db, st, plan) == ""


def test_other_scene_type_is_not_affected(db):
    st, other = scene(db), scene(db)
    for _ in range(2):
        reviewed(db, fight_plan(), 10, ["camera"], st)
    plan = fight_plan()
    plan.scene_type = other
    assert lessons_from_feedback(db, other, plan) == ""


def test_pose_complaints_count_per_action_state_of_the_plan(db):
    st = scene(db)
    for _ in range(2):
        reviewed(db, fight_plan(), 40, ["pose"], st)
    plan = fight_plan()  # striking + blocking
    plan.scene_type = st
    out = lessons_from_feedback(db, st, plan)
    assert "fully extended" in out and "raised in front of the body" in out
    plan.actors[0].action_state, plan.actors[1].action_state = "falling", "dodging"
    assert "fully extended" not in lessons_from_feedback(db, st, plan)


def test_complaints_without_camera_or_pose_tags_teach_nothing_here(db):
    st = scene(db)
    for _ in range(3):
        reviewed(db, fight_plan(), 10, ["style", "identity"], st)
    plan = fight_plan()
    plan.scene_type = st
    assert lessons_from_feedback(db, st, plan) == ""


def test_judge_report_shapes_and_none_when_empty(db):
    empty = store.judge_report(db)
    assert set(empty) == {"judges", "owner_agreement"}
    assert set(empty["owner_agreement"]) == {"overall", "when_disputed", "single_judge"}


def test_judge_report_counts_disputes_and_flips_per_judge(db):
    run = store.create_run(db, project_id=db.project_id, job_id=None, brief="b", plan=fight_plan().model_dump(mode="json"), image_path="p.png", result=RESULT)
    store.save_analysis(db, run["id"], {"judges": ["Zjudge", "Yjudge"], "single_judge": False, "seconds": 5.0, "items": [
        {"key": "camera", "status": "disputed", "value": None, "confidence": 0.3, "suspect_flips": [], "answers": {"Zjudge": {"round1": "level", "round2": "level", "evidence": "x"}, "Yjudge": {"round1": "looks_up", "round2": "looks_up", "evidence": "y"}}},
        {"key": "people", "status": "resolved", "value": "2", "confidence": 0.7, "suspect_flips": ["Yjudge"], "answers": {"Zjudge": {"round1": "2", "round2": None, "evidence": ""}, "Yjudge": {"round1": "3", "round2": "2", "evidence": "ok"}}},
    ]})
    rep = store.judge_report(db)["judges"]
    assert rep["Zjudge"]["items"] >= 2 and rep["Zjudge"]["disputed_share"] > 0
    assert rep["Yjudge"]["suspect_flip_share"] > 0 and 0 <= rep["Yjudge"]["disputed_share"] <= 1
    assert store.stats(db)["judges"]["Yjudge"]["suspect_flip_share"] > 0
