import io

from PIL import Image

from engine.original.anatomy.tiles import Tile, make_tiles


def _png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "orange").save(buf, "PNG")
    return buf.getvalue()


def test_portrait_picture_gives_whole_and_three_overlapping_bands():
    tiles = make_tiles(_png(768, 1344))
    assert [t.name for t in tiles] == ["whole", "upper", "middle", "lower"]
    by = {t.name: t for t in tiles}
    assert by["upper"].box[3] > by["middle"].box[1] and by["middle"].box[3] > by["lower"].box[1]  # neighbouring bands overlap


def test_two_people_add_left_and_right_halves():
    assert [t.name for t in make_tiles(_png(768, 1344), people=2)] == ["whole", "upper", "middle", "lower", "left", "right"]
    assert "left" not in [t.name for t in make_tiles(_png(768, 1344), people=1)]


def test_every_tile_decodes_is_upscaled_to_the_target_side_and_lies_inside_the_picture():
    for t in make_tiles(_png(768, 1344), people=2, target_side=1280):
        assert isinstance(t, Tile)
        with Image.open(io.BytesIO(t.png)) as im:
            assert max(im.size) == 1280
        x0, y0, x1, y1 = t.box
        assert 0 <= x0 < x1 <= 768 and 0 <= y0 < y1 <= 1344


def test_landscape_picture_splits_along_its_long_side():
    names = [t.name for t in make_tiles(_png(1344, 768))]
    assert names[0] == "whole" and len(names) == 4
    by = {t.name: t for t in make_tiles(_png(1344, 768))}
    assert by[names[1]].box[0] == 0 and by[names[3]].box[2] == 1344


def test_a_tiny_picture_still_gives_non_empty_tiles():
    tiles = make_tiles(_png(16, 16), people=2, target_side=64)
    assert len(tiles) == 6 and all(t.png for t in tiles)
    for t in tiles:
        with Image.open(io.BytesIO(t.png)) as im:
            assert im.width >= 1 and im.height >= 1
