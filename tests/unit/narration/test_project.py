import uuid
from pathlib import Path

from engine.database.models import ProjectRecord, ScriptSegmentRecord, VideoScriptRecord
from engine.database.session import SessionLocal, init_db
from engine.narration.project import apply_to_project
from engine.narration.steps.timeline import lock_timeline
from tests.unit.narration.test_timeline import _world


def _setup(tmp_path, settings=None, specs=((2.0, 300), (2.0, 300), (2.0, 300))):
    init_db()
    pid = str(uuid.uuid4())
    script, plan, takes, sheet, ids = _world(list(specs))
    for t in takes:
        wav = tmp_path / f"{t.line_id}.wav"
        wav.write_bytes(b"RIFFdata-" + t.line_id.encode())
        t.audio_path = str(wav)
    with SessionLocal() as db:
        db.add(ProjectRecord(id=pid, title="T", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path),
                             settings=settings or {}))
        db.commit()
    tl = lock_timeline(script, plan, takes, sheet, ids)
    return pid, tl, script, sheet, takes


def _state(pid):
    with SessionLocal() as db:
        return db.get(ProjectRecord, pid).settings["story_editor_state"]


def test_projection_replaces_only_scenes_and_clips(tmp_path):
    keep = {"scenes": [{"id": "old"}], "narration_clips": [{"id": "old"}], "bgm_tracks": [{"id": "b"}],
            "zoom_level": 7, "mode": "edit"}
    pid, tl, script, sheet, takes = _setup(tmp_path, {"story_editor_state": keep, "other": 1})
    with SessionLocal() as db:
        apply_to_project(db, pid, tl, script, sheet, takes, tmp_path)
        settings = db.get(ProjectRecord, pid).settings
    st = settings["story_editor_state"]
    assert st["bgm_tracks"] == [{"id": "b"}] and st["zoom_level"] == 7 and st["mode"] == "edit"
    assert settings["other"] == 1
    assert [s["id"] for s in st["scenes"]] == ["narr_s1"]
    assert [c["id"] for c in st["narration_clips"]] == ["narr_l0", "narr_l1", "narr_l2"]


def test_clip_and_layer_times_match_timeline(tmp_path):
    pid, tl, script, sheet, takes = _setup(tmp_path)
    with SessionLocal() as db:
        apply_to_project(db, pid, tl, script, sheet, takes, tmp_path)
    st = _state(pid)
    sc = st["scenes"][0]
    assert sc["start_time_sec"] == tl.panels[0].start and sc["duration_sec"] == tl.duration
    for k, (layer, p) in enumerate(zip(sc["layers"], tl.panels)):
        assert layer["id"] == f"layer_s1_{k}" and layer["source_panel_id"] == p.panel_id
        assert layer["start_offset_sec"] == p.start - sc["start_time_sec"]
        assert layer["duration_sec"] == p.end - p.start and layer["motion_preset"] == "cinematic_vertical_pan"
    for c, tc in zip(st["narration_clips"], tl.clips):
        assert c["start_time_sec"] == tc.start and c["duration_sec"] == tc.end - tc.start
        assert c["scene_offset_sec"] == tc.start - sc["start_time_sec"]
        assert c["source_evidence"]["panel_ids"] == [tc.panel_id]
        assert c["status"] == c["review_status"] == "APPROVED"
    assert "background" in sc and "camera" in sc and "transition_in" in sc


def test_new_video_script_version_keeps_old(tmp_path):
    pid, tl, script, sheet, takes = _setup(tmp_path)
    with SessionLocal() as db:
        db.add(VideoScriptRecord(id="old-" + pid, project_id=pid, version="1.0"))
        db.commit()
        new_id = apply_to_project(db, pid, tl, script, sheet, takes, tmp_path)
        rows = db.query(VideoScriptRecord).filter_by(project_id=pid).all()
        new = db.get(VideoScriptRecord, new_id)
        segs = db.query(ScriptSegmentRecord).filter_by(script_id=new_id).order_by(ScriptSegmentRecord.sequence).all()
        assert len(rows) == 2 and new.version == "2.0" and new.status == "APPROVED"
        assert new.adaptation_profile == "narration_compiler"
        assert [s.type for s in segs] == ["NARRATOR"] * 3
        assert [s.estimated_start for s in segs] == [c.start for c in tl.clips]
        assert segs[0].source_evidence["panel_ids"] == [tl.clips[0].panel_id]
    clip = _state(pid)["narration_clips"][0]
    assert clip["source_script_id"] == new_id and clip["source_segment_ids"] == [segs[0].id]


def test_audio_copied_and_url_shape(tmp_path):
    pid, tl, script, sheet, takes = _setup(tmp_path)
    with SessionLocal() as db:
        apply_to_project(db, pid, tl, script, sheet, takes, tmp_path)
    clip = _state(pid)["narration_clips"][1]
    assert clip["audio_url"] == f"/api/projects/{pid}/audio/dialogue/narr_l1.wav"
    assert (tmp_path / "audio" / "dialogue" / "narr_l1.wav").read_bytes() == b"RIFFdata-l1"
