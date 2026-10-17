import pytest
from engine.acquisition.downloader.validation import (
    validate_image_bytes,
    ImageValidationError,
    compute_sha256,
    sanitize_filename,
)
from tests.fixtures.helpers import create_test_image_bytes

def test_valid_image_bytes():
    jpeg_data = create_test_image_bytes(150, 200, color="red", format="JPEG")
    info = validate_image_bytes(jpeg_data, "test.jpg")
    assert info["width"] == 150
    assert info["height"] == 200
    assert info["format"] == "JPEG"
    assert info["mime_type"] == "image/jpeg"
    assert info["byte_size"] == len(jpeg_data)
    assert info["sha256"] == compute_sha256(jpeg_data)

def test_png_validation():
    png_data = create_test_image_bytes(80, 80, color="green", format="PNG")
    info = validate_image_bytes(png_data, "test.png")
    assert info["width"] == 80
    assert info["height"] == 80
    assert info["format"] == "PNG"
    assert info["mime_type"] == "image/png"

def test_reject_html_error_page():
    html_data = b"<!DOCTYPE html><html><head><title>404 Not Found</title></head><body><h1>404 Not Found</h1></body></html>"
    with pytest.raises(ImageValidationError, match="HTML error page"):
        validate_image_bytes(html_data, "page_01.jpg")

def test_reject_corrupt_data():
    corrupt_data = b"\xff\xd8\xff" + b"random invalid garbage content" * 10
    with pytest.raises(ImageValidationError):
        validate_image_bytes(corrupt_data, "corrupt.jpg")

def test_reject_empty_bytes():
    with pytest.raises(ImageValidationError, match="Empty data"):
        validate_image_bytes(b"", "empty.jpg")

def test_sanitize_filename():
    assert sanitize_filename("../../../etc/passwd.jpg", 1) == "passwd.jpg"
    assert sanitize_filename("my page #1?.png", 1) == "my_page__1_.png"
    assert sanitize_filename("", 5) == "page_0005.jpg"
    assert sanitize_filename("...", 7) == "page_0007.jpg"

def test_duplicate_image_detection():
    data_original = create_test_image_bytes(100, 100, color="magenta", format="JPEG")
    data_identical = create_test_image_bytes(100, 100, color="magenta", format="JPEG")
    data_different = create_test_image_bytes(100, 100, color="cyan", format="JPEG")

    info1 = validate_image_bytes(data_original, "original.jpg")
    info2 = validate_image_bytes(data_identical, "copy.jpg")
    info3 = validate_image_bytes(data_different, "different.jpg")

    assert info1["sha256"] == info2["sha256"]
    assert info1["sha256"] != info3["sha256"]
