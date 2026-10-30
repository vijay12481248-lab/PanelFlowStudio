"""Unit tests for the autonomous Motion Graphics and Kinetic Animation Engine."""

import pytest
from PIL import Image

from engine.render.motion.curves import (
    clamp,
    ease_linear,
    ease_out_cubic,
    ease_out_back,
    ease_out_expo,
    ease_out_elastic,
    spring_interpolate,
    interpolate_value,
)
from engine.render.motion.elements import (
    KineticTextElement,
    CardElement,
    ConnectorTrackElement,
    MetricCounterElement,
    AttentionHeatmapElement,
)
from engine.render.motion.scene import MotionScene
from engine.render.motion.rag_patterns import (
    find_best_motion_pattern,
    build_timeline_motion_scene,
    build_attention_matrix_motion_scene,
    build_diffusion_pipeline_motion_scene,
)
from engine.pipeline.ai_motion_director import AIMotionDirector


class TestMotionCurves:
    def test_clamp(self):
        assert clamp(-0.5) == 0.0
        assert clamp(1.5) == 1.0
        assert clamp(0.7) == 0.7

    def test_ease_out_cubic(self):
        assert ease_out_cubic(0.0) == 0.0
        assert ease_out_cubic(1.0) == 1.0
        assert ease_out_cubic(0.5) > 0.5  # Fast initial rise

    def test_ease_out_back_overshoot(self):
        assert ease_out_back(0.0) == 0.0
        assert ease_out_back(1.0) == 1.0
        # Should overshoot 1.0 around t=0.6 - 0.8
        overshoot_val = ease_out_back(0.7)
        assert overshoot_val > 1.0, f"Expected overshoot > 1.0, got {overshoot_val}"

    def test_ease_out_expo(self):
        assert ease_out_expo(0.0) == 0.0
        assert ease_out_expo(1.0) == 1.0
        assert ease_out_expo(0.2) > 0.7  # Explosive initial acceleration

    def test_spring_interpolate(self):
        assert spring_interpolate(0.0) == 0.0
        assert spring_interpolate(1.0) == 1.0
        val = spring_interpolate(0.5, stiffness=120.0, damping=8.0)
        assert 0.0 <= val <= 1.5

    def test_interpolate_value(self):
        res = interpolate_value(10.0, 100.0, 0.5, curve="ease_out_cubic")
        assert 70.0 < res < 95.0


class TestMotionElements:
    def test_kinetic_text_element_rendering(self):
        el = KineticTextElement("title_1", "Test Motion Title", x=50, y=50, enter_time=0.5, category_badge="TEST")
        canvas = Image.new("RGBA", (1280, 720), (0, 0, 0, 255))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(canvas)

        # Before enter time: should not render
        el.render(canvas, draw, t=0.2, w=1280, h=720)
        # At enter time: renders
        el.render(canvas, draw, t=1.0, w=1280, h=720)
        assert el.is_visible(1.0) is True

    def test_card_element_stagger_and_activation(self):
        card = CardElement(
            "card_1", x=60, y=200, width=200, height=220,
            title="Card Title", subtitle="Card Subtitle", tag="1950",
            enter_time=1.0, active_time_range=(2.0, 3.5),
        )
        assert card.is_visible(0.5) is False
        assert card.is_visible(1.2) is True
        assert card.is_active(1.5) is False
        assert card.is_active(2.5) is True
        assert card.is_active(4.0) is False

        canvas = Image.new("RGBA", (1280, 720), (10, 10, 10, 255))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(canvas)
        card.render(canvas, draw, t=2.5, w=1280, h=720)

    def test_connector_track_element(self):
        track = ConnectorTrackElement("track_1", (50, 300), (1000, 300), enter_time=0.5, draw_duration=2.0)
        canvas = Image.new("RGBA", (1280, 720), (0, 0, 0, 255))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(canvas)
        track.render(canvas, draw, t=1.5, w=1280, h=720)
        assert track.get_enter_progress(1.5) == 0.5

    def test_metric_counter_element(self):
        counter = MetricCounterElement("cnt_1", x=50, y=500, width=800, height=100, label="Scale", target_value=1000, enter_time=1.0)
        assert counter.get_enter_progress(0.5) == 0.0
        assert counter.get_enter_progress(2.8) == 1.0


class TestMotionScene:
    def test_motion_scene_render_frame(self):
        scene = MotionScene("scene_test", duration_sec=5.0)
        scene.add_element(KineticTextElement("title", "Hello Motion", 50, 50, enter_time=0.1))
        scene.add_element(CardElement("card", 50, 150, 200, 200, "C1", "Desc", enter_time=0.5))

        frame = scene.render_frame(t=1.0, size=(1280, 720))
        assert frame.size == (1280, 720)
        assert frame.mode == "RGB"
        # Check that canvas has color content
        assert frame.getpixel((640, 360)) != (0, 0, 0)


class TestRAGPatternsAndDirector:
    def test_rag_pattern_retrieval(self):
        pat_timeline = find_best_motion_pattern("The historical evolution and milestones of deep learning")
        assert pat_timeline["id"] == "timeline_roadmap"

        pat_attn = find_best_motion_pattern("Self-attention matrix with Query Key Value dot products in Transformers")
        assert pat_attn["id"] == "attention_matrix"

        pat_diff = find_best_motion_pattern("Generative latent diffusion pipeline with progressive denoising steps")
        assert pat_diff["id"] == "diffusion_pipeline"

    def test_ai_motion_director_builds_complete_scene(self):
        director = AIMotionDirector()
        clips = [
            {"text": "In 2017, the Transformer introduced self-attention mechanism across word tokens.", "start_time_sec": 0.0}
        ]
        scene = director.direct_scene("scene_transformers", 10.0, clips, topic_hint="Attention Matrix")
        assert len(scene.elements) >= 3
        frame = scene.render_frame(t=2.0)
        assert frame.size == (1280, 720)


class TestEndToEndMotionIntegration:
    def test_compiler_and_composer_integration(self, tmp_path):
        from engine.render.compiler import TimelineCompiler
        from engine.render.composer import FrameComposer
        from engine.pipeline.ai_motion_director import AIMotionDirector

        director = AIMotionDirector()
        m_scene = director.direct_scene(
            "scene_motion_integration",
            4.0,
            [{"text": "The attention mechanism in Transformer models.", "start_time_sec": 0.0}],
            topic_hint="Attention Matrix",
        )

        state = {
            "scenes": [
                {
                    "id": "shot_motion",
                    "duration_sec": 4.0,
                    "start_time_sec": 0.0,
                    "layers": [
                        {
                            "id": "ly_motion",
                            "type": "motion_graphic",
                            "motion_scene": m_scene,
                            "start_offset_sec": 0.0,
                            "duration_sec": 4.0,
                        }
                    ],
                }
            ]
        }

        compiler = TimelineCompiler()
        plan = compiler.compile(state=state, project_id="test_mg", workspace_path=tmp_path)
        composer = FrameComposer()

        frame = composer.compose_frame(30, plan)
        assert frame is not None
        assert frame.size[0] > 0 and frame.size[1] > 0
        assert frame.mode == "RGB"
