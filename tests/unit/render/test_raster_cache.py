import pytest
from PIL import Image

from engine.render.composer import FrameComposer
from engine.render.compiler import TimelineCompiler
from engine.render.models.profiles import RenderProfile


@pytest.mark.parametrize("preset", ["none", "pan_left", "slow_zoom_in", "rotate_cw", "fade_out", "blur"])
@pytest.mark.parametrize("smart", [False, True])
def test_cached_frames_match_uncached_during_animation(tmp_path, preset, smart):
    path = tmp_path / "source.png"
    image = Image.new("RGBA", (160, 200), (30, 90, 180, 190))
    image.paste((240, 180, 20, 255), (30, 20, 110, 150))
    image.save(path)
    scene = {"id": "scene", "duration_sec": 2, "camera": {"preset": "pan_right"},
             "layers": [{"id": "art", "image_url": str(path), "duration_sec": 2,
                         "motion_preset": preset, "transform": {"rotation": 12, "opacity": .8},
                         "crop": {"x": .1, "y": .1, "width": .8, "height": .8}}]}
    if smart:
        scene["background"] = {"enabled": True, "preset": "duplicate_blur", "edge_shadow": .4}
    plan = TimelineCompiler().compile({"scenes": [scene]}, "p", tmp_path, RenderProfile(width=160, height=90))
    cached, uncached = FrameComposer(), FrameComposer(raster_cache_bytes=0)
    for frame in [0, 1, 5, 20, 40, 59, 0]:
        assert cached.compose_frame(frame, plan).tobytes() == uncached.compose_frame(frame, plan).tobytes()


def test_static_transform_reuses_raster_and_does_not_reuse_changed_opacity():
    composer = FrameComposer()
    source = Image.new("RGBA", (100, 100), "red")
    a = composer._prepare_layer_raster(source, "source", 50, 50, 0, 0, 1)
    assert composer._prepare_layer_raster(source, "source", 50, 50, 0, 0, 1) is a
    b = composer._prepare_layer_raster(source, "source", 50, 50, 0, 0, .5)
    assert a.getpixel((0, 0))[3] == 255
    assert b.getpixel((0, 0))[3] == 128


def test_source_and_raster_caches_are_bounded_and_clearable(tmp_path):
    composer = FrameComposer(source_cache_bytes=800, raster_cache_bytes=800)
    for i in range(5):
        path = tmp_path / f"{i}.png"
        Image.new("RGBA", (10, 10), (i, 0, 0, 255)).save(path)
        image = composer.get_source_image(str(path), 10, 10)
        composer._prepare_layer_raster(image, str(path), 10, 10, 0, 0, 1)
    assert len(composer._image_cache) == len(composer._raster_cache) == 2
    assert composer._image_cache_bytes <= 800
    assert composer._raster_cache_bytes <= 800
    composer.clear_cache(str(path))
    assert composer._image_cache_bytes == 400
    assert composer._raster_cache_bytes == 0
    composer.clear_cache()
    assert composer._image_cache_bytes == 0


def test_explicit_invalidation_uses_updated_source(tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGBA", (10, 10), "red").save(path)
    composer = FrameComposer()
    composer._prepare_layer_raster(composer.get_source_image(str(path), 10, 10), str(path), 10, 10, 0, 0, 1)
    Image.new("RGBA", (10, 10), "blue").save(path)
    composer.clear_cache(str(path))
    actual = composer._prepare_layer_raster(composer.get_source_image(str(path), 10, 10), str(path), 10, 10, 0, 0, 1)
    assert actual.getpixel((0, 0)) == (0, 0, 255, 255)
