"""
Production acceptance tests for the Adaptive Resilient Chapter Extraction Engine.
Validates secret-safe recipe policies, API manifest bounds, SSRF redirect defense,
and evidence fusion.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import httpx

from engine.acquisition.web.chapter_extractor import AdaptiveChapterExtractor
from engine.acquisition.web.models.extraction_result import ExtractionState
from engine.acquisition.web.models.image_candidate import ImageCandidate, GlobalCandidatePool
from engine.acquisition.web.models.chapter_manifest import SourceQuality
from engine.acquisition.web.recipes.recipe import ReaderRecipe, sanitize_recipe_headers
from engine.acquisition.web.strategies.api_manifest import ApiManifestStrategy
from engine.acquisition.web.discovery.sequence_resolver import natural_sort_key


def test_secret_safe_recipe_header_sanitization():
    """
    Requirement 17: Audit ReaderRecipe storage.
    ReaderRecipe MUST NEVER persist Cookie, Authorization, Bearer tokens, or session secrets.
    Only harmless headers (User-Agent, Accept, Accept-Language, Referer) may be retained.
    """
    sensitive_headers = {
        "Cookie": "session_id=abcdef123456; auth_token=secret_xyz",
        "Set-Cookie": "track_id=98765",
        "Authorization": "Bearer super-secret-jwt-token-here",
        "Proxy-Authorization": "Basic dXNlcjpwYXNz",
        "X-CSRF-Token": "csrf-secret-999",
        "X-API-Key": "my-secret-key",
        "User-Agent": "PanelFlowStudio/0.1.0",
        "Referer": "https://reader.example.com/",
        "Accept": "text/html,application/xhtml+xml,image/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    sanitized = sanitize_recipe_headers(sensitive_headers)

    # Harmful headers must be completely stripped
    assert "Cookie" not in sanitized
    assert "cookie" not in sanitized
    assert "Authorization" not in sanitized
    assert "Set-Cookie" not in sanitized
    assert "X-CSRF-Token" not in sanitized
    assert "X-API-Key" not in sanitized
    assert "Proxy-Authorization" not in sanitized

    # Allowed headers must be preserved
    assert sanitized.get("User-Agent") == "PanelFlowStudio/0.1.0"
    assert sanitized.get("Referer") == "https://reader.example.com/"
    assert "Accept" in sanitized
    assert "Accept-Language" in sanitized

    # Validation in ReaderRecipe pydantic model directly
    recipe = ReaderRecipe(
        domain="reader.example.com",
        preferred_strategy="STATIC_DOM",
        headers=sensitive_headers,
        requires_authenticated_session=True,
    )

    assert "Authorization" not in recipe.headers
    assert "Cookie" not in recipe.headers
    assert recipe.headers.get("User-Agent") == "PanelFlowStudio/0.1.0"
    assert recipe.requires_authenticated_session is True


@pytest.mark.asyncio
async def test_api_manifest_safety_no_brute_forcing():
    """
    Requirement 19: API Manifest safety audit.
    The strategy must ONLY inspect documented or explicitly referenced endpoints.
    It must NEVER brute force endpoint dictionaries or probe arbitrary /api/* paths.
    """
    strategy = ApiManifestStrategy()

    # Document with no API references
    html_without_api = """
    <html><body>
        <h1>Normal Comic</h1>
        <div id="content"><p>Some story prose without manifests.</p></div>
    </body></html>
    """

    # We track how many requests httpx makes
    called_urls = []

    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def get(self, url, **kwargs):
            called_urls.append(url)
            return MagicMock(status_code=404)

    with patch("httpx.AsyncClient", return_value=MockClient()):
        result = await strategy.extract("https://example.com/chapter-1", html_text=html_without_api)

    # Strategy must gracefully report LOW_CONFIDENCE and make ZERO brute-force requests
    assert result.status == "LOW_CONFIDENCE"
    assert len(called_urls) == 0, f"ApiManifestStrategy unexpectedly probed endpoints: {called_urls}"


@pytest.mark.asyncio
async def test_ssrf_redirect_to_private_ip_blocked(tmp_path: Path):
    """
    Requirement 23: Verify SSRF validation occurs on redirects as well as initial URL.
    Public URL -> 302 redirect -> Private/Loopback IP -> FAILED_SSRF_BLOCKED.
    """
    extractor = AdaptiveChapterExtractor(recipe_dir=tmp_path / "recipes")

    class MockRedirectTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if str(request.url) == "https://legit-reader.org/chapter-1":
                # Redirect to private AWS metadata / loopback address
                return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
            return httpx.Response(200, text="Should never reach here")

    # Patch httpx.AsyncClient to use MockRedirectTransport while keeping event hooks active
    original_async_client = httpx.AsyncClient

    def create_intercepted_client(*args, **kwargs):
        kwargs["transport"] = MockRedirectTransport()
        return original_async_client(*args, **kwargs)

    with patch("httpx.AsyncClient", side_effect=create_intercepted_client):
        result = await extractor.extract("https://legit-reader.org/chapter-1")

    assert result.state == ExtractionState.FAILED_SSRF_BLOCKED
    assert "SSRF blocked" in result.error or "metadata" in result.error.lower()


@pytest.mark.asyncio
async def test_wrong_site_ordinary_non_reader_classified():
    """
    Requirement 22: Ordinary non-reader URL (blog or news article without reader layout)
    returns NOT_A_CHAPTER without running expensive browser strategies indefinitely.
    """
    extractor = AdaptiveChapterExtractor()

    ordinary_blog_html = """
    <html><head><title>Cooking Recipes Blog - Chocolate Chip Cookies</title></head>
    <body>
        <header><nav><a href="/">Home</a><a href="/about">About</a></nav></header>
        <main>
            <h1>Best Chocolate Chip Cookies</h1>
            <p>Here is my favorite recipe for soft and chewy cookies...</p>
            <p>Mix flour, sugar, and chocolate chips...</p>
        </main>
        <footer><p>&copy; 2026 Cooking Blog</p></footer>
    </body></html>
    """

    context = {"mock_html": ordinary_blog_html}
    result = await extractor.extract("https://cookingblog.com/recipes/chocolate-chip-cookies", context=context)

    assert result.state == ExtractionState.NOT_A_CHAPTER
    assert result.manifest is None


def test_natural_order_sorting():
    """
    Requirement 13: Order validation.
    Must sort naturally: 1, 2, ..., 9, 10, 11 (never 1, 10, 11, 2).
    """
    filenames = [
        "https://cdn.example.com/p10.jpg",
        "https://cdn.example.com/p1.jpg",
        "https://cdn.example.com/p2.jpg",
        "https://cdn.example.com/p11.jpg",
        "https://cdn.example.com/p9.jpg",
    ]

    sorted_files = sorted(filenames, key=natural_sort_key)
    expected = [
        "https://cdn.example.com/p1.jpg",
        "https://cdn.example.com/p2.jpg",
        "https://cdn.example.com/p9.jpg",
        "https://cdn.example.com/p10.jpg",
        "https://cdn.example.com/p11.jpg",
    ]
    assert sorted_files == expected


def test_global_candidate_pool_merges_without_duplicate_inflation():
    """
    Requirement 10: Resource Timing & multi-strategy evidence merging.
    GlobalCandidatePool must merge multiple sightings of the exact same canonical URL
    rather than treating them as separate images.
    """
    pool = GlobalCandidatePool()

    # Observed first by RENDERED_DOM
    c1 = ImageCandidate(
        url="https://cdn.example.com/page01.jpg",
        resolved_url="https://cdn.example.com/page01.jpg",
        dom_order=1,
        content_score=0.85,
        source_strategies={"RENDERED_DOM"},
    )
    pool.add_candidates([c1])
    assert len(pool.get_candidates()) == 1

    # Observed again by RESOURCE_TIMING with performance duration metadata
    c2 = ImageCandidate(
        url="https://cdn.example.com/page01.jpg",
        resolved_url="https://cdn.example.com/page01.jpg",
        dom_order=1,
        content_score=0.90,
        source_strategies={"RESOURCE_TIMING"},
        attributes={"duration_ms": "120"},
    )
    pool.add_candidates([c2])

    # Total unique candidates must remain exactly 1, but with fused strategy evidence
    candidates = pool.get_candidates()
    assert len(candidates) == 1
    assert "RENDERED_DOM" in candidates[0].source_strategies
    assert "RESOURCE_TIMING" in candidates[0].source_strategies
