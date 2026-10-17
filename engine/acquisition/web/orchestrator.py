"""
Adaptive Chapter Extraction Orchestrator.
Coordinates the multi-strategy discovery waterfall, candidate clustering, evidence fusion,
recipe fast-path and self-healing, early-exit pruning, and failure classification.
"""
import time
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup

from engine.acquisition.web.models.chapter_manifest import (
    ChapterManifest,
    PageType,
    ContentLayout,
    ExtractionStrategyId,
    SourceQuality,
)
from engine.acquisition.web.models.image_candidate import (
    ImageCandidate,
    CandidateCluster,
    GlobalCandidatePool,
)
from engine.acquisition.web.models.extraction_result import (
    ExtractionState,
    ExtractionAttempt,
    ChapterExtractionResult,
)
from engine.acquisition.web.models.site_fingerprint import SiteFingerprint

from engine.acquisition.web.discovery.page_classifier import PageClassifier
from engine.acquisition.web.discovery.reader_classifier import ReaderClassifier
from engine.acquisition.web.discovery.container_detector import ContainerDetector
from engine.acquisition.web.discovery.candidate_clusterer import CandidateClusterer
from engine.acquisition.web.discovery.candidate_scorer import CandidateScorer
from engine.acquisition.web.discovery.sequence_resolver import SequenceResolver

from engine.acquisition.web.validation.ssrf_guard import is_safe_url
from engine.acquisition.web.validation.chapter_validator import ChapterValidator

from engine.acquisition.web.diagnostics.extraction_trace import ExtractionTrace, sanitize_url
from engine.acquisition.web.diagnostics.failure_classifier import FailureClassifier

from engine.acquisition.web.recipes.recipe import ReaderRecipe
from engine.acquisition.web.recipes.recipe_store import RecipeStore
from engine.acquisition.web.recipes.recipe_builder import RecipeBuilder
from engine.acquisition.web.recipes.recipe_validator import RecipeValidator

from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.strategies.direct_document import DirectDocumentStrategy
from engine.acquisition.web.strategies.static_dom import StaticDomStrategy
from engine.acquisition.web.strategies.reader_container import ReaderContainerStrategy
from engine.acquisition.web.strategies.lazy_images import LazyImagesStrategy
from engine.acquisition.web.strategies.embedded_json import EmbeddedJsonStrategy
from engine.acquisition.web.strategies.api_manifest import ApiManifestStrategy
from engine.acquisition.web.strategies.rendered_dom import RenderedDomStrategy
from engine.acquisition.web.strategies.browser_network import BrowserNetworkStrategy
from engine.acquisition.web.strategies.resource_timing import ResourceTimingStrategy
from engine.acquisition.web.strategies.rendered_capture import RenderedCaptureStrategy


