"""Real-frame regression coverage for the optional Smart Background branch."""
import pytest
from PIL import Image
from pydantic import ValidationError

from engine.render.compiler import TimelineCompiler
from engine.render.composer import FrameComposer
from engine.render.models.profiles import RenderProfile


def state_for(tmp_path, background=None):
    path = tmp_path / "art.png"
    Image.new("RGB", (40, 80), "red").save(path)
    scene = {"id": "scene", "duration_sec": 2, "layers": [{
        "id": "red", "image_url": str(path), "duration_sec": 1,
        "crop": {"x": 0, "y": 0, "width": 1, "height": 1},
    }]}
    if background is not None:
        scene["background"] = background
    return {"scenes": [scene]}


def compile_state(state, tmp_path, width=160, height=90):
    return TimelineCompiler().compile(state, "project", tmp_path, RenderProfile(width=width, height=height))


def settings(**updates):
    return {"enabled": True, "preset": "duplicate_blur", "brightness": 0, "saturation": 1, **updates}


def test_enabled_fills_canvas_and_foreground_uses_full_height(tmp_path):
    plan = compile_state(state_for(tmp_path, settings()), tmp_path)
    assert plan.shots[0].background is not None
    frame = FrameComposer().compose_frame(0, plan)
    assert frame.getpixel((0, 45)) == (255, 0, 0)
    assert frame.getpixel((80, 0)) == (255, 0, 0)


def test_disabled_matches_legacy_byte_for_byte(tmp_path):
    old = compile_state(state_for(tmp_path), tmp_path)
    disabled = compile_state(state_for(tmp_path, settings(enabled=False)), tmp_path)
    composer = FrameComposer()
    assert composer.compose_frame(0, old).tobytes() == composer.compose_frame(0, disabled).tobytes()


def test_default_inherits_and_explicit_disabled_overrides(tmp_path):
    state = state_for(tmp_path)
    state["background_default"] = settings()
    assert compile_state(state, tmp_path).shots[0].background.enabled
    state["scenes"][0]["background"] = {"enabled": False}
    assert not compile_state(state, tmp_path).shots[0].background.enabled


def test_background_follows_active_layer_and_ignores_hidden_layers(tmp_path):
    state = state_for(tmp_path, settings())
    blue = tmp_path / "blue.png"
    Image.new("RGB", (40, 80), "blue").save(blue)
    state["scenes"][0]["layers"].append({"id": "blue", "image_url": str(blue), "start_offset_sec": 1, "duration_sec": 1})
    plan = compile_state(state, tmp_path)
    composer = FrameComposer()
    assert composer.compose_frame(0, plan).getpixel((0, 45)) == (255, 0, 0)
    assert composer.compose_frame(45, plan).getpixel((0, 45)) == (0, 0, 255)
    state["track_states"] = {"Visuals": {"visible": False}}
    assert FrameComposer().compose_frame(0, compile_state(state, tmp_path)).getpixel((0, 45)) == (9, 9, 11)


def test_both_branches_share_crop_and_pre_extracted_assets_are_not_recropped(tmp_path):
    state = state_for(tmp_path, settings())
    img = Image.new("RGB", (80, 80), "blue")
    img.paste("red", (0, 0, 40, 80))
    img.save(tmp_path / "art.png")
    state["scenes"][0]["layers"][0]["crop"] = {"x": 0, "y": 0, "width": .5, "height": 1}
    frame = FrameComposer().compose_frame(0, compile_state(state, tmp_path))
    assert frame.getpixel((0, 45)) == frame.getpixel((80, 45)) == (255, 0, 0)
    plan = compile_state(state, tmp_path)
    plan.shots[0].scene_layers[0]["already_cropped"] = True
    frame = FrameComposer().compose_frame(0, plan)
    assert frame.getpixel((120, 45)) == (0, 0, 255)


@pytest.mark.parametrize("bad", [{"version": 2}, {"zoom": 0}, {"blur_sigma": float("nan")}, {"brightness": 2}, {"color": "red"}, {"preset": "custom_video"}])
def test_schema_rejects_invalid_values(tmp_path, bad):
    with pytest.raises(ValidationError):
        compile_state(state_for(tmp_path, settings(**bad)), tmp_path)


def test_custom_source_missing_never_uses_unrelated_page(tmp_path):
    state = state_for(tmp_path, settings(preset="custom_image", custom_image_url="/api/projects/project/backgrounds/missing.png"))
    with pytest.raises(ValueError, match="[Bb]ackground.*(missing|upload|found)"):
        compile_state(state, tmp_path)


def test_custom_source_resolves_only_workspace_background_or_known_layer(tmp_path):
    state = state_for(tmp_path, settings(preset="custom_image", custom_image_url="/api/projects/project/backgrounds/fill.png"))
    (tmp_path / "backgrounds").mkdir()
    Image.new("RGBA", (20, 20), (0, 255, 0, 255)).save(tmp_path / "backgrounds/fill.png")
    plan = compile_state(state, tmp_path)
    assert FrameComposer().compose_frame(0, plan).getpixel((0, 45)) == (0, 255, 0)
    state["scenes"][0]["background"]["custom_image_url"] = str(tmp_path / "backgrounds/fill.png")
    with pytest.raises(ValueError, match="[Bb]ackground"):
        compile_state(state, tmp_path)


