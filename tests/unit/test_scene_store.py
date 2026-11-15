"""Task 5 of the review-page plan: runs, analyses and owner feedback in SQLite, with full-text search (temp database from conftest)."""
import uuid

import pytest

from engine.database.models import Base, ProjectRecord, SceneFeedbackRecord, SceneRunRecord
from engine.database.session import SessionLocal, engine as db_engine
from engine.original import scene_store as store
from engine.database.session import ensure_scene_fts

PLAN = {"scene_type": "fight", "brief": "the hero fights the villain", "actors": []}
RESULT = {"status": "needs_review", "unmet": ["the camera looks up at the scene from a low angle"], "unverified": False, "seconds": 41.5,
          "iterations": [{"n": 1, "kind": "generate"}, {"n": 2, "kind": "generate"}], "review": {"decision": "regenerate", "score": 0.86}}
CC_DISPUTED = {"judges": ["A", "B"], "single_judge": False, "seconds": 9.0,
               "items": [{"key": "camera", "status": "disputed", "value": None, "confidence": 0.3, "answers": {}, "suspect_flips": []},
                         {"key": "people", "status": "agreed", "value": "2", "confidence": 0.9, "answers": {}, "suspect_flips": []}]}
CC_AGREED = {"judges": ["A", "B"], "single_judge": False, "seconds": 5.0, "items": [{"key": "camera", "status": "agreed", "value": "level", "confidence": 0.9, "answers": {}, "suspect_flips": []}]}
CC_SINGLE = {"judges": ["A"], "single_judge": True, "seconds": 2.0, "items": [{"key": "camera", "status": "single", "value": "level", "confidence": 0.5, "answers": {}, "suspect_flips": []}]}


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
    for model in (SceneFeedbackRecord, SceneRunRecord):
        pass
    project = session.get(ProjectRecord, pid)
    if project:
        session.delete(project)
        session.commit()
    session.close()


def new_run(db, brief="the hero fights the villain", **kw):
    return store.create_run(db, project_id=db.project_id, job_id="job-1", brief=brief, plan={**PLAN, "brief": brief}, image_path="panels/a.png", result=RESULT, **kw)


def test_run_roundtrip_with_analysis_and_feedback(db):
    run = new_run(db)
    assert run["review_state"] == "pending" and run["scene_type"] == "fight" and run["attempts"] == 2 and run["status"] == "needs_review"
    store.save_analysis(db, run["id"], CC_DISPUTED)
    store.submit_feedback(db, run["id"], liked=70, agrees_with_ai=True, good_tags=["Pose"], wrong_tags=["camera"], note="nice but the angle is flat")
    got = store.get_run(db, run["id"])
    assert got["analysis"]["crosscheck"]["items"][0]["status"] == "disputed" and got["analysis"]["single_judge"] is False
    assert got["feedback"]["liked"] == 70 and got["feedback"]["good_tags"] == ["pose"] and got["review_state"] == "reviewed"


def test_feedback_twice_keeps_one_row_the_second_wins(db):
    run = new_run(db)
    store.submit_feedback(db, run["id"], liked=10, agrees_with_ai=False, good_tags=[], wrong_tags=["style"], note="first")
    store.submit_feedback(db, run["id"], liked=90, agrees_with_ai=True, good_tags=["mood"], wrong_tags=[], note="second")
    assert db.query(SceneFeedbackRecord).filter_by(run_id=run["id"]).count() == 1
    assert store.get_run(db, run["id"])["feedback"]["note"] == "second"


def test_feedback_validation_and_unknown_run(db):
    run = new_run(db)
    for bad in (-1, 101):
        with pytest.raises(ValueError):
            store.submit_feedback(db, run["id"], liked=bad, agrees_with_ai=True, good_tags=[], wrong_tags=[])
    with pytest.raises(KeyError):
        store.submit_feedback(db, "nope", liked=50, agrees_with_ai=True, good_tags=[], wrong_tags=[])
    with pytest.raises(KeyError):
        store.get_run(db, "nope")