class AdaptiveChapterOrchestrator:
    """
    Central engine orchestrating the extraction ladder and evidence fusion.
    """

    def __init__(self, recipe_store: Optional[RecipeStore] = None):
        self.recipe_store = recipe_store or RecipeStore()
        self.recipe_builder = RecipeBuilder()
        self.recipe_validator = RecipeValidator()

        self.page_classifier = PageClassifier()
        self.reader_classifier = ReaderClassifier()
        self.container_detector = ContainerDetector()
        self.clusterer = CandidateClusterer()
        self.scorer = CandidateScorer()
        self.sequence_resolver = SequenceResolver()
        self.chapter_validator = ChapterValidator()
        self.failure_classifier = FailureClassifier()

        # Strategy Registry in Cost Order (Cheap -> Expensive)
        self.strat_direct = DirectDocumentStrategy()
        self.strat_static = StaticDomStrategy()
        self.strat_container = ReaderContainerStrategy()
        self.strat_lazy = LazyImagesStrategy()
        self.strat_json = EmbeddedJsonStrategy()
        self.strat_api = ApiManifestStrategy()
        self.strat_rendered = RenderedDomStrategy()
        self.strat_network = BrowserNetworkStrategy()
        self.strat_timing = ResourceTimingStrategy()
        self.strat_capture = RenderedCaptureStrategy()

    async def extract(
        self,
        url: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ChapterExtractionResult:
        context = context or {}
        trace = ExtractionTrace(url)
        pool = GlobalCandidatePool()
        attempts: List[ExtractionAttempt] = []

        allow_loopback = context.get("allow_loopback_for_testing", False)

        # -------------------------------------------------------------------
        # STAGE 0: URL Validation & SSRF Check
        # -------------------------------------------------------------------
        safe, reason = is_safe_url(url, allow_loopback_for_testing=allow_loopback)
        if not safe:
            is_ssrf = any(keyword in reason.lower() for keyword in ["ssrf blocked", "loopback", "private network", "cloud metadata", "forbidden cloud"])
            state = ExtractionState.FAILED_SSRF_BLOCKED if is_ssrf else ExtractionState.INVALID_URL
            trace.record_step("STAGE_0", state.value, message=f"URL validation failed: {reason}")
            trace.final_status = state.value
            return ChapterExtractionResult(
                state=state,
                overall_confidence=0.0,
                error=reason,
                diagnostics=trace.to_dict(),
            )

        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

        # -------------------------------------------------------------------
        # STAGE 1: Direct Resource Detection
        # -------------------------------------------------------------------
        direct_res = await self.strat_direct.extract(url, context=context)
        attempts.append(self._attempt_from_result(direct_res))
        trace.record_step(
            direct_res.strategy_id,
            direct_res.status,
            len(direct_res.candidates),
            direct_res.confidence,
            direct_res.elapsed_ms,
            message="Direct document check",
        )

        if direct_res.status == "SUCCESS" and direct_res.candidates:
            manifest = self._build_manifest_from_candidates(
                url, direct_res.candidates, direct_res.strategy_id, direct_res.confidence, 1.0
            )
            trace.final_status = "EXTRACTED"
            return ChapterExtractionResult(
                state=ExtractionState.EXTRACTED,
                manifest=manifest,
                attempts=attempts,
                final_strategy=direct_res.strategy_id,
                overall_confidence=1.0,
                completeness_score=1.0,
                diagnostics=trace.to_dict(),
            )

        # -------------------------------------------------------------------
        # Fetch Initial Document Content (with safety and redirect SSRF policies)
        # -------------------------------------------------------------------
        html_text = context.get("mock_html")
        content_type = context.get("mock_content_type", "text/html")

        if html_text is None:
            try:
                headers = {"User-Agent": "PanelFlowStudio/0.1.0"}

                async def check_redirect(response: httpx.Response):
                    if response.is_redirect:
                        loc = response.headers.get("Location")
                        if loc:
                            target = urljoin(str(response.url), loc)
                            s, r = is_safe_url(target, allow_loopback_for_testing=allow_loopback)
                            if not s:
                                raise ValueError(f"SSRF_REDIRECT_BLOCKED: {r}")

                async with httpx.AsyncClient(
                    timeout=15.0,
                    follow_redirects=True,
                    event_hooks={"response": [check_redirect]},
                ) as client:
                    resp = await client.get(url, headers=headers)

                    # Check for access restrictions or security challenges
                    if resp.status_code in (401, 403, 429):
                        fail_state, fail_msg = self.failure_classifier.classify_http_error(resp.status_code, resp.text)
                        trace.record_step("HTTP_FETCH", fail_state.value, message=fail_msg)
                        trace.final_status = fail_state.value
                        return ChapterExtractionResult(
                            state=fail_state,
                            overall_confidence=0.0,
                            error=fail_msg,
                            attempts=attempts,
                            diagnostics=trace.to_dict(),
                        )

                    content_type = resp.headers.get("content-type", "").lower()
                    html_text = resp.text

            except ValueError as ve:
                if "SSRF_REDIRECT_BLOCKED" in str(ve):
                    err_msg = str(ve).replace("SSRF_REDIRECT_BLOCKED: ", "")
                    trace.record_step("HTTP_FETCH", "FAILED_SSRF_BLOCKED", message=err_msg)
                    trace.final_status = "FAILED_SSRF_BLOCKED"
                    return ChapterExtractionResult(
                        state=ExtractionState.FAILED_SSRF_BLOCKED,
                        overall_confidence=0.0,
                        error=err_msg,
                        attempts=attempts,
                        diagnostics=trace.to_dict(),
                    )
                raise ve

            except (httpx.TimeoutException, httpx.NetworkError) as ne:
                trace.record_step("HTTP_FETCH", "FAILED_NETWORK", message=str(ne))
                trace.final_status = "FAILED_NETWORK"
                return ChapterExtractionResult(
                    state=ExtractionState.FAILED_NETWORK,
                    overall_confidence=0.0,
                    error=f"Network error: {ne}",
                    attempts=attempts,
                    diagnostics=trace.to_dict(),
                )

        # Classify document
        page_type, page_conf, page_reason = self.page_classifier.classify_document(
            url, html_text=html_text, content_type=content_type
        )
        trace.record_step("PAGE_CLASSIFICATION", page_type.value, confidence=page_conf, message=page_reason)

        if page_type == PageType.NOT_CONTENT:
            if any(term in page_reason.lower() for term in ("login", "auth", "sign in", "subscription")):
                trace.final_status = "AUTHENTICATION_REQUIRED"
                return ChapterExtractionResult(
                    state=ExtractionState.AUTHENTICATION_REQUIRED,
                    overall_confidence=page_conf,
                    error=page_reason,
                    attempts=attempts,
                    diagnostics=trace.to_dict(),
                )
            else:
                trace.final_status = "NOT_A_CHAPTER"
                return ChapterExtractionResult(
                    state=ExtractionState.NOT_A_CHAPTER,
                    overall_confidence=page_conf,
                    error=page_reason or "Page is not an illustrated chapter or reader document",
                    attempts=attempts,
                    diagnostics=trace.to_dict(),
                )

        if page_type == PageType.SERIES_PAGE:
            trace.final_status = "NOT_A_CHAPTER"
            return ChapterExtractionResult(
                state=ExtractionState.NOT_A_CHAPTER,
                overall_confidence=page_conf,
                error=page_reason,
                attempts=attempts,
                diagnostics=trace.to_dict(),
            )

        # Extract title and headings
        soup = BeautifulSoup(html_text, "html.parser")
        title_el = soup.find("title")
        page_title = title_el.get_text(strip=True) if title_el else domain

        # -------------------------------------------------------------------
        # RECIPE CHECK: Fast Path vs Stale Fallback
        # -------------------------------------------------------------------
        cached_recipe = self.recipe_store.find_recipe(url)
        stale_recipe_detected = False
        if cached_recipe:
            trace.record_step("RECIPE_CHECK", "RECIPE_FOUND", message=f"Matched recipe for {cached_recipe.domain}")
            # Test recipe preferred strategy
            strat = self._get_strategy_by_id(cached_recipe.preferred_strategy)
            if strat:
                rec_res = await strat.extract(url, html_text=html_text, context=context)
                attempts.append(self._attempt_from_result(rec_res))
                is_valid, rec_conf, issues = self.recipe_validator.validate_candidates(cached_recipe, rec_res.candidates)

                if is_valid and rec_res.status == "SUCCESS":
                    trace.record_step("RECIPE_FASTPATH", "SUCCESS", len(rec_res.candidates), rec_conf, rec_res.elapsed_ms)
                    pool.add_candidates(rec_res.candidates)
                    return self._conclude_extraction(
                        url, pool, "RECIPE_FASTPATH", rec_conf, attempts, trace, page_title=page_title, allow_loopback=allow_loopback
                    )
                else:
                    stale_recipe_detected = True
                    self.recipe_store.remove_recipe(cached_recipe)
                    trace.add_warning(f"Cached recipe stale or invalid: {'; '.join(issues)}. Falling back to generic discovery.")
                    trace.record_step("RECIPE_VALIDATION", "RECIPE_STALE", confidence=0.0, message="Fallback to generic discovery")

        # -------------------------------------------------------------------
        # STRATEGY CASCADE & EVIDENCE FUSION
        # -------------------------------------------------------------------

        # 1. Static DOM
        static_res = await self.strat_static.extract(url, html_text=html_text, context=context)
        attempts.append(self._attempt_from_result(static_res))
        trace.record_step(static_res.strategy_id, static_res.status, len(static_res.candidates), static_res.confidence, static_res.elapsed_ms)
        if static_res.candidates:
            pool.add_candidates(static_res.candidates)

        # 2. Reader Container
        container_res = await self.strat_container.extract(url, html_text=html_text, context=context)
        attempts.append(self._attempt_from_result(container_res))
        trace.record_step(container_res.strategy_id, container_res.status, len(container_res.candidates), container_res.confidence, container_res.elapsed_ms)
        if container_res.candidates:
            pool.add_candidates(container_res.candidates)

        # 3. Lazy Images
        lazy_res = await self.strat_lazy.extract(url, html_text=html_text, context=context)
        attempts.append(self._attempt_from_result(lazy_res))
        trace.record_step(lazy_res.strategy_id, lazy_res.status, len(lazy_res.candidates), lazy_res.confidence, lazy_res.elapsed_ms)
        if lazy_res.candidates:
            pool.add_candidates(lazy_res.candidates)

        # Check early exit after HTML tier
        if self._should_early_exit(pool, min_conf=0.90, min_candidates=4):
            return self._conclude_extraction(
                url, pool, "STATIC_HTML_FUSION", 0.95, attempts, trace, page_title=page_title, learned_recipe=stale_recipe_detected, allow_loopback=allow_loopback
            )

        # 4. Embedded JSON / Hydration Manifest
        json_res = await self.strat_json.extract(url, html_text=html_text, context=context)
        attempts.append(self._attempt_from_result(json_res))
        trace.record_step(json_res.strategy_id, json_res.status, len(json_res.candidates), json_res.confidence, json_res.elapsed_ms)
        if json_res.candidates:
            pool.add_candidates(json_res.candidates)

        if self._should_early_exit(pool, min_conf=0.90, min_candidates=4):
            return self._conclude_extraction(
                url, pool, "EMBEDDED_JSON", 0.96, attempts, trace, page_title=page_title, learned_recipe=stale_recipe_detected, allow_loopback=allow_loopback
            )

        # 5. API Manifest
        api_res = await self.strat_api.extract(url, html_text=html_text, context=context)
        attempts.append(self._attempt_from_result(api_res))
        trace.record_step(api_res.strategy_id, api_res.status, len(api_res.candidates), api_res.confidence, api_res.elapsed_ms)
        if api_res.candidates:
            pool.add_candidates(api_res.candidates)

        if self._should_early_exit(pool, min_conf=0.90, min_candidates=4):
            return self._conclude_extraction(
                url, pool, "API_MANIFEST", 0.96, attempts, trace, page_title=page_title, learned_recipe=stale_recipe_detected, allow_loopback=allow_loopback
            )

        # 6. Rendered DOM (Headless Browser)
        rendered_res = await self.strat_rendered.extract(url, html_text=html_text, context=context)
        attempts.append(self._attempt_from_result(rendered_res))
        trace.record_step(rendered_res.strategy_id, rendered_res.status, len(rendered_res.candidates), rendered_res.confidence, rendered_res.elapsed_ms)
        if rendered_res.candidates:
            pool.add_candidates(rendered_res.candidates)

        # 7. Browser Network Observation
        net_res = await self.strat_network.extract(url, html_text=html_text, context=context)
        attempts.append(self._attempt_from_result(net_res))
        trace.record_step(net_res.strategy_id, net_res.status, len(net_res.candidates), net_res.confidence, net_res.elapsed_ms)
        if net_res.candidates:
            pool.add_candidates(net_res.candidates)

        if self._should_early_exit(pool, min_conf=0.85, min_candidates=3):
            return self._conclude_extraction(
                url, pool, "RENDERED_NETWORK_FUSION", 0.95, attempts, trace, page_title=page_title, learned_recipe=stale_recipe_detected or True, allow_loopback=allow_loopback
            )

        # 8. Resource Timing
        timing_res = await self.strat_timing.extract(url, html_text=html_text, context=context)
        attempts.append(self._attempt_from_result(timing_res))
        trace.record_step(timing_res.strategy_id, timing_res.status, len(timing_res.candidates), timing_res.confidence, timing_res.elapsed_ms)
        if timing_res.candidates:
            pool.add_candidates(timing_res.candidates)

        # Evaluate fused pool after browser & network observation
        if self._should_early_exit(pool, min_conf=0.75, min_candidates=2):
            return self._conclude_extraction(
                url, pool, "RENDERED_NETWORK_FUSION", 0.95, attempts, trace, page_title=page_title, learned_recipe=stale_recipe_detected or True, allow_loopback=allow_loopback
            )

        # 9. Rendered Capture Fallback (Canvas / WebGL)
        capture_res = await self.strat_capture.extract(url, html_text=html_text, context=context)
        attempts.append(self._attempt_from_result(capture_res))
        trace.record_step(capture_res.strategy_id, capture_res.status, len(capture_res.candidates), capture_res.confidence, capture_res.elapsed_ms)
        if capture_res.candidates:
            pool.add_candidates(capture_res.candidates)
            return self._conclude_extraction(
                url, pool, "RENDERED_CAPTURE", 0.75, attempts, trace, page_title=page_title, allow_loopback=allow_loopback
            )

        # -------------------------------------------------------------------
        # UNRESOLVED / TEACH MODE EVALUATION
        # -------------------------------------------------------------------
        all_candidates = pool.all_candidates()
        if not all_candidates:
            fail_state, fail_msg = self.failure_classifier.classify_content_anomaly(
                candidates_found=0, page_type=page_type.value
            )
            trace.final_status = fail_state.value
            return ChapterExtractionResult(
                state=fail_state,
                overall_confidence=0.0,
                error=fail_msg,
                attempts=attempts,
                diagnostics=trace.to_dict(),
            )

        clusters = self.clusterer.cluster_candidates(all_candidates)
        trace.final_status = "NEEDS_REVIEW"
        return ChapterExtractionResult(
            state=ExtractionState.NEEDS_REVIEW,
            overall_confidence=0.50,
            candidate_clusters=clusters,
            needs_review_reasons=["Multiple candidate clusters or low confidence requires user confirmation (Teach Mode)."],
            attempts=attempts,
            diagnostics=trace.to_dict(),
        )

    # -----------------------------------------------------------------------
    # Helper Methods
    # -----------------------------------------------------------------------

    def _should_early_exit(self, pool: GlobalCandidatePool, min_conf: float = 0.90, min_candidates: int = 3) -> bool:
        all_cands = pool.all_candidates()
        if len(all_cands) < min_candidates:
            return False
        clusters = self.clusterer.cluster_candidates(all_cands)
        if not clusters:
            return False
        dominant = clusters[0]
        return dominant.cluster_score >= min_conf and len(dominant.candidates) >= min_candidates

    def _attempt_from_result(self, res: StrategyResult) -> ExtractionAttempt:
        return ExtractionAttempt(
            strategy_id=res.strategy_id,
            status=res.status,
            candidate_count=len(res.candidates),
            confidence=res.confidence,
            elapsed_ms=res.elapsed_ms,
            metadata=res.metadata,
            failure_reason=res.failure_reason,
            diagnostics=res.diagnostics,
        )

    def _get_strategy_by_id(self, strategy_id: str) -> Optional[BaseExtractionStrategy]:
        strategies = {
            "DIRECT_DOCUMENT": self.strat_direct,
            "STATIC_DOM": self.strat_static,
            "READER_CONTAINER": self.strat_container,
            "LAZY_IMAGES": self.strat_lazy,
            "EMBEDDED_JSON": self.strat_json,
            "API_MANIFEST": self.strat_api,
            "RENDERED_DOM": self.strat_rendered,
            "BROWSER_NETWORK": self.strat_network,
            "RESOURCE_TIMING": self.strat_timing,
            "RENDERED_CAPTURE": self.strat_capture,
        }
        return strategies.get(strategy_id)

    def _build_manifest_from_candidates(
        self,
        url: str,
        candidates: List[ImageCandidate],
        strategy_id: str,
        confidence: float,
        completeness: float,
        page_title: Optional[str] = None,
        container_signature: Optional[str] = None,
    ) -> ChapterManifest:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Resolve deterministic natural reading sequence
        pages = self.sequence_resolver.resolve_sequence(candidates, preferred_strategy=strategy_id)

        # Detect layout (paged vs long-strip)
        layout = self.reader_classifier.classify_layout(candidates)

        manifest = ChapterManifest(
            source_url=url,
            canonical_url=url,
            domain=domain,
            page_type=PageType.CHAPTER_PAGE,
            chapter_title=page_title or "Chapter",
            extraction_strategy=strategy_id,
            extraction_confidence=round(confidence, 2),
            completeness_score=round(completeness, 2),
            content_layout=layout,
            reader_container_signature=container_signature,
            pages=pages,
            diagnostics={"strategy_ladder_terminal": strategy_id},
        )
        return manifest

    def _conclude_extraction(
        self,
        url: str,
        pool: GlobalCandidatePool,
        strategy_id: str,
        confidence: float,
        attempts: List[ExtractionAttempt],
        trace: ExtractionTrace,
        page_title: Optional[str] = None,
        learned_recipe: bool = False,
        allow_loopback: bool = False,
    ) -> ChapterExtractionResult:
        all_cands = pool.all_candidates()

        # Sanitize candidates (remove duplicates, placeholders, SSRF risks)
        sanitized_cands, san_issues = self.chapter_validator.sanitize_candidates(
            all_cands, allow_loopback_for_testing=allow_loopback
        )
        for issue in san_issues:
            trace.add_warning(issue)

        # Cluster and select dominant chapter cluster
        clusters = self.clusterer.cluster_candidates(sanitized_cands)
        if not clusters:
            trace.final_status = "NO_CONTENT_IMAGES"
            return ChapterExtractionResult(
                state=ExtractionState.NO_CONTENT_IMAGES,
                overall_confidence=0.0,
                error="All candidates were excluded by quality validation filters",
                attempts=attempts,
                diagnostics=trace.to_dict(),
            )

        dominant_cluster = clusters[0]
        # Re-score candidates against the selected dominant cluster
        scored_cands = self.scorer.score_all(
            dominant_cluster.candidates,
            dominant_cluster=dominant_cluster,
            in_reader_container=bool(dominant_cluster.dominant_parent),
        )
        chapter_candidates = [c for c in scored_cands if c.content_score >= 0.40]
        if not chapter_candidates:
            chapter_candidates = dominant_cluster.candidates

        # Build canonical manifest
        manifest = self._build_manifest_from_candidates(
            url,
            chapter_candidates,
            strategy_id,
            confidence=confidence,
            completeness=1.0,
            page_title=page_title,
            container_signature=dominant_cluster.dominant_parent,
        )

        # Validate completeness
        self.chapter_validator.validate_manifest(manifest)

        # Learn and store self-healing recipe if appropriate
        if learned_recipe or confidence >= 0.85:
            new_recipe = self.recipe_builder.build_from_manifest(manifest, dominant_cluster)
            self.recipe_store.save_recipe(new_recipe, persist=True)
            trace.record_step("RECIPE_LEARNING", "SUCCESS", message=f"Generated and cached recipe for {new_recipe.domain}")

        # Build site fingerprint
        fingerprint = SiteFingerprint(
            domain=manifest.domain,
            path_pattern=new_recipe.chapter_path_pattern if 'new_recipe' in locals() else "/*",
            reader_container_signature=dominant_cluster.dominant_parent,
            known_cdn_hosts=[dominant_cluster.common_host] if dominant_cluster.common_host else [],
            content_architecture="LONG_STRIP" if manifest.content_layout == ContentLayout.LONG_STRIP else "PAGED",
            estimated_page_count=len(manifest.pages),
        )

        trace.final_status = "EXTRACTED"
        return ChapterExtractionResult(
            state=ExtractionState.EXTRACTED,
            manifest=manifest,
            site_fingerprint=fingerprint,
            attempts=attempts,
            final_strategy=strategy_id,
            overall_confidence=manifest.extraction_confidence,
            completeness_score=manifest.completeness_score,
            candidate_clusters=clusters,
            diagnostics=trace.to_dict(),
        )
