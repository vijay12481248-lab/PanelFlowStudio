"""Framed recap layout: panels keep their own size over a blurred backdrop and move without jitter."""
import numpy as np
from PIL import Image

from engine.render.compiler import TimelineCompiler
from engine.render.composer import FrameComposer
from engine.render.models.profiles import RenderProfile
from engine.render.motion.effects.ambient import AmbientDust

W, H = 320, 180


def compose(tmp_path, size, frames, background=None, layer_extra=None):
    art = tmp_path / "art.png"
    Image.new("RGB", size, (255, 0, 0)).save(art)
    layer = {"id": "p", "image_url": str(art), "duration_sec": 2, "crop": {"x": 0, "y": 0, "width": 1, "height": 1},
             **(layer_extra or {})}
    bg = {"enabled": True, "preset": "solid", "color": "#000000", "foreground_fit": "contain",
          "auto_only_when_needed": False, **(background or {})}
    state = {"scenes": [{"id": "s", "duration_sec": 2, "layers": [layer], "background": bg}]}
    plan = TimelineCompiler().compile(state, "project", tmp_path, RenderProfile(width=W, height=H))
    composer = FrameComposer()
    return [np.asarray(composer.compose_frame(f, plan).convert("RGB"), dtype=np.float32) for f in frames]


def red_box(frame):
    mask = frame[:, :, 0] > 200
    ys, xs = np.where(mask)
    return xs.min(), xs.max(), ys.min(), ys.max()


def test_small_panel_is_not_blown_up_to_fill_the_screen(tmp_path):
    [frame] = compose(tmp_path, (20, 20), [30])
    x0, x1, y0, y1 = red_box(frame)
    assert 20 <= x1 - x0 + 1 <= 24 and 20 <= y1 - y0 + 1 <= 24  # at most 1.15x its real pixels
    assert frame[0, 0].max() == 0  # the rest of the screen is backdrop


def test_wide_panel_leaves_room_for_the_backdrop(tmp_path):
    [frame] = compose(tmp_path, (1920, 1080), [30])
    x0, x1, y0, y1 = red_box(frame)
    assert x0 >= W * 0.05 and W - 1 - x1 >= W * 0.05 and y0 >= H * 0.05  # no full-bleed 16:9 panel


def test_slow_move_is_smooth_at_sub_pixel_steps(tmp_path):
    frames = compose(tmp_path, (40, 80), range(20, 32), layer_extra={"motion_preset": "move_right"})
    centroid = []
    for f in frames:
        red = f[:, :, 0]
        centroid.append((red.sum(axis=0) * np.arange(W)).sum() / red.sum())
    steps = np.diff(centroid)
    # Whole-pixel rounding moves the panel 0 or 1 px per frame; fractional drawing changes pace gradually.
    assert steps.min() > 0.2 and np.abs(np.diff(steps)).max() < 0.05, steps


def test_new_panel_slides_in_then_settles(tmp_path):
    first, settled = compose(tmp_path, (40, 80), [0, 30])
    assert red_box(first)[0] > red_box(settled)[0] + 10  # starts to the right
    assert red_box(first)[1] <= W - 1                    # but is already on screen on its first frame


def test_particles_are_deterministic_and_off_by_default(tmp_path):
    dust = AmbientDust((160, 90))
    a, b = dust.mask(3.0), AmbientDust((160, 90)).mask(3.0)
    assert np.array_equal(a, b) and a.max() > 0.2 and not np.array_equal(a, dust.mask(3.5))
    [plain] = compose(tmp_path, (20, 20), [30])
    [lit] = compose(tmp_path, (20, 20), [30], background={"particles": True})
    assert (lit > plain).any() and not (lit < plain).any()  # particles only ever add light
