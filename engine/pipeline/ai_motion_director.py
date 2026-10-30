"""AI Motion Director: RAG-driven autonomous motion graphics generation.

Analyzes narration transcripts and timestamps to automatically select, choreograph,
and assemble After Effects-grade procedural motion graphics scenes.
"""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional
from engine.render.motion.scene import MotionScene
from engine.render.motion.rag_patterns import (
    find_best_motion_pattern,
    build_timeline_motion_scene,
    build_attention_matrix_motion_scene,
    build_diffusion_pipeline_motion_scene,
)


class AIMotionDirector:
    """Autonomous motion graphics director with RAG pattern retrieval."""

    def __init__(self) -> None:
        pass

    def direct_scene(
        self,
        scene_id: str,
        duration_sec: float,
        narration_clips: List[Dict[str, Any]],
        topic_hint: Optional[str] = None,
    ) -> MotionScene:
        """Analyzes narration and synthesizes an optimal motion graphics scene."""
        combined_text = " ".join([c.get("text", "") for c in narration_clips])
        if topic_hint:
            combined_text = f"{topic_hint} {combined_text}"

        pattern = find_best_motion_pattern(combined_text)
        pid = pattern["id"]

        if pid == "attention_matrix":
            tokens = ["The", "autonomous", "agent", "navigated", "the", "maze"]
            weights = [
                [0.40, 0.10, 0.35, 0.05, 0.05, 0.05],
                [0.05, 0.65, 0.20, 0.05, 0.02, 0.03],
                [0.08, 0.25, 0.50, 0.10, 0.02, 0.05],
                [0.02, 0.10, 0.30, 0.45, 0.03, 0.10],
                [0.05, 0.05, 0.05, 0.05, 0.35, 0.45],
                [0.02, 0.05, 0.20, 0.25, 0.10, 0.38],
            ]
            bullets = [
                {"title": "QKV Projections", "desc": "Dot-product token query alignment across embeddings."},
                {"title": "Global Scaling", "desc": "O(1) path length across sequence contexts."},
                {"title": "Massive Parallelism", "desc": "Concurrent GPU tensor core pretraining."},
            ]
            return build_attention_matrix_motion_scene(
                scene_id=scene_id,
                duration_sec=duration_sec,
                title="The Transformer & Self-Attention",
                category="ARCHITECTURAL FOUNDATIONS",
                tokens=tokens,
                weights=weights,
                insight_bullets=bullets,
            )

        elif pid == "diffusion_pipeline":
            steps = [
                {"title": "Input x0", "desc": "Latent space encoding"},
                {"title": "Forward (+Noise)", "desc": "T=1000 Gaussian steps"},
                {"title": "Pure Noise", "desc": "Stochastic Gaussian prior"},
                {"title": "Denoising (U-Net)", "desc": "Noise vector prediction"},
                {"title": "Text Conditioning", "desc": "Cross-attention steering"},
                {"title": "Synthesis", "desc": "VAE HD decoding"},
            ]
            return build_diffusion_pipeline_motion_scene(
                scene_id=scene_id,
                duration_sec=duration_sec,
                title="Generative AI & Latent Diffusion",
                category="MULTIMODAL SYNTHESIS",
                steps=steps,
            )

        else:
            # Default to Timeline Roadmap pattern
            items = [
                {"tag": "1950", "title": "Turing Test", "desc": "Algorithmic machine imitation"},
                {"tag": "1957", "title": "Perceptron", "desc": "First artificial neuron"},
                {"tag": "1986", "title": "Backpropagation", "desc": "Loss gradient descent"},
                {"tag": "2012", "title": "AlexNet & GPUs", "desc": "Deep convolutional vision"},
                {"tag": "2017+", "title": "Transformers", "desc": "Attention across context"},
            ]
            items[0]["metric"] = {"label": "Frontier Parameter Scale", "value": 175000000000, "suffix": "Weights"}

            return build_timeline_motion_scene(
                scene_id=scene_id,
                duration_sec=duration_sec,
                title="The Evolution of Artificial Intelligence",
                category="HISTORICAL REVOLUTION",
                items=items,
            )
