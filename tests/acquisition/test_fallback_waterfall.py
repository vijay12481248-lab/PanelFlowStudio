"""
Integration tests for the complete multi-strategy fallback waterfall,
including the 3 required fallback and failure tests specified in the prompt.
"""
import pytest
from pathlib import Path
from engine.acquisition.web.chapter_extractor import AdaptiveChapterExtractor
from engine.acquisition.web.models.extraction_result import ExtractionState
from engine.acquisition.web.recipes.recipe import ReaderRecipe


@pytest.mark.asyncio
async def test_required_fallback_1_static_fails_network_fuses_success(tmp_path: Path):
    """
    REQUIRED FALLBACK TEST 1:
    Static DOM FAILS (0 images)
    Embedded JSON FAILS (0 manifests)
    Rendered DOM discovers partial content (2 images)
    Network observation discovers all content (5 images)
    Evidence fusion succeeds -> Expected: EXTRACTED / SUCCESS
    """
    extractor = AdaptiveChapterExtractor(recipe_dir=tmp_path / "recipes")

    # Static HTML is completely blank shell (SPA / dynamic client loader)
    blank_shell_html = """
    <html><head><title>Chapter 10: The Awakening</title></head>
    <body>
        <div id="app">Loading reader...</div>
        <!-- Zero static images or embedded JSON -->
    </body></html>
    """

    # Rendered DOM only caught 2 lazy images before full scroll
    mock_rendered = [
        {"url": "https://cdn.example.com/ch10/p01.jpg", "natural_width": 800, "natural_height": 1200, "dom_order": 1},
        {"url": "https://cdn.example.com/ch10/p02.jpg", "natural_width": 800, "natural_height": 1200, "dom_order": 2},
    ]

    # Network observation caught all 5 images requested as the reader scrolled
    mock_network = [
        {"url": f"https://cdn.example.com/ch10/p{i:02d}.jpg", "mime_type": "image/jpeg", "status": 200}
        for i in range(1, 6)
    ]

    context = {
        "mock_html": blank_shell_html,
        "mock_rendered_items": mock_rendered,
        "mock_network_events": mock_network,
    }

    result = await extractor.extract("https://example.com/manga/series-x/chapter-10", context=context)

    assert result.state == ExtractionState.EXTRACTED
    assert result.manifest is not None
    assert len(result.manifest.pages) == 5
    assert result.manifest.extraction_strategy in ("RENDERED_NETWORK_FUSION", "RENDERED_DOM", "BROWSER_NETWORK")
    assert result.overall_confidence >= 0.85
    assert result.completeness_score >= 0.90


@pytest.mark.asyncio
async def test_required_fallback_2_stale_recipe_heals_via_browser(tmp_path: Path):
    """
    SECOND REQUIRED FALLBACK TEST:
    Saved recipe FAILS because site structure changed (CDN changed / container selector broken)
    Generic static discovery gives low confidence (1 thumbnail)
    Browser-rendered discovery succeeds (6 images)
    A new recipe candidate is generated -> Expected: SUCCESS / EXTRACTED with self-healing recipe.
    """
    recipe_dir = tmp_path / "recipes"
    extractor = AdaptiveChapterExtractor(recipe_dir=recipe_dir)

    # 1. Pre-seed a stale recipe with old CDN pattern that no longer matches
    stale_recipe = ReaderRecipe(
        domain="dynamic-manga.org",
        chapter_path_pattern="/series/*/chapter-*",
        preferred_strategy="STATIC_DOM",
        container_signatures=["div.legacy-reader"],
        known_cdn_patterns=["legacy-cdn.dynamic-manga.org"],  # Old CDN
        expected_cluster_minimum=5,
    )
    extractor.recipe_store.save_recipe(stale_recipe, persist=True)

    # Static HTML has modern container and new CDN (only 1 image loaded statically)
    new_html = """
    <html><head><title>Dynamic Chapter 4</title></head>
    <body>
        <div class="new-v2-reader">
            <img src="https://new-cdn.dynamic-manga.org/ch4/preview.jpg" width="100" height="100" />
        </div>
    </body></html>
    """

    # Browser render discovers the full 6 pages on the new CDN
    mock_rendered = [
        {
            "url": f"https://new-cdn.dynamic-manga.org/ch4/page_{i:02d}.jpg",
            "natural_width": 800,
            "natural_height": 1200,
            "dom_order": i,
            "parent_tag": "div.new-v2-reader",
        }
        for i in range(1, 7)
    ]

    context = {
        "mock_html": new_html,
        "mock_rendered_items": mock_rendered,
    }

    result = await extractor.extract("https://dynamic-manga.org/series/my-title/chapter-4", context=context)

    assert result.state == ExtractionState.EXTRACTED
    assert result.manifest is not None
    assert len(result.manifest.pages) == 6

    # Verify self-healing: a new recipe candidate was generated and saved
    updated_recipe = extractor.recipe_store.find_recipe("https://dynamic-manga.org/series/my-title/chapter-4")
    assert updated_recipe is not None
    assert "new-cdn.dynamic-manga.org" in updated_recipe.known_cdn_patterns


