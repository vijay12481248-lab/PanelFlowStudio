from copy import deepcopy
from engine.pipeline.narration import synchronize_narration


def test_sync_preserves_uncited_panels_and_absolute_audio_clock():
    scenes = [{"id": str(i), "duration_sec": 9, "layers": [
        {"source_panel_id": f"{i}-{j}", "transform": {"scale": 1.3}, "motion_preset": "cinematic_vertical_pan"}
        for j in range(3)]} for i in range(2)]
    clips = [{"id": str(i), "scene_id": str(i), "duration_sec": 6.25,
              "source_evidence": {"panel_ids": [f"{i}-1"]}} for i in range(2)]
    synchronize_narration(scenes, clips)
    assert clips[1]["start_time_sec"] == 6.35
    assert scenes[1]["start_time_sec"] == 6.35
    assert [c["duration_sec"] for c in clips] == [6.25, 6.25]
    for i, scene in enumerate(scenes):
        assert [l["source_panel_id"] for l in scene["layers"]] == [f"{i}-{j}" for j in range(3)]
        assert abs(sum(l["duration_sec"] for l in scene["layers"]) - scene["duration_sec"]) < 1e-6
        assert all(l["transform"]["scale"] == 1.3 for l in scene["layers"])
        assert all(l["motion_preset"] == "cinematic_vertical_pan" for l in scene["layers"])


def test_stale_estimated_layer_timing_is_retimed_to_measured_audio():
    # Layers carry offsets from the pre-TTS estimate (10s); measured speech is 4s.
    scenes = [{"id": "s", "duration_sec": 10, "layers": [
        {"source_panel_id": "a", "start_offset_sec": 0.0, "duration_sec": 5.0},
        {"source_panel_id": "b", "start_offset_sec": 5.0, "duration_sec": 5.0}]}]
    clips = [{"id": "c", "scene_id": "s", "duration_sec": 4.0}]
    synchronize_narration(scenes, clips)
    layers = scenes[0]["layers"]
    assert scenes[0]["duration_sec"] == 4.1
    assert layers[1]["start_offset_sec"] < scenes[0]["duration_sec"]
    assert abs(sum(l["duration_sec"] for l in layers) - 4.1) < 0.01


def test_recap_lines_cut_on_their_panel_even_with_repeats():
    # Recap style: one short line per panel; two lines on panel b, one line cites nothing new.
    scenes = [{"id": "s", "duration_sec": 1, "layers": [{"source_panel_id": p} for p in "abcd"]}]
    plan = [("a", 2.0), ("b", 1.5), ("b", 1.0), ("a", 0.5), ("d", 2.0)]
    clips = [{"id": str(i), "scene_id": "s", "duration_sec": d, "source_evidence": {"panel_ids": [p]}}
             for i, (p, d) in enumerate(plan)]
    synchronize_narration(scenes, clips)
    starts = {l["source_panel_id"]: l["start_offset_sec"] for l in scenes[0]["layers"]}
    assert starts["a"] == 0.0
    assert starts["b"] == 2.0  # cut lands when the first "b" line starts
    assert starts["d"] == 5.0  # repeat and backward lines keep b/c on screen until "d"
    assert starts["b"] < starts["c"] < starts["d"]  # uncited c stays visible
    assert abs(sum(l["duration_sec"] for l in scenes[0]["layers"]) - scenes[0]["duration_sec"]) < 1e-6


def test_single_panel_per_clip_follows_measured_audio():
    scenes = [{"id": "s", "duration_sec": 10, "layers": [{"source_panel_id": p} for p in ['a', 'b']]}]
    clips = [{"id": p, "scene_id": "s", "duration_sec": d, "source_evidence": {"panel_ids": [p]}}
             for p, d in [('a', 3.1), ('b', 5.2)]]
    synchronize_narration(scenes, clips)
    assert scenes[0]['layers'][1]['start_offset_sec'] == 3.1
    assert clips[1]['start_time_sec'] == 3.1
