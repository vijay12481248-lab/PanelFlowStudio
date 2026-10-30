"""
Comprehensive Unit Tests for Super Motion Graphics Subsystems:
- Effects: Shimmer, Chromatic Aberration, Scanlines, Camera Shake, Particles, Lighting Flares & Vignette
- Typography: Scramble text, Word stagger reveal, Tracking expansion, Rolling counters
- Generative Backgrounds: Fluid caustics, Silk wave ribbons, 3D Cyber grid, 3D Starfield particles
- Presentation Templates: KeynoteShowcaseScene, CyberHUDScene, SciFiContainmentScene, CorporateBenchmarkScene
"""

import pytest
from PIL import Image, ImageDraw, ImageFont

from engine.render.motion import (
    ease_out_expo,
    ease_out_back,
    ease_out_cubic,
    spring_interpolate,
    # Effects
    render_shimmer_text,
    apply_chromatic_aberration,
    apply_scanline_glitch,
    compute_camera_shake,
    ParticleEmitter,
    Particle,
    render_volumetric_glow,
    render_anamorphic_flare,
    render_vignette,
    # Typography
    get_scramble_text,
    draw_word_stagger_reveal,
    draw_tracking_expansion_text,
    compute_rolling_counter,
    # Backgrounds
    FluidCausticsGenerator,
    WaveRibbonMeshGenerator,
    CyberGrid3DGenerator,
    ParticleStarfield3DGenerator,
    # Templates
    KeynoteShowcaseScene,
    CyberHUDScene,
    SciFiContainmentScene,
    CorporateBenchmarkScene,
)


class TestVisualEffects:
    def test_shimmer_text(self):
        canvas = Image.new("RGBA", (400, 200), (10, 10, 20, 255))
        font = ImageFont.load_default()
        res = render_shimmer_text(
            canvas,
            "SYNTHESIS",
            x=50,
            y=50,
            font=font,
            base_color=(255, 255, 255),
            shimmer_color=(124, 58, 237),
            shimmer_phase=0.5,
        )
        assert res.size == (400, 200)
        assert res.mode == "RGBA"

    def test_chromatic_aberration(self):
        img = Image.new("RGB", (320, 240), (40, 120, 200))
        shifted = apply_chromatic_aberration(img, shift_px=6)
        assert shifted.size == (320, 240)
        assert shifted.mode == "RGB"

    def test_scanline_glitch(self):
        img = Image.new("RGB", (320, 240), (50, 50, 50))
        glitched = apply_scanline_glitch(img, glitch_intensity=0.2)
        assert glitched.size == (320, 240)

    def test_camera_shake(self):
        # Zero trauma gives zero offset
        ox0, oy0 = compute_camera_shake(0.0)
        assert ox0 == 0.0 and oy0 == 0.0

        # High trauma produces shake offset within bounds
        ox, oy = compute_camera_shake(0.9, max_offset=15.0)
        assert -15.0 <= ox <= 15.0
        assert -15.0 <= oy <= 15.0

    def test_particle_emitter(self):
        emitter = ParticleEmitter(bounds=(640, 480), max_particles=50)
        canvas = Image.new("RGBA", (640, 480), (10, 10, 15, 255))

        # First tick emits particles
        rendered = emitter.update_and_render(canvas, dt=0.033)
        assert len(emitter.particles) > 0
        assert rendered.size == (640, 480)

    def test_lighting_and_vignette(self):
        canvas = Image.new("RGBA", (300, 300), (20, 20, 30, 255))
        glow = render_volumetric_glow(canvas, center=(150, 150), radius=60, color=(0, 255, 200))
        assert glow.size == (300, 300)

        flare = render_anamorphic_flare(canvas, center=(150, 150), length=200, height=8)
        assert flare.size == (300, 300)

        vig = render_vignette(canvas.convert("RGB"), strength=0.4)
        assert vig.size == (300, 300)


