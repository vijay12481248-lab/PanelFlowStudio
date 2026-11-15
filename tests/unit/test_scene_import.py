"""Loading existing Scene pictures (the 24 baseline pictures, the director set, earlier runs) into the review queue, with the two judges (faked here)."""
import json
import uuid
from pathlib import Path

import pytest

from engine.database.models import Base, ProjectRecord, SceneAnalysisRecord, SceneRunRecord
from engine.database.session import SessionLocal, engine as db_engine, ensure_scene_fts
from engine.original import scene_import as si
from engine.original import scene_store as store

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64


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


@pytest.fixture
def tree(tmp_path):
    """A tiny copy of output/Original_Scenes: baseline raw + director (one failed brief) + one earlier run folder."""
    root = tmp_path / "Original_Scenes"
    briefs = [{"id": "fight-01", "scene_type": "fight", "text": "the hero fights the villain"}, {"id": "emotion-01", "scene_type": "emotion", "text": "a girl who just lost her best friend"}]
    briefs_file = tmp_path / "baseline_briefs.json"
    briefs_file.write_text(json.dumps(briefs), encoding="utf-8")
    raw = root / "_baseline" / "raw"
    raw.mkdir(parents=True)
    for b in briefs:
        (raw / f"{b['id']}.png").write_bytes(PNG)
    dr = root / "_baseline" / "director"
    (dr / "panels").mkdir(parents=True)
    plan = {"scene_type": "fight", "brief": "the hero fights the villain", "actors": [], "camera": {"angle": "low", "distance": "medium"}}
    (dr / "panels" / "fight-01.png").write_bytes(PNG)
    (dr / "panels" / "fight-01.json").write_text(json.dumps({"image_path": "panels/fight-01.png", "plan": plan, "status": "needs_review", "unmet": ["x"], "unverified": False, "seconds": 80.0,
                                                           "iterations": [{"n": 1, "kind": "generate"}], "review": {"decision": "regenerate"}}), encoding="utf-8")
    (dr / "results.json").write_text(json.dumps([
        {"id": "fight-01", "scene_type": "fight", "text": "the hero fights the villain", "mode": "director", "file": "panels/fight-01.png", "error": ""},
        {"id": "emotion-01", "scene_type": "emotion", "text": "a girl who just lost her best friend", "mode": "director", "file": None, "error": "planner failed"}]), encoding="utf-8")
    run_dir = root / "1481de22-aaaa" / "panels"
    run_dir.mkdir(parents=True)
    (run_dir / "5cb57d21.png").write_bytes(PNG)
    (run_dir / "5cb57d21.json").write_text(json.dumps({"image_path": "panels/5cb57d21.png", "plan": {**plan, "brief": "a samurai duel at dusk"}, "status": "accept", "unmet": [], "unverified": False,
                                                       "seconds": 99.0, "iterations": []}), encoding="utf-8")
    return root, briefs_file


def test_collect_finds_every_picture_and_labels_where_it_came_from(tree):
    root, briefs = tree
    items = si.collect(root, briefs)
    by = {i["rel"]: i for i in items}
    assert sorted(by) == ["baseline/director/fight-01.png", "baseline/raw/emotion-01.png", "baseline/raw/fight-01.png", "earlier/1481de22-aaaa/5cb57d21.png"]  # the failed brief has no picture
    assert by["baseline/raw/fight-01.png"]["brief"] == "[raw] the hero fights the villain" and by["baseline/raw/fight-01.png"]["plan"] == {"scene_type": "fight", "brief": "the hero fights the villain"}
    assert by["baseline/director/fight-01.png"]["brief"].startswith("[director] ") and by["baseline/director/fight-01.png"]["plan"]["camera"]["angle"] == "low"
    assert by["earlier/1481de22-aaaa/5cb57d21.png"]["brief"] == "[earlier run] a samurai duel at dusk"
    assert all(i["source"].is_file() for i in items)


def test_import_creates_pending_runs_copies_pictures_and_runs_the_judges(db, tree, tmp_path):
    root, briefs = tree
    dest = tmp_path / "scene_root"
    judged = []
    out = si.import_runs(db, db.project_id, si.collect(root, briefs), dest, lambda d, run_id, scene_type, image: judged.append((run_id, scene_type, image.name)))
    assert out == {"created": 4, "skipped": 0, "judged": 4, "judge_errors": 0}
    mine = db.query(SceneRunRecord).filter_by(project_id=db.project_id).all()
    assert {r.review_state for r in mine} == {"pending"} and len(mine) == 4
    for r in mine:
        assert (dest / db.project_id / r.image_path).read_bytes() == PNG  # served from <scene root>/<project>/<image_path>, like the engine does
    assert sorted(t for _, t, _ in judged) == ["emotion", "fight", "fight", "fight"]


def test_import_twice_does_not_duplicate_or_rejudge(db, tree, tmp_path):
    root, briefs = tree
    dest, calls = tmp_path / "scene_root", []
    judge = lambda d, run_id, scene_type, image: (calls.append(run_id), store.save_analysis(d, run_id, {"judges": ["A", "B"], "items": []}))  # noqa: E731
    si.import_runs(db, db.project_id, si.collect(root, briefs), dest, judge)
    again = si.import_runs(db, db.project_id, si.collect(root, briefs), dest, judge)
    assert again == {"created": 0, "skipped": 4, "judged": 0, "judge_errors": 0} and len(calls) == 4
    assert db.query(SceneRunRecord).filter_by(project_id=db.project_id).count() == 4


def test_a_failed_judge_run_is_retried_and_never_stops_the_import(db, tree, tmp_path):
    root, briefs = tree
    dest = tmp_path / "scene_root"
    state = {"n": 0}

    def flaky(d, run_id, scene_type, image):
        state["n"] += 1
        if state["n"] == 2:
            store.save_analysis(d, run_id, None, error="ComfyUI is down")
            raise RuntimeError("ComfyUI is down")
        store.save_analysis(d, run_id, {"judges": ["A", "B"], "items": []})

    out = si.import_runs(db, db.project_id, si.collect(root, briefs), dest, flaky)
    assert out["created"] == 4 and out["judged"] == 3 and out["judge_errors"] == 1
    again = si.import_runs(db, db.project_id, si.collect(root, briefs), dest, flaky)  # the one whose analysis is an error is judged again
    assert again["created"] == 0 and again["judged"] == 1 and again["judge_errors"] == 0
    good = db.query(SceneAnalysisRecord).filter(SceneAnalysisRecord.error.is_(None)).count()
    assert good >= 4
