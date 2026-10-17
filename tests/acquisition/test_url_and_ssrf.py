"""
Tests for URL normalization, scheme validation, and SSRF security guards.
"""
import pytest
from engine.acquisition.web.validation.ssrf_guard import is_safe_url
from engine.acquisition.web.discovery.candidate_collector import normalize_image_url, parse_srcset_best_url


def test_ssrf_rejects_unsafe_schemes():
    assert not is_safe_url("file:///etc/passwd")[0]
    assert not is_safe_url("javascript:alert(1)")[0]
    assert not is_safe_url("data:image/png;base64,123")[0]
    assert not is_safe_url("ftp://example.com/image.jpg")[0]
    assert not is_safe_url("gopher://example.com/")[0]


def test_ssrf_rejects_loopback_and_metadata():
    assert not is_safe_url("http://127.0.0.1:8080/image.jpg")[0]
    assert not is_safe_url("http://localhost:3000/image.jpg")[0]
    assert not is_safe_url("http://169.254.169.254/latest/meta-data/")[0]
    assert not is_safe_url("http://instance-data/")[0]
    assert not is_safe_url("http://metadata.google.internal/")[0]


def test_ssrf_permits_safe_public_urls():
    # Public domain names
    safe, _ = is_safe_url("https://example.com/chapter1/page01.jpg")
    assert safe is True

    safe, _ = is_safe_url("http://example.org/comics/01.png")
    assert safe is True


def test_ssrf_loopback_override_for_testing():
    # In test suites, allow_loopback_for_testing can be toggled on
    safe, _ = is_safe_url("http://127.0.0.1:8000/test.jpg", allow_loopback_for_testing=True)
    assert safe is True


def test_url_normalization():
    base = "https://example.com/manga/ch-01/"
    assert normalize_image_url("page1.jpg", base) == "https://example.com/manga/ch-01/page1.jpg"
    assert normalize_image_url("/images/p1.jpg", base) == "https://example.com/images/p1.jpg"
    assert normalize_image_url("//cdn.example.org/p1.webp", base) == "https://cdn.example.org/p1.webp"


def test_srcset_parsing():
    srcset = "thumb.jpg 300w, medium.jpg 600w, highres.jpg 1200w"
    base = "https://example.com/"
    assert parse_srcset_best_url(srcset, base) == "https://example.com/highres.jpg"
