"""The scene knowledge base: runs, the two judges' analysis and the owner's feedback in the app's SQLite database, with full-text search and statistics.

Everything the system learns from the owner lives here. Functions take a SQLAlchemy session and return plain dicts (JSON-ready for the API and the MCP tools).
"""
from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import text as sql

from engine.database.models import SceneAnalysisRecord, SceneFeedbackRecord, SceneRunRecord

MAX_NOTE = 4000
MAX_TAGS, MAX_TAG_LEN = 12, 40
MAX_LIMIT = 200


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _clean_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for t in tags:
        t = str(t).strip().lower()[:MAX_TAG_LEN]
        if t and t not in out:
            out.append(t)
    return out[:MAX_TAGS]


def _analysis_dict(a: SceneAnalysisRecord | None) -> dict | None:
    if a is None:
        return None
    return {"id": a.id, "crosscheck": a.crosscheck, "judges": a.judges, "single_judge": a.single_judge, "seconds": a.seconds, "error": a.error, "created_at": _iso(a.created_at)}


def _feedback_dict(f: SceneFeedbackRecord | None) -> dict | None:
    if f is None:
        return None
    return {"liked": f.liked, "agrees_with_ai": f.agrees_with_ai, "good_tags": f.good_tags, "wrong_tags": f.wrong_tags, "note": f.note, "created_at": _iso(f.created_at)}


def _run_dict(db, r: SceneRunRecord, full: bool = True) -> dict:
    out = {"id": r.id, "project_id": r.project_id, "job_id": r.job_id, "brief": r.brief, "scene_type": r.scene_type, "plan": r.plan, "image_path": r.image_path,
           "status": r.status, "system_review": r.system_review, "attempts": r.attempts, "seconds": r.seconds, "review_state": r.review_state, "created_at": _iso(r.created_at)}
    if full:
        analysis = db.query(SceneAnalysisRecord).filter_by(run_id=r.id).order_by(SceneAnalysisRecord.created_at.desc()).first()
        feedback = db.query(SceneFeedbackRecord).filter_by(run_id=r.id).first()
        out["analysis"], out["feedback"] = _analysis_dict(analysis), _feedback_dict(feedback)
    return out


def _fts_write(db, run_id: str, *parts: str) -> None:
    db.execute(sql("DELETE FROM scene_fts WHERE run_id = :id"), {"id": run_id})
    db.execute(sql("INSERT INTO scene_fts (run_id, text) VALUES (:id, :t)"), {"id": run_id, "t": " ".join(p for p in parts if p)})


def create_run(db, *, project_id: str, job_id: str | None, brief: str, plan: dict, image_path: str, result: dict) -> dict:
    rec = SceneRunRecord(
        project_id=project_id, job_id=job_id, brief=brief, scene_type=str(plan.get("scene_type", "")), plan=plan, image_path=image_path,
        status=str(result.get("status", "")), attempts=sum(1 for i in result.get("iterations", []) if i.get("kind") == "generate"), seconds=float(result.get("seconds", 0.0)),
        system_review={"unmet": result.get("unmet", []), "unverified": result.get("unverified", False), "review": result.get("review")})
    db.add(rec)
    db.flush()
    _fts_write(db, rec.id, brief, rec.scene_type)
    db.commit()
    return _run_dict(db, rec)


def save_analysis(db, run_id: str, crosscheck: dict | None, error: str = "") -> dict:
    if db.get(SceneRunRecord, run_id) is None:
        raise KeyError(run_id)
    cc = crosscheck or {}
    rec = SceneAnalysisRecord(run_id=run_id, crosscheck=cc, judges=cc.get("judges", []), single_judge=bool(cc.get("single_judge", False)), seconds=float(cc.get("seconds", 0.0)), error=error or None)
    db.add(rec)
    db.commit()
    return _analysis_dict(rec)