def test_alpha_source_composites_over_solid_base(tmp_path):
    state = state_for(tmp_path, settings(color="#00ff00"))
    Image.new("RGBA", (40, 80), (255, 0, 0, 0)).save(tmp_path / "art.png")
    assert FrameComposer().compose_frame(0, compile_state(state, tmp_path)).getpixel((0, 45)) == (0, 255, 0)


def test_solid_still_draws_when_aspect_matches(tmp_path):
    state = state_for(tmp_path, settings(preset="solid", color="#00ff00"))
    Image.new("RGBA", (160, 90), (255, 0, 0, 0)).save(tmp_path / "art.png")
    assert FrameComposer().compose_frame(0, compile_state(state, tmp_path)).getpixel((0, 45)) == (0, 255, 0)


def test_custom_background_file_resource_url_with_capability_suffix(tmp_path):
    filename = "a" * 32 + ".png"
    (tmp_path / "backgrounds").mkdir()
    Image.new("RGB", (10, 10), "green").save(tmp_path / "backgrounds" / filename)
    state = state_for(tmp_path, settings(preset="custom_image", custom_image_url=f"http://localhost:8765/api/projects/project/backgrounds/{filename}/file;pf-token=secret?x=1"))
    assert compile_state(state, tmp_path).shots[0].background_image_path == str((tmp_path / "backgrounds" / filename).resolve())


def test_sigma_normalization_and_additive_brightness():
    from engine.render.composer import background_sigma, build_background
    from engine.render.models.background import BackgroundSettings
    assert background_sigma(32, 1920, 1080) == 32
    assert background_sigma(32, 1080, 1920) == pytest.approx(32 * 1920 / 1080)
    assert background_sigma(32, 3840, 2160) == 64
    config = BackgroundSettings(**settings(blur_sigma=0, brightness=-.1, auto_only_when_needed=False))
    frame = build_background(Image.new("RGB", (10, 20), (100, 100, 100)), config, (100, 60))
    assert frame.getpixel((0, 0))[:3] == (74, 74, 74)


@pytest.mark.parametrize("preset", ["solid", "duplicate_blur", "gradient", "mirror", "edge_stretch", "custom_image"])
def test_composable_effects_and_motion_are_deterministic(preset):
    from engine.render.composer import build_background
    from engine.render.models.background import BackgroundSettings
    img = Image.new("RGBA", (30, 60), "red")
    img.paste("blue", (15, 0, 30, 60))
    cfg = BackgroundSettings(**settings(preset=preset, vignette=.3, glow=.2, tint_opacity=.2,
                                         motion="pan_left", motion_amount=.2))
    frame = build_background(img, cfg, (160, 90), .4)
    assert frame.size == (160, 90)
    assert frame.tobytes() == build_background(img, cfg, (160, 90), .4).tobytes()


def test_frame_time_uses_profile_fps(tmp_path):
    state = state_for(tmp_path, settings())
    blue = tmp_path / "blue.png"
    Image.new("RGB", (40, 80), "blue").save(blue)
    state["scenes"][0]["layers"].append({"id": "blue", "image_url": str(blue), "start_offset_sec": 1, "duration_sec": 1})
    plan = TimelineCompiler().compile(state, "project", tmp_path, RenderProfile(width=160, height=90, fps=60))
    assert FrameComposer().compose_frame(45, plan).getpixel((0, 45)) == (255, 0, 0)


def test_exif_orientation_applies_before_foreground_and_fill(tmp_path):
    state = state_for(tmp_path, settings())
    path = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (80, 40), "red").save(path, exif=exif)
    state["scenes"][0]["layers"][0]["image_url"] = str(path)
    plan = compile_state(state, tmp_path)
    composer = FrameComposer()
    assert composer.get_source_image(str(path.resolve()), 160, 90, True).size == (40, 80)
    assert composer.compose_frame(0, plan).getpixel((80, 0))[0] > 250


def test_preflight_reports_invalid_background_as_blocker(tmp_path):
    state = state_for(tmp_path, settings(preset="custom_image", custom_image_url="/missing.png"))
    result = TimelineCompiler().preflight_validate(state, "project", tmp_path)
    assert not result["valid"]
    assert any("Background" in message for message in result["blockers"])


def test_pinned_missing_media_never_uses_arbitrary_workspace_page(tmp_path):
    state = state_for(tmp_path, settings(source_mode="pinned_layer", source_layer_id="red"))
    state["scenes"][0]["layers"][0]["image_url"] = "missing.png"
    (tmp_path / "pages").mkdir()
    Image.new("RGB", (20, 40), "blue").save(tmp_path / "pages/unrelated.png")
    with pytest.raises(ValueError, match="Background pinned layer is missing"):
        compile_state(state, tmp_path)