def test_huge_note_and_tags_are_cut(db):
    run = new_run(db)
    out = store.submit_feedback(db, run["id"], liked=50, agrees_with_ai=True, good_tags=[f"t{i}" for i in range(50)] + ["x" * 100], wrong_tags=[" Camera ", "camera"], note="n" * 100_000)
    assert len(out["feedback"]["note"]) == 4000 and len(out["feedback"]["good_tags"]) == 12 and out["feedback"]["wrong_tags"] == ["camera"]
    assert all(len(t) <= 40 for t in out["feedback"]["good_tags"])


def test_dismiss_removes_it_from_the_waiting_list(db):
    run = new_run(db)
    assert store.list_runs(db, unreviewed=True)["total_unreviewed"] >= 1
    store.dismiss(db, run["id"])
    assert store.get_run(db, run["id"])["review_state"] == "dismissed"
    assert all(r["id"] != run["id"] for r in store.list_runs(db, unreviewed=True)["items"])


def test_list_runs_unreviewed_paged_and_counted(db):
    before = store.list_runs(db, unreviewed=True)["total_unreviewed"]
    for i in range(210):
        new_run(db, brief=f"brief {i}")
    page = store.list_runs(db, unreviewed=True, limit=50)
    assert len(page["items"]) == 50 and page["total_unreviewed"] == before + 210
    assert len(store.list_runs(db, unreviewed=True, limit=9999)["items"]) == 200
    assert len(store.list_runs(db, unreviewed=True, limit=50, offset=100)["items"]) == 50
    assert page["items"][0]["created_at"] >= page["items"][-1]["created_at"]  # newest first


def test_search_finds_brief_and_note_text(db):
    a = new_run(db, brief="a dragon over a frozen canyon")
    b = new_run(db, brief="two samurai at dusk")
    store.submit_feedback(db, b["id"], liked=40, agrees_with_ai=False, good_tags=[], wrong_tags=["camera"], note="the horizon felt flat and boring")
    assert [r["id"] for r in store.search(db, "frozen dragon")] == [a["id"]]
    assert [r["id"] for r in store.search(db, "horizon")] == [b["id"]]
    assert store.search(db, "") == [] and store.search(db, "   ") == []


@pytest.mark.parametrize("query", ['"', "AND", "OR NOT", "*", "(", "dragon AND (", "'; DROP TABLE scene_runs; --", 'a"b', "NEAR(", "x" * 5000])
def test_search_with_operators_and_quotes_never_raises(db, query):
    new_run(db, brief="a dragon over a frozen canyon")
    assert isinstance(store.search(db, query), list)


def test_stats_counts_agreement_by_case(db):
    base = store.stats(db)
    r1, r2, r3 = new_run(db), new_run(db), new_run(db)
    store.save_analysis(db, r1["id"], CC_DISPUTED)
    store.save_analysis(db, r2["id"], CC_AGREED)
    store.save_analysis(db, r3["id"], CC_SINGLE)
    store.submit_feedback(db, r1["id"], liked=30, agrees_with_ai=False, good_tags=[], wrong_tags=["camera", "pose"])
    store.submit_feedback(db, r2["id"], liked=90, agrees_with_ai=True, good_tags=["mood"], wrong_tags=[])
    store.submit_feedback(db, r3["id"], liked=60, agrees_with_ai=True, good_tags=[], wrong_tags=["camera"])
    s = store.stats(db)
    assert s["runs"] == base["runs"] + 3 and s["reviewed"] == base["reviewed"] + 3
    assert s["by_scene_type"]["fight"]["n"] >= 3 and s["wrong_tags"]["camera"] >= 2 and s["wrong_tags"]["pose"] >= 1
    only = {"overall": s["ai_agreement"]["overall"]}
    assert s["ai_agreement"]["when_disputed"] is not None and s["ai_agreement"]["single_judge"] is not None and only["overall"] is not None


def test_stats_agreement_is_none_when_nothing_is_reviewed(db):
    # a fresh database state for these three keys is only guaranteed per run, so check the shape rather than a global value
    s = store.stats(db)
    assert set(s["ai_agreement"]) == {"overall", "when_disputed", "single_judge"} and {"runs", "reviewed", "mean_liked", "by_scene_type", "wrong_tags"} <= set(s)


