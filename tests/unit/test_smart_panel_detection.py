import cv2
import numpy as np

from engine.imaging.panels.detector import ContourPanelDetector
from engine.imaging.panels.classification import PanelClassifier


def classify(text="", bbox=None):
    return PanelClassifier.classify_panel("p", 1, "panel.jpg", bbox or [0, 0, 300, 100], ocr_text=text)


def test_small_geometry_alone_does_not_exclude_story():
    assert classify().classification == "UNCERTAIN"
    assert classify("Run! Get out of here!").classification == "STORY_PANEL"


def test_website_call_to_action_is_recognized():
    for text in ["Visit our website for releases", "Read at www.example.com", "Join us on discord.gg/example"]:
        assert classify(text).classification == "NON_STORY_CONTENT"


def test_wide_dialogue_panel_is_not_a_banner():
    assert classify("We have finally arrived.", [0, 0, 900, 150]).classification == "STORY_PANEL"


def test_slanted_quadrilateral_frame_is_detected():
    image = np.full((800, 800, 3), 255, dtype=np.uint8)
    points = np.array([[80, 80], [650, 180], [600, 500], [30, 400]], dtype=np.int32)
    cv2.polylines(image, [points], True, (0, 0, 0), 5)
    boxes = ContourPanelDetector()._detect_page_contours(image, 800, 800, "MANGA_PAGE")
    assert any(w > 500 and h > 350 for x, y, w, h, confidence, kind in boxes)


def test_artwork_contour_does_not_mask_away_panel():
    image = np.full((600, 600, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (200, 200), (350, 350), (0, 0, 0), 5)
    assert ContourPanelDetector()._extract_polygon_from_box(image, 0, 0, 600, 600) is None
