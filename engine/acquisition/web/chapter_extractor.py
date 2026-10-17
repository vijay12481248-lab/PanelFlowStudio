"""
Primary public interface for PanelFlow Studio Adaptive Resilient Chapter Extraction Engine.
"""
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from engine.acquisition.web.models.chapter_manifest import ChapterManifest
from engine.acquisition.web.models.extraction_result import ChapterExtractionResult
from engine.acquisition.web.recipes.recipe import ReaderRecipe
from engine.acquisition.web.recipes.recipe_store import RecipeStore
from engine.acquisition.web.orchestrator import AdaptiveChapterOrchestrator
from engine.acquisition.web.downloader import ResumableChapterDownloader
from engine.acquisition.downloader.pipeline import PipelineCancellationToken


class AdaptiveChapterExtractor:
    """
    High-level facade providing extraction, teach-mode recipe learning,
    and resumable chapter asset downloading.
    """

    def __init__(self, recipe_dir: Optional[Path] = None):
        self.recipe_store = RecipeStore(storage_dir=recipe_dir)
        self.orchestrator = AdaptiveChapterOrchestrator(recipe_store=self.recipe_store)
        self.downloader = ResumableChapterDownloader()

    async def extract(
        self,
        url: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ChapterExtractionResult:
        """
        Executes progressive discovery waterfall across multiple strategies
        and returns a canonical ChapterExtractionResult.
        """
        return await self.orchestrator.extract(url, context=context)

    async def download(
        self,
        manifest: ChapterManifest,
        output_dir: Path,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_token: Optional[PipelineCancellationToken] = None,
        allow_loopback_for_testing: bool = False,
    ) -> Dict[str, Any]:
        """
        Downloads all pages declared in ChapterManifest with resume support,
        byte validation, SHA-256 calculation, and atomic moves.
        """
        return await self.downloader.download_chapter(
            manifest=manifest,
            output_dir=output_dir,
            progress_cb=progress_cb,
            cancel_token=cancel_token,
            allow_loopback_for_testing=allow_loopback_for_testing,
        )

    def teach_selection(
        self,
        result: ChapterExtractionResult,
        selected_cluster_id: str,
    ) -> Optional[ReaderRecipe]:
        """
        Teach Mode handler: When extraction state is NEEDS_REVIEW, allows the user
        to select the true chapter image cluster and generates a reusable ReaderRecipe.
        """
        if not result.candidate_clusters:
            return None

        chosen_cluster = None
        for cl in result.candidate_clusters:
            if cl.cluster_id == selected_cluster_id:
                chosen_cluster = cl
                break

        if not chosen_cluster or not result.manifest:
            return None

        # Build recipe from user-selected cluster
        recipe = self.orchestrator.recipe_builder.build_from_manifest(result.manifest, chosen_cluster)
        self.recipe_store.save_recipe(recipe, persist=True)
        return recipe