def submit_feedback(db, run_id: str, *, liked: int, agrees_with_ai: bool, good_tags: list[str], wrong_tags: list[str], note: str = "") -> dict:
    """KeyError for an unknown run, ValueError for `liked` outside 0-100. A second submission replaces the first (one row per run)."""
    run = db.get(SceneRunRecord, run_id)
    if run is None:
        raise KeyError(run_id)
    if not isinstance(liked, int) or isinstance(liked, bool) or not 0 <= liked <= 100:
        raise ValueError("liked must be a whole number from 0 to 100")
    fb = db.query(SceneFeedbackRecord).filter_by(run_id=run_id).first() or SceneFeedbackRecord(run_id=run_id, liked=liked)
    fb.liked, fb.agrees_with_ai, fb.good_tags, fb.wrong_tags, fb.note = liked, bool(agrees_with_ai), _clean_tags(good_tags), _clean_tags(wrong_tags), (note or "")[:MAX_NOTE]
    db.add(fb)
    run.review_state = "reviewed"
    _fts_write(db, run_id, run.brief, run.scene_type, fb.note, " ".join(fb.good_tags + fb.wrong_tags))
    db.commit()
    return _run_dict(db, run)


def dismiss(db, run_id: str) -> dict:
    run = db.get(SceneRunRecord, run_id)
    if run is None:
        raise KeyError(run_id)
    if run.review_state == "pending":
        run.review_state = "dismissed"
        db.commit()
    return _run_dict(db, run)


def list_runs(db, *, unreviewed: bool = False, limit: int = 50, offset: int = 0) -> dict:
    q = db.query(SceneRunRecord)
    if unreviewed:
        q = q.filter(SceneRunRecord.review_state == "pending")
    rows = q.order_by(SceneRunRecord.created_at.desc(), SceneRunRecord.id).offset(max(0, offset)).limit(max(1, min(limit, MAX_LIMIT))).all()
    total = db.query(SceneRunRecord).filter(SceneRunRecord.review_state == "pending").count()
    return {"items": [_run_dict(db, r) for r in rows], "total_unreviewed": total}


def get_run(db, run_id: str) -> dict:
    rec = db.get(SceneRunRecord, run_id)
    if rec is None:
        raise KeyError(run_id)
    return _run_dict(db, rec)


def search(db, query: str, limit: int = 20) -> list[dict]:
    """Full-text search over briefs, owner notes and tags. Every word is quoted, so FTS operators, quotes and parentheses in the query are plain text."""
    words = re.findall(r"\w+", query or "")[:20]
    if not words:
        return []
    match = " ".join(f'"{w}"' for w in words)
    ids = [r[0] for r in db.execute(sql("SELECT run_id FROM scene_fts WHERE scene_fts MATCH :m LIMIT :n"), {"m": match, "n": max(1, min(limit, MAX_LIMIT))}).fetchall()]
    runs = {r.id: r for r in db.query(SceneRunRecord).filter(SceneRunRecord.id.in_(ids)).all()} if ids else {}
    return [_run_dict(db, runs[i], full=False) for i in ids if i in runs]  # a row whose run was deleted with its project is skipped


def _share(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def stats(db) -> dict:
    runs = db.query(SceneRunRecord).all()
    feedback = {f.run_id: f for f in db.query(SceneFeedbackRecord).all()}
    analyses = {}
    for a in db.query(SceneAnalysisRecord).order_by(SceneAnalysisRecord.created_at).all():
        analyses[a.run_id] = a  # the latest analysis of a run wins
    by_type: dict[str, dict] = {}
    for r in runs:
        t = by_type.setdefault(r.scene_type or "unknown", {"n": 0, "reviewed": 0, "_liked": []})
        t["n"] += 1
        if r.id in feedback:
            t["reviewed"] += 1
            t["_liked"].append(feedback[r.id].liked)
    for t in by_type.values():
        liked = t.pop("_liked")
        t["mean_liked"] = sum(liked) / len(liked) if liked else None
    tags = Counter(tag for f in feedback.values() for tag in f.wrong_tags)

    def disputed(a) -> bool:
        return any(i.get("status") == "disputed" for i in (a.crosscheck or {}).get("items", []))

    agree = lambda pred: _share([f.agrees_with_ai for rid, f in feedback.items() if (rid in analyses and pred(analyses[rid]))])
    liked_all = [f.liked for f in feedback.values()]
    return {
        "runs": len(runs), "reviewed": sum(1 for r in runs if r.review_state == "reviewed"), "mean_liked": sum(liked_all) / len(liked_all) if liked_all else None,
        "by_scene_type": by_type, "wrong_tags": dict(tags),
        "ai_agreement": {"overall": _share([f.agrees_with_ai for f in feedback.values()]), "when_disputed": agree(disputed), "single_judge": agree(lambda a: a.single_judge)},
    }
