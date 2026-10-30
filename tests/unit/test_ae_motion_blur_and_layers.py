"""
Unit tests for Adobe After Effects Motion Blur & Layer Compositing (Parenting & Track Mattes).
"""

import pytest
from PIL import Image, ImageDraw
import numpy as np
from engine.render.motion.ae import AEMotionBlur, AELayer


def test_ae_motion_blur_temporal_accumulation():
    """Verify that motion blur smoothly accumulates moving objects across sub-frame samples."""
    blur_engine = AEMotionBlur(shutter_angle=180.0, samples_per_frame=4)

    def render_moving_dot(t: float) -> Image.Image:
        img = Image.new("RGBA", (200, 100), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)
        # Dot moves horizontally with speed 200 px/sec
        x = int(50 + t * 200.0)
        draw.rectangle([x, 40, x + 10, 60], fill=(255, 255, 255, 255))
        return img

    sharp_frame = render_moving_dot(0.1)
    blurred_frame = blur_engine.render_blurred_frame(render_moving_dot, t_sec=0.1, fps=60.0)

    assert sharp_frame.size == blurred_frame.size

    # In sharp frame, pixels are either 0 or 255
    sharp_arr = np.array(sharp_frame.convert("L"))
    blurred_arr = np.array(blurred_frame.convert("L"))

    # In blurred frame, intermediate gray values exist from temporal exposure accumulation
    intermediate_pixels = np.sum((blurred_arr > 10) & (blurred_arr < 240))
    assert intermediate_pixels > 0


def test_ae_layer_parenting_hierarchy():
    """Child layer should inherit parent translation and rotation around anchor point."""
    parent = AELayer(
        name="Null Controller",
        position=(500.0, 300.0),
        rotation=90.0,
        scale=(1.0, 1.0),
    )
    child = AELayer(
        name="Follower Item",
        position=(100.0, 0.0),  # 100px to the right of parent in local space
        parent=parent,
    )

    wx, wy, wrot, wsx, wsy = child.compute_world_transform()
    assert abs(wrot - 90.0) < 0.1
    # Rotated 90 deg clockwise, +100px in X becomes +100px in Y
    assert abs(wx - 500.0) < 0.1
    assert abs(wy - 400.0) < 0.1


def test_ae_track_matte_alpha():
    """Alpha track matte masks pixels according to the matte's alpha channel."""
    layer_img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))  # Solid red
    matte_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(matte_img)
    # Circle in center with 255 alpha
    draw.ellipse([25, 25, 75, 75], fill=(0, 0, 0, 255))

    matted = AELayer.apply_track_matte(layer_img, matte_img, mode="alpha")
    arr = np.array(matted)

    # Center must remain opaque red
    assert arr[50, 50, 3] == 255
    # Corner must be transparent
    assert arr[5, 5, 3] == 0


def test_ae_track_matte_luma():
    """Luma track matte masks pixels according to the matte's RGB luminance."""
    layer_img = Image.new("RGBA", (100, 100), (0, 255, 0, 255))  # Solid green
    matte_img = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    draw = ImageDraw.Draw(matte_img)
    # Draw black square (zero luminance) in top half
    draw.rectangle([0, 0, 100, 50], fill=(0, 0, 0, 255))

    matted = AELayer.apply_track_matte(layer_img, matte_img, mode="luma")
    arr = np.array(matted)

    # Top half (black matte) should have 0 alpha
    assert arr[25, 50, 3] == 0
    # Bottom half (white matte) should have 255 alpha
    assert arr[75, 50, 3] == 255
