"""Motion Graphics Design Pattern Catalog & RAG Knowledge Base.

Defines procedural blueprints for After Effects-style animations that can be
queried and assembled automatically by the AI Motion Director.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional, Callable
from engine.render.motion.scene import MotionScene
from engine.render.motion.elements import (
    KineticTextElement,
    CardElement,
    ConnectorTrackElement,
    MetricCounterElement,
    AttentionHeatmapElement,
)


def build_timeline_motion_scene(
    scene_id: str,
    duration_sec: float,
    title: str,
    category: str,
    items: List[Dict[str, Any]],
    highlight_idx: Optional[int] = None,
) -> MotionScene:
    """Builds a staggered milestone timeline with dynamic connector track."""
    scene = MotionScene(scene_id, duration_sec=duration_sec)

    # 1. Kinetic Header
    scene.add_element(
        KineticTextElement(
            element_id=f"{scene_id}_title",
            text=title,
            x=60,
            y=60,
            enter_time=0.2,
            enter_duration=0.7,
            category_badge=category,
            badge_color=(0, 240, 255),
        )
    )

    # 2. Dynamic Connector Track
    scene.add_element(
        ConnectorTrackElement(
            element_id=f"{scene_id}_track",
            start_pt=(60, 330),
            end_pt=(1220, 330),
            enter_time=0.6,
            draw_duration=2.5,
            color=(0, 240, 255),
        )
    )

    # 3. Staggered Milestone Cards
    count = min(5, len(items))
    card_w = 216
    card_h = 240
    card_spacing = (1160 - (count * card_w)) // max(1, count - 1)

    colors = [
        (0, 240, 255),    # Cyan
        (59, 130, 246),   # Electric Blue
        (168, 85, 247),   # Purple
        (236, 72, 153),   # Pink
        (249, 115, 22),   # Orange
    ]

    for idx in range(count):
        item = items[idx]
        enter_t = 0.8 + idx * 0.5
        active_range = (enter_t + 0.1, enter_t + 2.0) if highlight_idx == idx or highlight_idx is None else None

        scene.add_element(
            CardElement(
                element_id=f"{scene_id}_card_{idx}",
                x=60 + idx * (card_w + card_spacing),
                y=210,
                width=card_w,
                height=card_h,
                title=item.get("title", ""),
                subtitle=item.get("desc", ""),
                tag=item.get("tag", str(idx + 1)),
                tag_color=colors[idx % len(colors)],
                enter_time=enter_t,
                enter_duration=0.6,
                active_time_range=active_range,
            )
        )

    # 4. Optional metric counter if provided
    if "metric" in items[0]:
        metric = items[0]["metric"]
        scene.add_element(
            MetricCounterElement(
                element_id=f"{scene_id}_metric",
                x=60,
                y=500,
                width=1160,
                height=110,
                label=metric.get("label", "Scale"),
                target_value=metric.get("value", 1000000),
                suffix=metric.get("suffix", ""),
                enter_time=2.8,
            )
        )

    return scene


def build_attention_matrix_motion_scene(
    scene_id: str,
    duration_sec: float,
    title: str,
    category: str,
    tokens: List[str],
    weights: List[List[float]],
    insight_bullets: List[str],
) -> MotionScene:
    """Builds a dynamic Self-Attention heatmap scene with side architectural cards."""
    scene = MotionScene(scene_id, duration_sec=duration_sec)

    # 1. Kinetic Header
    scene.add_element(
        KineticTextElement(
            element_id=f"{scene_id}_title",
            text=title,
            x=60,
            y=60,
            enter_time=0.2,
            category_badge=category,
            badge_color=(236, 72, 153),
        )
    )

    # 2. Dynamic Attention Heatmap Grid
    scene.add_element(
        AttentionHeatmapElement(
            element_id=f"{scene_id}_heatmap",
            x=60,
            y=180,
            tokens=tokens,
            weights=weights,
            enter_time=0.8,
            enter_duration=1.8,
        )
    )

    # 3. Architectural Insight Cards on the Right
    right_x = 680
    right_w = 540
    for idx, bullet in enumerate(insight_bullets[:3]):
        scene.add_element(
            CardElement(
                element_id=f"{scene_id}_insight_{idx}",
                x=right_x,
                y=210 + idx * 135,
                width=right_w,
                height=115,
                title=bullet.get("title", f"Principle {idx+1}") if isinstance(bullet, dict) else f"Principle {idx+1}",
                subtitle=bullet.get("desc", bullet) if isinstance(bullet, dict) else bullet,
                tag=f"0{idx+1}",
                tag_color=(0, 240, 255) if idx == 0 else (168, 85, 247),
                enter_time=1.2 + idx * 0.7,
                enter_duration=0.6,
            )
        )

    return scene


def build_diffusion_pipeline_motion_scene(
    scene_id: str,
    duration_sec: float,
    title: str,
    category: str,
    steps: List[Dict[str, str]],
) -> MotionScene:
    """Builds a multi-stage generative flow pipeline with progressive step illumination."""
    scene = MotionScene(scene_id, duration_sec=duration_sec)

    scene.add_element(
        KineticTextElement(
            element_id=f"{scene_id}_title",
            text=title,
            x=60,
            y=60,
            enter_time=0.2,
            category_badge=category,
            badge_color=(249, 115, 22),
        )
    )

    count = min(6, len(steps))
    card_w = (1160 - (count - 1) * 16) // count
    card_h = 280

    for idx in range(count):
        step = steps[idx]
        enter_t = 0.6 + idx * 0.4
        scene.add_element(
            CardElement(
                element_id=f"{scene_id}_step_{idx}",
                x=60 + idx * (card_w + 16),
                y=190,
                width=card_w,
                height=card_h,
                title=step.get("title", f"Step {idx+1}"),
                subtitle=step.get("desc", ""),
                tag=f"Step {idx+1}",
                tag_color=(249, 115, 22) if idx % 2 == 0 else (0, 240, 255),
                enter_time=enter_t,
                enter_duration=0.5,
                rise_distance=60,
            )
        )

    # Connector across all steps
    scene.add_element(
        ConnectorTrackElement(
            element_id=f"{scene_id}_step_track",
            start_pt=(60, 490),
            end_pt=(1220, 490),
            enter_time=0.8,
            draw_duration=2.4,
            color=(249, 115, 22),
        )
    )

    return scene


# RAG Blueprint Registry
MOTION_GRAPHICS_PATTERNS: Dict[str, Dict[str, Any]] = {
    "timeline_roadmap": {
        "id": "timeline_roadmap",
        "name": "Kinetic Milestone Timeline",
        "description": "Horizontal chronological progression with dynamic connector track and staggered milestone cards.",
        "keywords": ["timeline", "history", "evolution", "chronology", "milestones", "years", "stages", "past"],
        "builder": build_timeline_motion_scene,
    },
    "attention_matrix": {
        "id": "attention_matrix",
        "name": "Attention Heatmap & Token Association",
        "description": "Multi-token attention matrix with illuminating cells and architectural principle cards.",
        "keywords": ["attention", "transformer", "matrix", "tokens", "self-attention", "query", "key", "value", "heatmap"],
        "builder": build_attention_matrix_motion_scene,
    },
    "diffusion_pipeline": {
        "id": "diffusion_pipeline",
        "name": "Generative Flow Pipeline",
        "description": "Sequential multistep pipeline with progressive card illumination and connector track.",
        "keywords": ["diffusion", "generative", "pipeline", "steps", "flow", "denoising", "latent", "unet", "process"],
        "builder": build_diffusion_pipeline_motion_scene,
    },
}


def find_best_motion_pattern(query_text: str) -> Dict[str, Any]:
    """Semantic/keyword query matching against the RAG motion pattern catalog."""
    query_lower = query_text.lower()
    best_pattern = MOTION_GRAPHICS_PATTERNS["timeline_roadmap"]
    highest_score = -1

    for pid, pattern in MOTION_GRAPHICS_PATTERNS.items():
        score = 0
        for kw in pattern["keywords"]:
            if kw in query_lower:
                score += 1
        if score > highest_score:
            highest_score = score
            best_pattern = pattern

    return best_pattern
