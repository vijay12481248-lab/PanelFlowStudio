import httpx

from engine.acquisition.adapters.generic_web import GenericAuthorizedWebAdapter


def test_inspection_excludes_site_logo_from_chapter(monkeypatch):
    html = '''<title>Chapter</title><header><img src="/logo-1-1.png"></header>
    <div class="reading-content"><img src="/001.jpg"><img src="/002.jpg"></div>
    <footer><img src="/recommended.jpg"></footer>'''
    monkeypatch.setattr(httpx.Client, "get", lambda self, url: httpx.Response(
        200, text=html, headers={"content-type": "text/html"},
        request=httpx.Request("GET", url),
    ))
    result = GenericAuthorizedWebAdapter().inspect("https://example.com/chapter/1")
    assert result.is_valid
    assert result.chapters[0].extra_metadata["discovered_urls"] == [
        "https://example.com/001.jpg", "https://example.com/002.jpg",
    ]
    assert result.total_pages_detected == 2


def test_lazy_image_uses_content_url_instead_of_placeholder(monkeypatch):
    html = '''<div class="reading-content">
    <img src="/loading.gif" data-src=" /001.jpg "></div>'''
    monkeypatch.setattr(httpx.Client, "get", lambda self, url: httpx.Response(
        200, text=html, headers={"content-type": "text/html"},
        request=httpx.Request("GET", url),
    ))
    result = GenericAuthorizedWebAdapter().inspect("https://example.com/chapter/1")
    assert result.chapters[0].extra_metadata["discovered_urls"] == [
        "https://example.com/001.jpg",
    ]


def test_unfamiliar_reader_preserves_order_and_resolves_srcsets(monkeypatch):
    html = '''<header><img src="/logo.png"></header><main>
    <section class="comic-viewer"><img data-lazy-src="/002.jpg">
    <img srcset="/003-small.jpg 300w, /003-full.jpg 1000w"></section>
    </main><aside><img src="/avatar.png"></aside>'''
    monkeypatch.setattr(httpx.Client, "get", lambda self, url: httpx.Response(
        200, text=html, headers={"content-type": "text/html"}, request=httpx.Request("GET", url)))
    result = GenericAuthorizedWebAdapter().inspect("https://example.com/chapter/1")
    assert result.chapters[0].extra_metadata["discovered_urls"] == [
        "https://example.com/002.jpg", "https://example.com/003-full.jpg"]
