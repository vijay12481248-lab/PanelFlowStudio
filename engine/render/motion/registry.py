"""
Centralized Motion Graphics Preset Registry for PanelFlow Studio.
Manages metadata, schema definitions, and scene instantiation for all production presets.
Now expanded to 10 production-grade presets spanning Keynotes, Cyberpunk, Sci-Fi, SaaS,
Swiss Editorial, Anime Combat, Matrix Terminals, 80s Synthwave, Luxury Gold, and Cosmic Warp.
"""

from typing import List, Dict, Any, Optional, Tuple, Type
from engine.render.motion.models import MotionPresetDefinition
from engine.render.motion.presentation.templates import (
    KeynoteShowcaseScene,
    CyberHUDScene,
    SciFiContainmentScene,
    CorporateBenchmarkScene,
    KineticEditorialScene,
    AnimeBattleHUDScene,
    AEDynamicKineticScene,
    GlobalShoeOrbitScene,
)
from engine.render.motion.presentation.cinema_templates import (
    MatrixDigitalRainScene,
    SynthwaveSunsetScene,
    LuxuryGoldMonogramScene,
    CosmicNebulaWarpScene,
)


class MotionRegistry:
    """Central registry and factory for professional motion graphics presets."""

    _PRESETS: Dict[str, MotionPresetDefinition] = {
        "keynote_showcase": MotionPresetDefinition(
            id="keynote_showcase",
            name="Apple Keynote Showcase",
            category="Keynote",
            description="Luxury product presentation with fluid caustics, wave silk ribbons, specular shimmers, and glassmorphic rolling metric cards.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "headline": "SYNTHESIS ONE",
                "subtitle": "The Next Generation Neural Presentation Architecture",
                "badge_text": "GLOBAL KEYNOTE 2026",
                "accent_color": [124, 58, 237],
                "metrics": [
                    {"val": 99.8, "unit": "%", "label": "PRECISION ACCURACY", "delta": "+14.2%"},
                    {"val": 3.8, "unit": "x", "label": "FASTER INFERENCE", "delta": "+280%"},
                    {"val": 1.2, "unit": "ms", "label": "MEDIAN LATENCY", "delta": "-68%"},
                ],
            },
            preview_description="Liquid ambient gradient with sweeping specular shimmer headline and rolling cards.",
        ),
        "cyber_hud": MotionPresetDefinition(
            id="cyber_hud",
            name="Cyberpunk Tactical HUD",
            category="Cyberpunk",
            description="Esports & broadcast telemetry HUD with 3D horizon floor grid, starfield warp, hacker scramble decrypt, and procedural audio equalizers.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "title": "CYBERNETIC_MAINFRAME // V8",
                "target_name": "UNIT_AEGIS_09",
                "status": "STATUS: SYNCHRONIZED",
                "accent_color": [0, 255, 170],
                "telemetry": [
                    "SYS.LATENCY: 0.42 ms",
                    "QUANTUM_CORE: STABLE",
                    "NEURAL_LINK: 100.0%",
                    "PROTOCOL: AES-GCM-256",
                ],
            },
            preview_description="Receding neon cyan grid with hacker scramble title and animated equalizer bars.",
        ),
        "scifi_containment": MotionPresetDefinition(
            id="scifi_containment",
            name="Sci-Fi Containment Breach",
            category="Sci-Fi",
            description="Cinematic breach warning title sequence with crimson caustics, floating embers, camera shake trauma, and chromatic glitching.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "title": "CONTAINMENT FAILURE",
                "facility": "SUBTERRANEAN SECTOR 09",
                "threat_level": "CLASS 5 : PROTOCOL BREACH",
                "warning_text": "NEURAL RESTRICTIONS DISSOLVED // OVERRIDE ACTIVE",
                "accent_color": [239, 68, 68],
            },
            preview_description="Pulsing crimson breach alert with floating fire embers and camera shake.",
        ),
        "corporate_benchmark": MotionPresetDefinition(
            id="corporate_benchmark",
            name="Enterprise SaaS Benchmark",
            category="Enterprise",
            description="Corporate AI throughput and latency benchmark comparison with animated progress bars, live KPI metrics, and verified badge.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "title": "ENTERPRISE INFERENCE BENCHMARK",
                "subtitle": "PanelFlow Studio v8.0 vs Industry Standard Baselines",
                "accent_color": [6, 182, 212],
                "benchmarks": [
                    {"model": "PanelFlow Engine (v8)", "score": 96.4, "highlight": True},
                    {"model": "Standard Framework A", "score": 71.2, "highlight": False},
                    {"model": "Legacy Batch Pipeline", "score": 48.6, "highlight": False},
                ],
                "kpis": [
                    {"label": "THROUGHPUT", "val": 420.0, "unit": " fps"},
                    {"label": "VRAM FOOTPRINT", "val": 1.4, "unit": " GB"},
                    {"label": "COST EFFICIENCY", "val": 94.2, "unit": "%"},
                ],
            },
            preview_description="Multi-model benchmark chart with glowing fill bars and rolling KPI metrics.",
        ),
        "kinetic_editorial": MotionPresetDefinition(
            id="kinetic_editorial",
            name="Swiss Kinetic Editorial",
            category="Editorial",
            description="High-contrast typographic manifesto with bold tracking expansion, architectural grid wipe lines, and acid yellow accents.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "headline": "ARCHITECTURAL SYNTAX",
                "subtitle": "Pure Typographic Motion & Kinetic Geometry",
                "issue_tag": "VOL. 08 // SPECIAL EDITION",
                "statement": "FORM FOLLOWS LOGIC. EVERY PIXEL HAS PURPOSE.",
                "accent_color": [250, 204, 21],
            },
            preview_description="Stark monochrome editorial design with animated divider rules and tracking text.",
        ),
        "anime_battle_hud": MotionPresetDefinition(
            id="anime_battle_hud",
            name="Shonen Combat Battle HUD",
            category="Anime",
            description="Combat tactical anime HUD with fighter plate, scramble technique name, rolling battle power level (9M+), and energy shield gauge.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "fighter_name": "SHADOW REAPER // KAI",
                "technique_name": "FORBIDDEN DOMAIN: ABYSS REND",
                "power_level": 9450000,
                "status": "LIMITER RELEASE: 100%",
                "threat_rank": "SPECIAL GRADE [S]",
                "accent_color": [249, 115, 22],
                "secondary_color": [239, 68, 68],
            },
            preview_description="Fiery combat HUD with 3D perspective floor, energy gauge, and power level roll.",
        ),
        "matrix_rain": MotionPresetDefinition(
            id="matrix_rain",
            name="Matrix Cyber Terminal",
            category="Cyberpunk",
            description="Cascading vertical Katakana and Hex digital rain streams with leading phosphor glow and hacker typewriter prompt.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "headline": "ACCESS GRANTED // MAINFRAME INFILTRATED",
                "subtitle": "Root privileges acquired. Decrypting neural weights...",
                "badge_text": "SYSTEM COMPROMISED",
                "accent_color": [34, 197, 94],
            },
            preview_description="Cascading green digital glyph streams with active phosphor leader and typewriter box.",
        ),
        "synthwave_sunset": MotionPresetDefinition(
            id="synthwave_sunset",
            name="80s Retro Synthwave Sunset",
            category="Retro",
            description="Outrun synthwave sunset with sliced radiant sun orb, horizon wireframe mountains, 3D floor grid, and chrome specular headline.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "headline": "OUTRUN THE FUTURE",
                "subtitle": "Retro Electro Aesthetics // Neural Frequency 1984",
                "badge_text": "SYNTHWAVE 84",
                "accent_color": [244, 63, 94],
                "secondary_color": [168, 85, 247],
            },
            preview_description="Radiant sliced sunset over wireframe mountains and neon magenta floor grid.",
        ),
        "luxury_gold": MotionPresetDefinition(
            id="luxury_gold",
            name="Luxury Gold Monogram",
            category="Prestige",
            description="Prestige award title sequence with 3D extruded gold typography, sweeping specular sheen, and floating warm gold bokeh.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "headline": "AURELIA CINEMA",
                "subtitle": "Grand Award of Cinematic Distinction 2026",
                "badge_text": "OFFICIAL SELECTION",
                "accent_color": [234, 179, 8],
            },
            preview_description="Deep royal velvet caustics with 3D extruded gold monogram and floating dust.",
        ),
        "cosmic_warp": MotionPresetDefinition(
            id="cosmic_warp",
            name="Cosmic Nebula Warp",
            category="Sci-Fi",
            description="Deep space hyperspace warp jump with gravitational lens vortex, high-speed 3D starfield velocity streaks, and warp shockwave trauma.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "headline": "WARP FACTOR 9.9 // ENGAGED",
                "subtitle": "Folding space-time metrics... Destination: Sector Andromeda",
                "badge_text": "HYPERSPACE ACCELERATION",
                "accent_color": [168, 85, 247],
            },
            preview_description="Interstellar nebula caustics with high-speed warping starfield and gravitational vortex.",
        ),
        "ae_dynamic_kinetic": MotionPresetDefinition(
            id="ae_dynamic_kinetic",
            name="After Effects Kinetic",
            category="After Effects",
            description="Professional Adobe After Effects motion mechanics: Per-character Range Selectors, 75%/85% Keyframe Velocity curves, Dan Ebberts inertia bounce, and 180° shutter angle motion blur.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "headline": "AFTER EFFECTS KINETIC",
                "subtitle": "Procedural Range Selectors & Velocity Interpolation",
                "badge_text": "ADOBE AE ENGINE // 60FPS",
                "accent_color": [99, 102, 241],
                "metrics": [
                    {"val": 85.0, "unit": "%", "label": "VELOCITY INFLUENCE"},
                    {"val": 180.0, "unit": "°", "label": "SHUTTER ANGLE"},
                    {"val": 60.0, "unit": "fps", "label": "SUB-FRAME SAMPLING"},
                ],
            },
            preview_description="Dynamic AE Range Selector kinetic typography with Dan Ebberts inertia bounce KPI cards.",
        ),
        "shoe_brand_orbit": MotionPresetDefinition(
            id="shoe_brand_orbit",
            name="Global Shoe 3D Orbit",
            category="Product 3D",
            description="Flagship athletic footwear commercial with weightless levitating sneaker and 3D cylindrical orbital kinetic typography turning around the shoe in true spatial depth.",
            default_duration=6.0,
            aspect_ratios=["16:9", "9:16"],
            default_props={
                "headline": "AETHER VELOCITY ONE",
                "subtitle": "SUPPLYING EVERY CORNER OF THE WORLD",
                "orbit_text_1": "AETHER VELOCITY ONE // ZERO-GRAVITY NITROGEN // FULL-LENGTH CARBON PLATE // ",
                "orbit_text_2": "SUPPLYING EVERY CORNER OF THE WORLD // 195 COUNTRIES // WORLDWIDE LOGISTICS // ",
                "accent_color": [6, 182, 212],
            },
            preview_description="Hero floating sneaker with dual counter-rotating 3D kinetic typography rings turning around the shoe.",
        ),
    }

    _SCENE_CLASSES: Dict[str, Type] = {
        "keynote_showcase": KeynoteShowcaseScene,
        "cyber_hud": CyberHUDScene,
        "scifi_containment": SciFiContainmentScene,
        "corporate_benchmark": CorporateBenchmarkScene,
        "kinetic_editorial": KineticEditorialScene,
        "anime_battle_hud": AnimeBattleHUDScene,
        "matrix_rain": MatrixDigitalRainScene,
        "synthwave_sunset": SynthwaveSunsetScene,
        "luxury_gold": LuxuryGoldMonogramScene,
        "cosmic_warp": CosmicNebulaWarpScene,
        "ae_dynamic_kinetic": AEDynamicKineticScene,
        "shoe_brand_orbit": GlobalShoeOrbitScene,
    }

    @classmethod
    def list_presets(cls) -> List[MotionPresetDefinition]:
        """Returns all registered motion graphics presets."""
        return list(cls._PRESETS.values())

    @classmethod
    def get_preset(cls, preset_id: str) -> Optional[MotionPresetDefinition]:
        """Retrieves preset definition by ID."""
        return cls._PRESETS.get(preset_id)

    @classmethod
    def create_scene(
        cls,
        preset_id: str,
        props: Optional[Dict[str, Any]] = None,
        duration_sec: Optional[float] = None,
        bounds: Optional[Tuple[int, int]] = None,
        aspect_ratio: str = "16:9",
        audio_path: Optional[str] = None,
    ) -> Any:
        """
        Instantiates a ready-to-render motion graphics scene.
        """
        scene_cls = cls._SCENE_CLASSES.get(preset_id)
        if not scene_cls:
            raise ValueError(f"Unknown motion preset ID: {preset_id}. Available: {list(cls._PRESETS.keys())}")

        preset_def = cls._PRESETS[preset_id]
        merged_props = dict(preset_def.default_props)
        if props:
            merged_props.update(props)

        # Resolve aspect ratio & bounds
        eff_bounds = bounds
        if not eff_bounds:
            if aspect_ratio == "9:16":
                eff_bounds = (720, 1280)
            else:
                eff_bounds = (1280, 720)

        eff_duration = duration_sec if duration_sec is not None else preset_def.default_duration

        # Convert accent color list to tuple if provided as list
        for col_key in ("accent_color", "secondary_color"):
            if col_key in merged_props and isinstance(merged_props[col_key], (list, tuple)):
                merged_props[col_key] = tuple(int(c) for c in merged_props[col_key][:3])

        kwargs = dict(merged_props)
        kwargs["bounds"] = eff_bounds
        kwargs["duration_sec"] = eff_duration

        # Pass audio_path if accepted by scene constructor
        if preset_id == "matrix_rain" and audio_path:
            kwargs["audio_path"] = audio_path

        return scene_cls(**kwargs)
