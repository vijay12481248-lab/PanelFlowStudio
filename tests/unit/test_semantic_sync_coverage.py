from copy import deepcopy
from engine.pipeline.narration import synchronize_narration


def test_sync_preserves_uncited_panels_and_absolute_audio_clock():
    scenes = [{"id": str(i), "duration_sec": 9, "layers": [
        {"source_panel_id": f"{i}-{j}", "transform": {"scale": 1.3}, "motion_preset": "cinematic_vertical_pan"}
        for j in range(3)]} for i in range(2)]
    clips = [{"id": str(i), "scene_id": str(i), "duration_sec": 6.25,
              "source_evidence": {"panel_ids": [f"{i}-1"]}} for i in range(2)]
    synchronize_narration(scenes, clips)
    assert clips[1]["start_time_sec"] == 6.6
    assert scenes[1]["start_time_sec"] == 6.6
    assert [c["duration_sec"] for c in clips] == [6.25, 6.25]
    for i, scene in enumerate(scenes):
        assert [l["source_panel_id"] for l in scene["layers"]] == [f"{i}-{j}" for j in range(3)]
        assert abs(sum(l["duration_sec"] for l in scene["layers"]) - scene["duration_sec"]) < 1e-6
        assert all(l["transform"]["scale"] == 1.3 for l in scene["layers"])
        assert all(l["motion_preset"] == "cinematic_vertical_pan" for l in scene["layers"])


def test_single_panel_per_clip_follows_measured_audio():
    scenes = [{"id": "s", "duration_sec": 10, "layers": [{"source_panel_id": p} for p in ['a', 'b']]}]
    clips = [{"id": p, "scene_id": "s", "duration_sec": d, "source_evidence": {"panel_ids": [p]}}
             for p, d in [('a', 3.1), ('b', 5.2)]]
    synchronize_narration(scenes, clips)
    assert scenes[0]['layers'][1]['start_offset_sec'] == 3.1
    assert clips[1]['start_time_sec'] == 3.1
