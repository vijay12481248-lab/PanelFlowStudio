"""Absolute Story Editor timing through production compilation and composition."""
from pathlib import Path
import json
import subprocess

from PIL import Image

from engine.render.compiler import TimelineCompiler
from engine.render.composer import FrameComposer
from engine.render.engine import RenderEngine
from engine.render.models.profiles import RenderProfile


def timing_state(tmp_path: Path):
    scenes = []
    for name, color, start in [("a", "red", 0), ("b", "blue", 6)]:
        image = tmp_path / f"{name}.png"
        Image.new("RGB", (64, 64), color).save(image)
        scenes.append({"id": name, "title": name, "start_time_sec": start, "duration_sec": 4,
                       "layers": [{"id": name, "image_url": str(image), "motion_preset": "none",
                                   "transform": {"x": 0, "y": 0, "scale": 1, "opacity": 1, "z_index": 0}}]})
    return {"scenes": scenes, "ripple_edit": False}


def test_preflight_duration_includes_fixed_start_gap(tmp_path):
    state = timing_state(tmp_path)
    result = TimelineCompiler().preflight_validate(state, "ripple-gap", tmp_path)
    assert result["stats"]["planned_duration_sec"] == 10
    assert result["stats"]["total_frames_30fps"] == 300


def test_composed_gap_is_black_and_next_scene_starts_at_six(tmp_path):
    plan = TimelineCompiler().compile(timing_state(tmp_path), "ripple-gap", tmp_path,
                                      profile=RenderProfile(width=64, height=64, fps=30))
    composer = FrameComposer()
    assert composer.compose_frame(119, plan).getpixel((32, 32)) == (255, 0, 0)
    assert composer.compose_frame(120, plan).getpixel((32, 32)) == (0, 0, 0)
    assert composer.compose_frame(179, plan).getpixel((32, 32)) == (0, 0, 0)
    assert composer.compose_frame(180, plan).getpixel((32, 32)) == (0, 0, 255)
    assert plan.total_duration_sec == 10


def test_legacy_missing_and_stale_scene_starts_keep_contiguous_fallback(tmp_path):
    for start in (None, 0, float("nan")):
        state = timing_state(tmp_path)
        state["scenes"][1]["start_time_sec"] = start
        plan = TimelineCompiler().compile(state, "legacy-timing", tmp_path)
        assert [(shot.start_time, shot.end_time) for shot in plan.shots] == [(0, 4), (4, 8)]
        assert TimelineCompiler().preflight_validate(state, "legacy-timing", tmp_path)["stats"]["planned_duration_sec"] == 8


def test_leading_gap_is_black_without_changing_legacy_motion_hold_behavior(tmp_path):
    state = timing_state(tmp_path)
    state["scenes"][0]["start_time_sec"] = 1
    plan = TimelineCompiler().compile(state, "leading-gap", tmp_path, profile=RenderProfile(width=64, height=64))
    assert FrameComposer().compose_frame(0, plan).getpixel((32, 32)) == (0, 0, 0)
    legacy = plan.model_copy(update={"metadata": {}})
    assert FrameComposer().compose_frame(0, legacy).getpixel((32, 32)) != (0, 0, 0)


def test_linked_audio_export_uses_parent_offset_like_editor_restore(tmp_path):
    import wave
    audio = tmp_path / "fixture-voice.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 8000)
    state = timing_state(tmp_path)
    state["narration_clips"] = [{"id": "voice", "scene_id": "b", "linked_to_scene": True,
                                  "scene_offset_sec": 0.5, "start_time_sec": 4.5, "duration_sec": 1,
                                  "audio_url": str(audio), "text": "Fixture voice"}]
    plan = TimelineCompiler().compile(state, "ripple-audio", tmp_path, subtitle_enabled=True)
    assert plan.audio_tracks[0].start_time == 6.5
    assert plan.shots[1].captions[0].start_time == 6.5
    state["narration_clips"][0]["linked_to_scene"] = False
    floating = TimelineCompiler().compile(state, "ripple-audio", tmp_path)
    assert floating.audio_tracks[0].start_time == 4.5


def test_plan_hash_changes_when_gap_changes_but_total_duration_does_not(tmp_path):
    state = timing_state(tmp_path)
    compiler = TimelineCompiler()
    before = compiler.compile(state, "ripple-hash", tmp_path)
    state["scenes"][0]["duration_sec"] = 6
    after = compiler.compile(state, "ripple-hash", tmp_path)
    assert before.total_duration_sec == after.total_duration_sec
    assert before.hash != after.hash


def test_ffmpeg_export_preserves_black_gap_and_fixed_later_start(tmp_path):
    engine = RenderEngine()
    assert engine.encoder.check_runtime()["available"], "Acceptance requires a real installed FFmpeg"
    assert engine.encoder.ffmpeg_path and engine.encoder.ffprobe_path
    plan = TimelineCompiler().compile(timing_state(tmp_path), "ripple-gap-mp4", tmp_path,
                                      profile=RenderProfile(width=64, height=64, fps=30, preset="ultrafast"))
    output = tmp_path / "ripple-gap.mp4"
    report = engine.execute_render(plan, output, workspace_dir=tmp_path / "render")
    assert output.is_file(), report.model_dump()
    assert report.is_valid, report.model_dump()
    probe = subprocess.run([engine.encoder.ffprobe_path, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(output)],
                           check=True, capture_output=True, text=True)
    metadata = json.loads(probe.stdout)
    assert abs(float(metadata["format"]["duration"]) - 10) < 0.1
    video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
    assert int(video["nb_frames"]) == 300
    for index, expected in [(119, "red"), (120, "black"), (150, "black"), (179, "black"), (180, "blue")]:
        decoded = subprocess.run([engine.encoder.ffmpeg_path, "-v", "error", "-i", str(output), "-vf", f"select=eq(n\\,{index})", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                                 check=True, capture_output=True)
        offset = (32 * 64 + 32) * 3
        red, green, blue = decoded.stdout[offset:offset + 3]
        if expected == "black":
            assert max(red, green, blue) <= 3, (index, red, green, blue)
        elif expected == "red":
            assert red > 240 and green < 10 and blue < 10
        else:
            assert blue > 240 and red < 10 and green < 10
