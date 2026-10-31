from engine.ocr.providers.windows_media_provider import deskewed_bbox


def test_zero_angle_keeps_box():
    assert deskewed_bbox([(10, 20, 30, 40)], 0.0, 200, 200) == [10, 20, 30, 40]


def test_angle_maps_box_back_to_page_pixels():
    # Magic Emperor 928 panel #40 (1863x3757): Windows reported TextAngle -6.2 and put "MANHUA" at
    # (1139, 3410); the logo glyphs actually start near (1305, 3380).
    x, y, w, h = deskewed_bbox([(1139, 3410, 248, 72)], -6.2, 1863, 3757)
    assert abs(x - 1303) < 15 and abs(y - 3352) < 30 and w > 248