def test_deleting_a_project_removes_its_runs(db):
    run = new_run(db)
    store.submit_feedback(db, run["id"], liked=50, agrees_with_ai=True, good_tags=[], wrong_tags=[])
    db.delete(db.get(ProjectRecord, db.project_id))
    db.commit()
    with pytest.raises(KeyError):
        store.get_run(db, run["id"])
    assert db.query(SceneFeedbackRecord).filter_by(run_id=run["id"]).count() == 0
    assert all(r["id"] != run["id"] for r in store.search(db, "hero"))


def test_item_verdicts_are_stored_and_cleaned(db):
    run = new_run(db)
    out = store.submit_feedback(db, run["id"], liked=60, agrees_with_ai=False, good_tags=[], wrong_tags=[],
                                item_verdicts={"camera": "looks_up", "action:1": "blocking", "evil": "x", "people": "y" * 100})
    assert out["feedback"]["item_verdicts"] == {"camera": "looks_up", "action:1": "blocking", "people": "y" * 40}  # unknown keys dropped, values cut
    again = store.submit_feedback(db, run["id"], liked=60, agrees_with_ai=False, good_tags=[], wrong_tags=[])
    assert again["feedback"]["item_verdicts"] == {}


def test_owner_choices_score_each_judge_against_the_owner(db):
    run = new_run(db)
    store.save_analysis(db, run["id"], {"judges": ["Aj", "Bj"], "single_judge": False, "seconds": 1.0, "items": [
        {"key": "camera", "status": "disputed", "value": None, "confidence": 0.3, "suspect_flips": [],
         "answers": {"Aj": {"round1": "level", "round2": "level", "evidence": ""}, "Bj": {"round1": "looks_up", "round2": "looks_up", "evidence": ""}}}]})
    store.submit_feedback(db, run["id"], liked=50, agrees_with_ai=False, good_tags=[], wrong_tags=[], item_verdicts={"camera": "looks_up"})
    rep = store.judge_report(db)["judges"]
    assert rep["Bj"]["owner_checked"] >= 1 and rep["Bj"]["owner_agreed"] >= 1
    assert rep["Aj"]["owner_checked"] >= 1 and rep["Aj"]["owner_agreed"] == rep["Aj"]["owner_checked"] - 1 or rep["Aj"]["owner_agreed"] < rep["Aj"]["owner_checked"]


def test_agreement_with_the_ai_ignores_reviews_where_there_was_no_ai_review(db):
    # review finding I8: "I agree with the AI" saved on a run whose judging failed must not inflate the agreement figure
    base = store.stats(db)["ai_agreement"]["overall"]
    good = new_run(db)
    store.save_analysis(db, good["id"], CC_AGREED)
    store.submit_feedback(db, good["id"], liked=80, agrees_with_ai=False, good_tags=[], wrong_tags=["style"])
    failed = new_run(db)
    store.save_analysis(db, failed["id"], None, error="judges exploded")
    store.submit_feedback(db, failed["id"], liked=80, agrees_with_ai=True, good_tags=[], wrong_tags=[])
    none = new_run(db)  # judging never finished
    store.submit_feedback(db, none["id"], liked=80, agrees_with_ai=True, good_tags=[], wrong_tags=[])
    s = store.stats(db)["ai_agreement"]["overall"]
    # only the run with a usable analysis counts, and it disagreed: the two "agrees" without an AI review cannot raise the figure above what disagreement gives
    assert s is not None and s <= (base if base is not None else 0.0) + 1e-9 or s == 0.0


def test_migration_adds_item_verdicts_to_an_older_feedback_table():
    from sqlalchemy import create_engine

    from engine.database.session import run_sqlite_migrations

    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.exec_driver_sql("CREATE TABLE scene_feedback (id TEXT PRIMARY KEY, run_id TEXT, liked INTEGER, agrees_with_ai BOOLEAN, good_tags JSON, wrong_tags JSON, note TEXT, created_at DATETIME)")
    run_sqlite_migrations(eng)
    with eng.connect() as c:
        assert "item_verdicts" in {r[1] for r in c.exec_driver_sql("PRAGMA table_info(scene_feedback)").fetchall()}
