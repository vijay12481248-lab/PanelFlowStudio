"""
Unit tests for CameraRenderer (Milestone 7).
Verifies camera pan/zoom crop calculations, aspect ratio fitting (COVER, CONTAIN), and background fills.
"""
from PIL import Image, ImageDraw
import numpy as np
import pytest

from engine.motion.models.camera import CameraState, NormalizedRect
from engine.motion.models.enums import MotionType, EasingFunction
from engine.render.composer import CameraRenderer
from engine.render.models.render_plan import RenderShotPlan
from engine.render.models.enums import ScalePolicy, BackgroundFillPolicy


def test_subpixel_camera_motion_does_not_snap_to_integer_crops():
    pattern = np.zeros((64, 64, 3), dtype=np.uint8)
    pattern[:, ::2] = 255
    source = Image.fromarray(pattern)
    shot = RenderShotPlan(shot_id="smooth", scene_id="scene", sequence_global=1,
                          source_asset_path="fixture", start_frame=0, end_frame=30, total_frames=30,
                          start_time=0, end_time=1, duration=1, scale_policy=ScalePolicy.CONTAIN,
                          camera_start=CameraState(center_x=0.5, center_y=0.5, zoom=1.2),
                          camera_end=CameraState(center_x=0.501, center_y=0.5, zoom=1.2))
    renderer = CameraRenderer()
    start = np.asarray(renderer.render_camera_view(source, shot, 0, 256, 256))
    end = np.asarray(renderer.render_camera_view(source, shot, 1, 256, 256))
    assert not np.array_equal(start, end)


@pytest.fixture
def test_portrait_image():
    """Create a 1000x1500 portrait test pattern image."""
    img = Image.new("RGB", (1000, 1500), color=(100, 120, 150))
    draw = ImageDraw.Draw(img)
    # Draw distinct markings
    draw.rectangle([100, 100, 400, 400], fill=(255, 0, 0))  # Top-left red
    draw.rectangle([600, 1100, 900, 1400], fill=(0, 255, 0))  # Bottom-right green
    draw.rectangle([400, 650, 600, 850], fill=(0, 0, 255))  # Center blue
    return img


def test_camera_renderer_cover(test_portrait_image):
    renderer = CameraRenderer()
    shot = RenderShotPlan(
        shot_id="shot_cover",
        scene_id="sc_01",
        sequence_global=1,
        source_asset_path="dummy.jpg",
        start_frame=0,
        end_frame=30,
        total_frames=30,
        start_time=0.0,
        end_time=1.0,
        duration=1.0,
        camera_start=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        camera_end=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        scale_policy=ScalePolicy.COVER,
        fill_policy=BackgroundFillPolicy.BLACK,
    )

    rendered = renderer.render_camera_view(
        source_img=test_portrait_image,
        shot_plan=shot,
        t_normalized=0.5,
        target_w=1920,
        target_h=1080,
    )

    assert rendered.size == (1920, 1080)
    arr = np.array(rendered)
    # Check that image is not completely blank/black
    assert arr.mean() > 20.0


def test_camera_renderer_contain_black(test_portrait_image):
    renderer = CameraRenderer()
    shot = RenderShotPlan(
        shot_id="shot_contain",
        scene_id="sc_01",
        sequence_global=1,
        source_asset_path="dummy.jpg",
        start_frame=0,
        end_frame=30,
        total_frames=30,
        start_time=0.0,
        end_time=1.0,
        duration=1.0,
        camera_start=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        camera_end=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        scale_policy=ScalePolicy.CONTAIN,
        fill_policy=BackgroundFillPolicy.BLACK,
    )

    rendered = renderer.render_camera_view(
        source_img=test_portrait_image,
        shot_plan=shot,
        t_normalized=0.5,
        target_w=1920,
        target_h=1080,
    )

    assert rendered.size == (1920, 1080)
    arr = np.array(rendered)
    # For a portrait image on 16:9 canvas with CONTAIN and BLACK fill,
    # far left and far right columns must be solid black [0, 0, 0]
    left_pillar = arr[:, :50, :]
    right_pillar = arr[:, -50:, :]
    assert np.all(left_pillar == 0)
    assert np.all(right_pillar == 0)


def test_camera_renderer_contain_blurred_source(test_portrait_image):
    renderer = CameraRenderer()
    shot = RenderShotPlan(
        shot_id="shot_blurred",
        scene_id="sc_01",
        sequence_global=1,
        source_asset_path="dummy.jpg",
        start_frame=0,
        end_frame=30,
        total_frames=30,
        start_time=0.0,
        end_time=1.0,
        duration=1.0,
        camera_start=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        camera_end=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        scale_policy=ScalePolicy.CONTAIN,
        fill_policy=BackgroundFillPolicy.BLURRED_SOURCE,
    )

    rendered = renderer.render_camera_view(
        source_img=test_portrait_image,
        shot_plan=shot,
        t_normalized=0.5,
        target_w=1920,
        target_h=1080,
    )

    assert rendered.size == (1920, 1080)
    arr = np.array(rendered)
    # The sides should NOT be solid black because of blurred source background
    left_pillar = arr[:, :50, :]
    assert left_pillar.mean() > 10.0


def test_camera_renderer_pan_motion(test_portrait_image):
    renderer = CameraRenderer()
    shot = RenderShotPlan(
        shot_id="shot_pan",
        scene_id="sc_01",
        sequence_global=1,
        source_asset_path="dummy.jpg",
        start_frame=0,
        end_frame=60,
        total_frames=60,
        start_time=0.0,
        end_time=2.0,
        duration=2.0,
        camera_start=CameraState(center_x=0.2, center_y=0.2, zoom=1.5),
        camera_end=CameraState(center_x=0.8, center_y=0.8, zoom=1.5),
        motion_type=MotionType.PAN_RIGHT,
        easing=EasingFunction.LINEAR,
        scale_policy=ScalePolicy.COVER,
    )

    frame_start = renderer.render_camera_view(test_portrait_image, shot, t_normalized=0.0, target_w=1920, target_h=1080)
    frame_end = renderer.render_camera_view(test_portrait_image, shot, t_normalized=1.0, target_w=1920, target_h=1080)

    arr_start = np.array(frame_start)
    arr_end = np.array(frame_end)

    # They must have different visual contents due to pan from top-left (red area) to bottom-right (green area)
    diff = np.abs(arr_start.astype(float) - arr_end.astype(float)).mean()
    assert diff > 15.0