class TestKineticTypography:
    def test_scramble_text(self):
        orig = "SECURITY_BREACH"
        scrambled_0 = get_scramble_text(orig, progress=0.0, seed=1)
        assert len(scrambled_0) == len(orig)
        assert scrambled_0 != orig

        solved_1 = get_scramble_text(orig, progress=1.0, seed=1)
        assert solved_1 == orig

        partial = get_scramble_text(orig, progress=0.5, seed=1)
        assert len(partial) == len(orig)

    def test_word_stagger_reveal(self):
        canvas = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()
        words = ["AUTONOMOUS.", "MULTIMODAL.", "INSTANTANEOUS."]

        # Test at progress 0.0, 0.5, 1.0
        for p in [0.0, 0.5, 1.0]:
            draw_word_stagger_reveal(
                draw=draw,
                words=words,
                center_x=300,
                baseline_y=100,
                font=font,
                progress=p,
                color=(255, 255, 255),
            )
        assert canvas.size == (600, 200)

    def test_tracking_expansion(self):
        canvas = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()

        draw_tracking_expansion_text(
            draw=draw,
            text="FUTURE IS NOW",
            center_x=300,
            y=100,
            font=font,
            progress=0.75,
            min_tracking=2,
            max_tracking=12,
            color=(200, 220, 255),
        )
        assert canvas.size == (600, 200)

    def test_rolling_counter(self):
        # Start at 0, target at 100
        val_0 = compute_rolling_counter(0.0, 100.0, 0.0)
        assert val_0 == 0.0

        val_1 = compute_rolling_counter(0.0, 100.0, 1.0)
        assert val_1 == 100.0

        val_half = compute_rolling_counter(0.0, 100.0, 0.5, easing="ease_out_expo")
        assert val_half > 50.0  # Fast initial rise with expo curve


class TestGenerativeBackgrounds:
    def test_fluid_caustics_generator(self):
        gen = FluidCausticsGenerator(bounds=(640, 360), blur_sigma=30)
        frame1 = gen.render(t=0.0)
        frame2 = gen.render(t=2.5)
        assert frame1.size == (640, 360)
        assert frame2.size == (640, 360)

    def test_wave_ribbon_mesh_generator(self):
        gen = WaveRibbonMeshGenerator(bounds=(640, 360), num_ribbons=4)
        canvas = Image.new("RGBA", (640, 360), (10, 10, 20, 255))
        result = gen.render_onto(canvas, t=1.0)
        assert result.size == (640, 360)

    def test_cyber_grid_3d_generator(self):
        gen = CyberGrid3DGenerator(bounds=(640, 360), horizon_y=180)
        canvas = Image.new("RGBA", (640, 360), (5, 5, 10, 255))
        result = gen.render_onto(canvas, t=0.8)
        assert result.size == (640, 360)

    def test_particle_starfield_3d_generator(self):
        gen = ParticleStarfield3DGenerator(bounds=(640, 360), num_stars=60)
        canvas = Image.new("RGBA", (640, 360), (0, 0, 5, 255))
        result = gen.render_onto(canvas, t=1.5)
        assert result.size == (640, 360)


class TestPresentationTemplates:
    def test_keynote_showcase_scene(self):
        scene = KeynoteShowcaseScene(
            headline="NEURAL SYNAPSE",
            subtitle="Autonomous Visual Supercomputing",
            badge_text="SPECIAL EVENT",
            bounds=(640, 360),
            duration_sec=4.0,
        )
        frame_in = scene.render_frame(0.4)
        frame_mid = scene.render_frame(2.0)
        assert frame_in.size == (640, 360)
        assert frame_in.mode == "RGB"
        assert frame_mid.size == (640, 360)
        assert frame_mid.mode == "RGB"

    def test_cyber_hud_scene(self):
        scene = CyberHUDScene(
            title="SYSTEM CORE V9",
            target_name="CYBER_TITAN",
            bounds=(640, 360),
            duration_sec=4.0,
        )
        # Check during initial chromatic glitch phase
        frame_glitch = scene.render_frame(0.2)
        # Check during stable phase
        frame_stable = scene.render_frame(2.5)
        assert frame_glitch.size == (640, 360)
        assert frame_stable.size == (640, 360)

    def test_scifi_containment_scene(self):
        scene = SciFiContainmentScene(
            title="CONTAINMENT BREACH",
            facility="ZONE 42",
            bounds=(640, 360),
            duration_sec=4.0,
        )
        # Check during camera shake & glitch phase
        frame_shake = scene.render_frame(0.5)
        frame_late = scene.render_frame(3.5)
        assert frame_shake.size == (640, 360)
        assert frame_late.size == (640, 360)

    def test_corporate_benchmark_scene(self):
        scene = CorporateBenchmarkScene(
            title="LATENCY REDUCTION",
            subtitle="Comparing PanelFlow V8 against benchmarks",
            bounds=(640, 360),
            duration_sec=4.0,
        )
        frame1 = scene.render_frame(1.2)
        frame2 = scene.render_frame(3.0)
        assert frame1.size == (640, 360)
        assert frame2.size == (640, 360)
