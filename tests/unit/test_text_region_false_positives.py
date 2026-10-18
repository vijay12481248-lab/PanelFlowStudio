import cv2
import numpy as np

from engine.imaging.text_regions import ClassicalTextRegionDetector


def test_empty_bordered_artwork_is_not_text():
    roi = np.full((140, 400), 240, dtype=np.uint8)
    cv2.rectangle(roi, (0, 0), (399, 139), 0, 4)
    assert not ClassicalTextRegionDetector()._has_text_content(roi)


def test_interior_letter_strokes_remain_text():
    roi = np.full((140, 400), 255, dtype=np.uint8)
    cv2.rectangle(roi, (0, 0), (399, 139), 0, 3)
    cv2.putText(roi, "HELLO WORLD", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.1, 0, 3)
    assert ClassicalTextRegionDetector()._has_text_content(roi)