@pytest.mark.asyncio
async def test_required_failure_3_login_access_restriction_safely_rejected(tmp_path: Path):
    """
    THIRD REQUIRED FAILURE TEST:
    A page looks like a chapter URL but contains login / paywall / access restriction.
    Expected: AUTHENTICATION_REQUIRED or ACCESS_RESTRICTED.
    The extractor MUST NOT attempt security bypass strategies.
    """
    extractor = AdaptiveChapterExtractor(recipe_dir=tmp_path / "recipes")

    login_wall_html = """
    <html><head><title>Sign In - Chapter Viewer</title></head>
    <body>
        <div class="auth-box">
            <h2>Subscriber Authentication Required</h2>
            <p>Please enter your credentials to read this chapter.</p>
            <form action="/login" method="POST">
                <input type="text" name="username" placeholder="Username" />
                <input type="password" name="password" placeholder="Password" />
                <button type="submit">Sign In</button>
            </form>
        </div>
    </body></html>
    """

    context = {
        "mock_html": login_wall_html,
    }

    result = await extractor.extract("https://paywall-manga.com/series/hero/chapter-99", context=context)

    # Must refuse to scrape and return structured status without bypass attempts
    assert result.state in (ExtractionState.AUTHENTICATION_REQUIRED, ExtractionState.ACCESS_RESTRICTED)
    assert result.manifest is None
    assert "Authentication" in result.error or "Login" in result.error or "restricted" in result.error.lower()


@pytest.mark.asyncio
async def test_http_403_forbidden_classified_as_access_restricted():
    extractor = AdaptiveChapterExtractor()

    context = {
        "mock_html": "<html><body>403 Forbidden - Access Denied</body></html>",
    }

    # Simulate HTTP 403 response
    from unittest.mock import patch, MagicMock
    with patch("httpx.AsyncClient.get") as mock_get:
        resp = MagicMock()
        resp.status_code = 403
        resp.text = "<html><body>403 Forbidden</body></html>"
        mock_get.return_value = resp

        result = await extractor.extract("https://restricted-host.org/chapter-1")
        assert result.state == ExtractionState.ACCESS_RESTRICTED


@pytest.mark.asyncio
async def test_http_429_rate_limited():
    extractor = AdaptiveChapterExtractor()

    from unittest.mock import patch, MagicMock
    with patch("httpx.AsyncClient.get") as mock_get:
        resp = MagicMock()
        resp.status_code = 429
        resp.text = "Too Many Requests"
        mock_get.return_value = resp

        result = await extractor.extract("https://rate-limited-host.com/chapter-1")
        assert result.state == ExtractionState.RATE_LIMITED


@pytest.mark.asyncio
async def test_wrong_non_chapter_site():
    extractor = AdaptiveChapterExtractor()

    # Series table of contents with 10 chapter links and 0 reader images
    series_html = """
    <html><head><title>My Comic Series Index</title></head>
    <body>
        <h1>Chapters</h1>
        <ul>
            <li><a href="/chapter-1">Chapter 1</a></li>
            <li><a href="/chapter-2">Chapter 2</a></li>
            <li><a href="/chapter-3">Chapter 3</a></li>
            <li><a href="/chapter-4">Chapter 4</a></li>
            <li><a href="/chapter-5">Chapter 5</a></li>
            <li><a href="/chapter-6">Chapter 6</a></li>
        </ul>
    </body></html>
    """

    context = {"mock_html": series_html}
    result = await extractor.extract("https://example.com/series/my-comic", context=context)
    assert result.state == ExtractionState.NOT_A_CHAPTER
