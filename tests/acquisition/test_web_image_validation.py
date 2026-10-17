"""
Tests for image byte probing, magic bytes verification, HTML error detection,
placeholder detection, and deduplication.
"""
import io
import pytest
from PIL import Image
from engine.acquisition.web.validation.image_probe import probe_image_bytes, detect_magic_bytes
from engine.acquisition.web.validation.placeholder_detector import is_placeholder_candidate
from engine.acquisition.web.validation.duplicate_detector import DuplicateDetector
from tests.fixtures.helpers import create_test_image_bytes


def test_magic_bytes_detection():
    jpeg_data = create_test_image_bytes(50, 50, "red", format="JPEG")
    assert detect_magic_bytes(jpeg_data) == "image/jpeg"

    png_data = create_test_image_bytes(50, 50, "green", format="PNG")
    assert detect_magic_bytes(png_data) == "image/png"


def test_probe_valid_image():
    data = create_test_image_bytes(800, 1200, "blue", format="JPEG")
    res = probe_image_bytes(data)
    assert res.is_valid is True
    assert res.width == 800
    assert res.height == 1200
    assert res.mime_type == "image/jpeg"
    assert res.sha256 is not None
    assert res.byte_size == len(data)


def test_probe_rejects_html_as_jpg():
    fake_jpg = b"<html><head><title>403 Forbidden</title></head><body>Cloudflare access denied</body></html>"
    res = probe_image_bytes(fake_jpg)
    assert res.is_valid is False
    assert "HTML error or challenge page" in res.error


def test_probe_rejects_corrupt_data():
    garbage = b"\xff\xd8\xff\xe0" + b"\x00" * 200
    res = probe_image_bytes(garbage)
    assert res.is_valid is False
    assert "Corrupt image" in res.error or "Invalid image" in res.error


def test_placeholder_detector():
    # 1. URL pattern
    is_p, _ = is_placeholder_candidate("https://example.com/assets/loading.gif")
    assert is_p is True

    is_p, _ = is_placeholder_candidate("https://example.com/images/spacer_1x1.png")
    assert is_p is True

    # 2. Dimensions
    is_p, _ = is_placeholder_candidate("https://example.com/img.jpg", width=1, height=1)
    assert is_p is True

    # 3. Legitimate content
    is_p, _ = is_placeholder_candidate("https://example.com/ch01/page_01.jpg", width=800, height=1200)
    assert is_p is False


def test_duplicate_detector():
    detector = DuplicateDetector()

    assert not detector.is_duplicate_url("https://example.com/page1.jpg")
    assert detector.is_duplicate_url("https://example.com/page1.jpg")

    hash1 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert not detector.is_duplicate_content(hash1)
    assert detector.is_duplicate_content(hash1)
