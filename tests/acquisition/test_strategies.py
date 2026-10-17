"""
Unit tests for individual extraction strategies across the strategy ladder.
"""
import pytest
from engine.acquisition.web.strategies.direct_document import DirectDocumentStrategy
from engine.acquisition.web.strategies.static_dom import StaticDomStrategy
from engine.acquisition.web.strategies.reader_container import ReaderContainerStrategy
from engine.acquisition.web.strategies.lazy_images import LazyImagesStrategy
from engine.acquisition.web.strategies.embedded_json import EmbeddedJsonStrategy
from engine.acquisition.web.strategies.rendered_dom import RenderedDomStrategy
from engine.acquisition.web.strategies.browser_network import BrowserNetworkStrategy
from engine.acquisition.web.strategies.resource_timing import ResourceTimingStrategy
from engine.acquisition.web.strategies.rendered_capture import RenderedCaptureStrategy


@pytest.mark.asyncio
async def test_direct_document_strategy():
    strat = DirectDocumentStrategy()
    res = await strat.extract("https://example.com/comics/ch1/page_01.jpg")
    assert res.status == "SUCCESS"
    assert len(res.candidates) == 1
    assert res.candidates[0].resolved_url == "https://example.com/comics/ch1/page_01.jpg"

    # Archive check
    res_arch = await strat.extract("https://example.com/comics/ch1.cbz")
    assert res_arch.status == "NOT_APPLICABLE"


@pytest.mark.asyncio
async def test_static_dom_strategy():
    strat = StaticDomStrategy()
    html = """
    <html><body>
        <div class="header"><img src="/logo.png" width="32" height="32" /></div>
        <div class="reader-area">
            <img src="/p1.jpg" width="800" height="1200" />
            <img src="/p2.jpg" width="800" height="1200" />
            <img src="/p3.jpg" width="800" height="1200" />
        </div>
    </body></html>
    """
    res = await strat.extract("https://example.com/chapter-1", html_text=html)
    assert res.status == "SUCCESS"
    assert len(res.candidates) >= 3


@pytest.mark.asyncio
async def test_reader_container_strategy():
    strat = ReaderContainerStrategy()
    html = """
    <html><body>
        <div class="sidebar"><img src="/thumb1.jpg" /><img src="/thumb2.jpg" /></div>
        <div class="chapter-content">
            <div><img src="/ch1/p01.jpg" width="800" height="1200" /></div>
            <div><img src="/ch1/p02.jpg" width="800" height="1200" /></div>
            <div><img src="/ch1/p03.jpg" width="800" height="1200" /></div>
            <div><img src="/ch1/p04.jpg" width="800" height="1200" /></div>
        </div>
    </body></html>
    """
    res = await strat.extract("https://example.com/chapter-1", html_text=html)
    assert res.status == "SUCCESS"
    assert len(res.candidates) == 4
    assert res.metadata["container_signature"].startswith("div.chapter-content")


@pytest.mark.asyncio
async def test_lazy_images_strategy():
    strat = LazyImagesStrategy()
    html = """
    <html><body>
        <div class="reader">
            <img src="/loading.gif" data-src="/highres/p1.jpg" />
            <img src="/loading.gif" data-src="/highres/p2.jpg" />
            <img src="/loading.gif" data-original="/highres/p3.jpg" />
        </div>
    </body></html>
    """
    res = await strat.extract("https://example.com/chapter-1", html_text=html)
    assert res.status == "SUCCESS"
    assert len(res.candidates) == 3
    assert all("highres" in c.resolved_url for c in res.candidates)


@pytest.mark.asyncio
async def test_embedded_json_strategy():
    strat = EmbeddedJsonStrategy()
    html = """
    <html><body>
        <script id="__NEXT_DATA__" type="application/json">
        {
            "props": {
                "pageProps": {
                    "chapter": {
                        "pages": [
                            "https://cdn.example.com/ch1/01.jpg",
                            "https://cdn.example.com/ch1/02.jpg",
                            "https://cdn.example.com/ch1/03.jpg",
                            "https://cdn.example.com/ch1/04.jpg"
                        ]
                    }
                }
            }
        }
        </script>
    </body></html>
    """
    res = await strat.extract("https://example.com/chapter-1", html_text=html)
    assert res.status == "SUCCESS"
    assert len(res.candidates) == 4
    assert res.metadata["manifest_format"] == "EMBEDDED_JSON"


@pytest.mark.asyncio
async def test_rendered_dom_strategy():
    strat = RenderedDomStrategy()
    mock_items = [
        {"url": "https://cdn.example.com/p1.jpg", "natural_width": 800, "natural_height": 1200, "dom_order": 1},
        {"url": "https://cdn.example.com/p2.jpg", "natural_width": 800, "natural_height": 1200, "dom_order": 2},
    ]
    res = await strat.extract("https://example.com/chapter-1", context={"mock_rendered_items": mock_items})
    assert res.status == "SUCCESS"
    assert len(res.candidates) == 2


@pytest.mark.asyncio
async def test_browser_network_strategy():
    strat = BrowserNetworkStrategy()
    mock_events = [
        {"url": "https://cdn.example.com/stream/01.webp", "mime_type": "image/webp", "status": 200},
        {"url": "https://cdn.example.com/stream/02.webp", "mime_type": "image/webp", "status": 200},
    ]
    res = await strat.extract("https://example.com/chapter-1", context={"mock_network_events": mock_events})
    assert res.status == "SUCCESS"
    assert len(res.candidates) == 2


@pytest.mark.asyncio
async def test_rendered_capture_strategy():
    strat = RenderedCaptureStrategy()
    mock_captures = [
        {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "width": 800, "height": 1200, "sequence": 1}
    ]
    res = await strat.extract("https://example.com/chapter-1", context={"mock_canvas_captures": mock_captures})
    assert res.status == "SUCCESS"
    assert len(res.candidates) == 1
    assert "RENDERED_CAPTURE" in res.metadata["capture_type"]
