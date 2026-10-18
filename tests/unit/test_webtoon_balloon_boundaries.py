import cv2
import numpy as np

from engine.imaging.panels.detector import ContourPanelDetector


def test_webtoon_gutter_does_not_cut_through_thin_balloon_outline():
    image = np.full((5000, 800, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (30, 100), (770, 1000), (90, 90, 90), -1)
    cv2.rectangle(image, (200, 700), (600, 1400), (255, 255, 255), -1)
    cv2.rectangle(image, (200, 700), (600, 1400), (0, 0, 0), 2)
    cv2.rectangle(image, (30, 1700), (770, 2400), (90, 90, 90), -1)
    panels = ContourPanelDetector()._detect_webtoon_tiled(image, 800, 5000)
    assert len(panels) == 2
    assert panels[0][1] <= 100
    assert panels[0][1] + panels[0][3] >= 1401


def test_colored_gutters_separate_panels_when_page_edges_are_white():
    image = np.full((5000, 800, 3), 255, dtype=np.uint8)
    image[100:4800] = (240, 220, 200)
    cv2.rectangle(image, (30, 300), (770, 1500), (80, 80, 80), -1)
    cv2.rectangle(image, (30, 1900), (770, 3000), (80, 80, 80), -1)
    panels = ContourPanelDetector()._detect_webtoon_tiled(image, 800, 5000)
    assert len(panels) == 2