def test_pinned_stays_fixed_when_layer_inactive(tmp_path):
    state = state_for(tmp_path, settings(source_mode="pinned_layer", source_layer_id="red"))
    state["scenes"][0]["layers"][0]["visible"] = False
    frame = FrameComposer().compose_frame(45, compile_state(state, tmp_path))
    assert frame.getpixel((0, 45)) == (255, 0, 0)


def test_solid_without_visual_layers_renders_canvas(tmp_path):
    state = state_for(tmp_path, settings(preset="solid", color="#00ff00"))
    state["scenes"][0]["layers"] = []
    assert FrameComposer().compose_frame(0, compile_state(state, tmp_path)).getpixel((0, 45)) == (0, 255, 0)


def test_background_opacity_scales_alpha_once():
    from engine.render.composer import build_background
    from engine.render.models.background import BackgroundSettings
    cfg = BackgroundSettings(**settings(color="#000000", opacity=.5, blur_sigma=0, auto_only_when_needed=False))
    pixel = build_background(Image.new("RGBA", (10, 20), "red"), cfg, (100, 60)).getpixel((0, 0))
    assert pixel[:3] == (128, 0, 0)


def test_auto_keeps_fill_when_matching_source_is_scaled_down(tmp_path):
    state = state_for(tmp_path, settings())
    Image.new("RGB", (160, 90), "red").save(tmp_path / "art.png")
    state["scenes"][0]["layers"][0]["transform"] = {"scale": .5}
    assert FrameComposer().compose_frame(0, compile_state(state, tmp_path)).getpixel((0, 45)) == (255, 0, 0)


def test_ffmpeg_1080p_duplicate_blur_export(tmp_path):
    import subprocess
    import json
    from engine.render.engine import RenderEngine

    engine = RenderEngine()
    if not engine.encoder.check_runtime()["available"]:
        pytest.skip("FFmpeg not available")

    art_path = tmp_path / "portrait_manga.png"
    art = Image.new("RGB", (600, 1000), (220, 50, 80))
    for y in range(400, 600):
        for x in range(200, 400):
            art.putpixel((x, y), (50, 180, 220))
    art.save(art_path)

    state = {
        "project_id": "test_bg_1080p",
        "aspect_ratio": "16:9",
        "scenes": [{
            "id": "scene_portrait",
            "duration_sec": 1.0,
            "background": {
                "enabled": True,
                "preset": "duplicate_blur",
                "blur_sigma": 32,
                "brightness": -0.04,
                "saturation": 0.85,
                "zoom": 1.0,
                "focal_x": 0.5,
                "focal_y": 0.5,
                "foreground_fit": "contain",
                "foreground_x": 0.5,
                "foreground_y": 0.5,
            },
            "layers": [{
                "id": "manga_panel",
                "image_url": str(art_path),
                "duration_sec": 1.0,
                "crop": {"x": 0, "y": 0, "width": 1.0, "height": 1.0},
                "transform": {"x": 0, "y": 0, "scale": 1.0, "rotation": 0, "opacity": 1.0},
            }],
        }]
    }

    profile = RenderProfile(width=1920, height=1080, fps=30, preset="ultrafast")
    plan = TimelineCompiler().compile(state, "test_bg_1080p", tmp_path, profile=profile)
    output_mp4 = tmp_path / "smart_bg_1080p.mp4"
    report = engine.execute_render(plan, output_mp4, workspace_dir=tmp_path / "work")

    assert output_mp4.is_file(), report.model_dump()
    assert report.is_valid, report.model_dump()

    probe = subprocess.run([
        engine.encoder.ffprobe_path, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(output_mp4)
    ], check=True, capture_output=True, text=True)
    meta = json.loads(probe.stdout)
    video = next(s for s in meta["streams"] if s["codec_type"] == "video")
    assert video["width"] == 1920
    assert video["height"] == 1080
    assert int(video["nb_frames"]) == 30

    decoded = subprocess.run([
        engine.encoder.ffmpeg_path, "-v", "error", "-i", str(output_mp4),
        "-vf", "select=eq(n\\,15)", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"
    ], check=True, capture_output=True)

    frame_bytes = decoded.stdout
    assert len(frame_bytes) == 1920 * 1080 * 3

    def get_pixel(x, y):
        offset = (y * 1920 + x) * 3
        return tuple(frame_bytes[offset:offset + 3])

    center_px = get_pixel(960, 540)
    assert center_px[1] > 120 and center_px[2] > 150, f"Expected foreground pattern at center: {center_px}"

    left_px = get_pixel(150, 540)
    assert max(left_px) > 30, f"Expected blurred fill on left side, got: {left_px}"

    right_px = get_pixel(1770, 540)
    assert max(right_px) > 30, f"Expected blurred fill on right side, got: {right_px}"
