from types import SimpleNamespace

from engine.audio.chapter_plan import plan_chapter_audio


def test_sparse_semantic_sfx_and_narration_only_failure(tmp_path):
    segments = [SimpleNamespace(id="a", scene_id="scene", music_intent="TENSE", sfx_intent="SWORD_DRAW", text="A blade emerges.")]
    timeline = {"total_duration_sec": 6, "intervals": [{"script_segment_id": "a", "start_time": 0.5, "end_time": 5.0}]}
    plan = plan_chapter_audio(tmp_path, {"auto_music": False, "auto_sfx": True}, segments, timeline)
    assert plan["music"]["path"] is None
    assert plan["music"]["emotional_arc"] == ["TENSE"]
    assert plan["sfx"] == []
    assert plan["warnings"]  # unavailable optional assets are visible
    assert (tmp_path / "audio/chapter_audio_plan.json").exists()
