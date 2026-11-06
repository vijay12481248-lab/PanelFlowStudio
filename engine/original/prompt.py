"""Centralized Global Prompt Architecture & Directorial Compilation Pipeline for PanelFlow Studio.

Implements Requirements R2 & R3 (Milestone M2) adhering to docs/PROMPT_PRACTITIONER_GUIDE.md.
Provides tool-agnostic Pydantic data schemas, 4-tier visual style anchors, character identity
tokens with the unnaming protocol, camera optics, composition guardrails, and model-specific
compiled prompt contracts for Qwen Image 2.1 (ArtEngine), MiniMax Fast H3 Turbo (ChronoFlow),
and Legacy SDXL.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from engine.original.genres import GENRES
from engine.original.models import Character, OriginalStory, Panel
from engine.original.shotspec import (
    CharPose,
    ShotSpec,
    resolve_dimensions,
    compile_interaction_bindings_natural,
    compile_interaction_bindings_tags,
    unname,
    describe_character,
    person_tags,
    tags_for,
    light_tags,
    pose_sensitive,
    _tokens,
    EXPRESSIONS,
    POSES,
    CAMERA,
    ANGLE,
    QUALITY,
    NEGATIVE,
    EYES_CLOSED_NEGATIVE,
    LOOK_AT_VIEWER_NEGATIVE,
    WEIGHTED,
    MARGIN_TAGS,
    MARGIN_NATURAL,
    FRAMING,
    NATURAL_SUFFIX,
    WORD_BUDGET,
)


# ==============================================================================
# 1. Target Generative Model Architecture
# ==============================================================================

class TargetModel(str, Enum):
    """Target generative model architecture for prompt compilation dispatch."""
    QWEN_IMAGE_21 = "qwen_image_21"  # Central ArtEngine text-to-image (Qwen Image 2.1 Turbo)
    MINIMAX_H3 = "minimax_h3"        # ChronoFlow / video motion model (MiniMax Fast H3 Turbo)
    SDXL = "sdxl"                    # Legacy SDXL tag/Danbooru workflow (ControlNet / IP-Adapter substrate)


# ==============================================================================
# 2. Four-Tier Invariant Visual Styling Anchor Schema
# ==============================================================================

class StyleAnchor(BaseModel):
    """4-tier immutable visual styling anchor locking visual consistency across sequential panels.

    Formula: Visual Style Anchor = Medium (Tier 1) + Line Geometry (Tier 2) + Palette (Tier 3) + Lighting Physics (Tier 4).
    Must remain strictly invariant across all panels within a story sequence.
    """
    genre: str = Field(description="Canonical genre key matching engine/original/genres.py")
    medium: str = Field(description="Tier 1: Material substrate, rendering engine simulation, and physical finish")
    line_geometry: str = Field(description="Tier 2: Stroke weight, contour continuity, and edge rendering physics")
    palette: str = Field(description="Tier 3: Chromatic harmony, saturation gamut, and tonal contrast ratio")
    lighting_physics: str = Field(description="Tier 4: Photon mechanics, directionality, specular highlights, and shadow geometry")
    negative_prompt: str = Field(description="Standard negative suppression tokens eliminating medium leakage and artifacts")
    review_witness_rule: str = Field(default="", description="Review Witness B verification criteria for quality audit gate")

    def to_natural_prose(self) -> str:
        """Combine the 4 tiers into a dense, cohesive natural prose styling paragraph."""
        parts = [
            self.medium.rstrip("."),
            self.line_geometry.rstrip("."),
            self.palette.rstrip("."),
            self.lighting_physics.rstrip("."),
        ]
        return ". ".join(p for p in parts if p) + "."

    def to_tags(self) -> list[str]:
        """Convert style anchor into tag tokens for legacy SDXL workflows."""
        tokens: list[str] = []
        for text in (self.medium, self.line_geometry, self.palette, self.lighting_physics):
            tokens.extend([t.strip() for t in text.split(",") if t.strip()])
        return tokens


# ==============================================================================
# 3. Master Genre Visual Style Presets (from Practitioner Guide Section 4)
# ==============================================================================

GENRE_STYLE_PRESETS: dict[str, StyleAnchor] = {
    "bedtime": StyleAnchor(
        genre="bedtime",
        medium="Hand-drawn 2D anime illustration, gentle storybook animation still, soft matte finish, zero 3D CGI, zero photographic textures",
        line_geometry="Clean, soft dark brown ink outlines, smooth uniform contours, gentle stroke weight",
        palette="Warm pastel palette, soft cream and amber tones, muted lavender shadows, gentle low contrast",
        lighting_physics="Diffused warm lamp light, soft golden ambient glow, even gentle illumination, soft-edged shadows",
        negative_prompt="lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, dark, gritty, scary, harsh shadows, 3d render, cgi, photorealistic skin, high contrast, oversaturated neon, violence, weapons",
        review_witness_rule="Witness B must confirm gentle storybook anime tone; flags failure on dark/gritty aesthetics, harsh shadows, or 3D rendering.",
    ),
    "horror": StyleAnchor(
        genre="horror",
        medium="Atmospheric 2D cinematic horror anime illustration, fine filmic grain texture, vintage cel aesthetic",
        line_geometry="Razor-sharp, thin black ink contours, high-precision dark outlines, stark silhouette definition",
        palette="Desaturated cool muted palette, slate blues, sickly moss greens, deep charcoal blacks, pale skin tones",
        lighting_physics="Noir chiaroscuro lighting, deep cast shadows, harsh single directional beam, eerie volumetric fog, high contrast",
        negative_prompt="lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, bright, vibrant, pastel, cheerful, colorful, 3d render, cgi, flat lighting, gore, bloody, dismemberment, mutilated",
        review_witness_rule="Witness B confirms unsettling noir atmosphere; verifies absence of forbidden overt gore (GORE filter) and cheerful lighting.",
    ),
    "mystery": StyleAnchor(
        genre="mystery",
        medium="Detective noir anime style, atmospheric 2D graphic illustration, matte paper finish",
        line_geometry="Crisp bold ink outlines, defined silhouette contours, clean architectural line weight",
        palette="Muted vintage palette, rich sepia and charcoal tones, deep umber accents, restrained amber highlights",
        lighting_physics="High-contrast dramatic side-lighting, Venetian blind shadow patterns, atmospheric dim lantern lighting",
        negative_prompt="lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, colorful, neon, flat lighting, 3d render, cgi, bright cheerful colors, oversaturated, photorealistic",
        review_witness_rule="Witness B confirms detective noir aesthetic and shadow patterns; verifies planted clue visibility.",
    ),
    "fantasy": StyleAnchor(
        genre="fantasy",
        medium="Epic fantasy anime feature film animation still, rich 2D anime rendering, vivid matte finish",
        line_geometry="Fine detailed ink outlines, clean elegant line art, defined dynamic contours",
        palette="Vivid saturated jewel tones, lapis lazuli blues, emerald greens, gold leaf highlights, rich contrast",
        lighting_physics="Dramatic cinematic golden hour temple sunlight, magical soft rim lighting, bioluminescent accents, ambient occlusion",
        negative_prompt="lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, washed out, dull, flat lighting, 3d render, cgi, photorealistic skin, modern clothing, modern buildings",
        review_witness_rule="Witness B confirms epic fantasy animation aesthetic; checks vibrant jewel-toned palette and magical atmospheric lighting.",
    ),
    "mythology": StyleAnchor(
        genre="mythology",
        medium="Authentic Indian historical cinema, 35mm Arri Alexa cinematography, naturalistic film still, documentary realism",
        line_geometry="Naturalistic photographic edge transitions, zero graphic ink outlines, natural physical edge falloff",
        palette="Culturally authentic Indian heritage palette, warm turmeric gold, sacred vermilion, raw cotton ivory, deep bronze",
        lighting_physics="Warm golden hour temple sunlight, brass diya oil lamp directional amber glow, floating dust motes, soft directional falloff",
        negative_prompt="lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, western comic, 2d cartoon, anime, 3d render, cgi, modern clothing, plastic skin, neon lighting, flat lighting",
        review_witness_rule="Witness B confirms authentic Indian historical cinematography, natural skin textures, sacred attire (dhoti, zari, rudraksha), and absence of cartoonish lines.",
    ),
    "vox": StyleAnchor(
        genre="vox",
        medium="Signature Vox 2D motion explainer style, modern flat vector graphic illustration, high-end YouTube visual journalism",
        line_geometry="Crisp bold dark outlines, geometric precision, uniform stroke weight, clean vector paths",
        palette="Solid vibrant color palette, bright canary yellow accents, deep navy background, stark graphic contrasts",
        lighting_physics="Minimalist flat clean cel shading, graphic studio illumination, zero cast shadows, zero photographic gradients",
        negative_prompt="lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, photographic textures, 3d render, cgi, gradients, painterly, realistic skin, sketchy lines, soft brushstrokes",
        review_witness_rule="Witness B confirms 2D flat vector motion explainer aesthetic; strictly rejects photographic textures, 3D CGI, and painterly gradients.",
    ),
}


# ==============================================================================
# 4. Character Identity Token & The Unnaming Protocol Schema
# ==============================================================================

NATURAL_PERSON_LOOKUP: dict[tuple[str, str], str] = {
    ("child", "male"): "a little boy",
    ("child", "female"): "a little girl",
    ("child", "neutral"): "a child",
    ("teen", "male"): "a teenage boy",
    ("teen", "female"): "a teenage girl",
    ("teen", "neutral"): "a teenager",
    ("adult", "male"): "an adult man",
    ("adult", "female"): "an adult woman",
    ("adult", "neutral"): "an adult",
    ("elder", "male"): "an old man with a wrinkled face",
    ("elder", "female"): "an old woman with a wrinkled face",
    ("elder", "neutral"): "an elderly person",
}

CLOTHING_KEYWORDS: tuple[str, ...] = (
    "coat", "boots", "dress", "shirt", "pants", "trousers", "armor", "robe",
    "tunic", "scarf", "hat", "jacket", "cape", "costume", "shoes", "gloves",
    "skirt", "hood", "cloak", "sweater", "vest", "sandals", "helmet", "uniform",
)

POSE_SENSITIVE_WORDS: tuple[str, ...] = (
    "closed", "asleep", "sleeping", "from behind", "facing away", "turned away",
    "looking up", "looking down", "looking back", "curled", "lying", "hiding", "peeking",
)


class CharacterIdentityToken(BaseModel):
    """Character identity preservation token strictly separating immutable anatomy from mutable situational states.

    Enforces the Unnaming Protocol: proper names are sanitized to descriptive role noun phrases
    to prevent semantic literalism defects (DEF-ID-002).
    """
    id: str = Field(description="Short character slug identifier, e.g. 'mira'")
    name: str = Field(description="Character proper name, sanitized during prompt assembly")
    role: str = Field(default="protagonist", description="Narrative role: protagonist | companion | antagonist | mentor | other")
    species: str = Field(default="human", description="Species: 'human' or creature description")
    gender: str = Field(default="neutral", description="male | female | neutral")
    age_group: str = Field(default="child", description="child | teen | adult | elder")
    immutable_features: str = Field(description="Permanent anatomical anchors: facial structure, jawline, eye shape/color, hair style/color, skin tone")
    mutable_features: str = Field(default="", description="Situational attire, clothing, accessories, or temporary state")
    pose: str = Field(default="", description="Physical body posture or stance")
    expression: str = Field(default="", description="Facial expression, emotional state, eyelid/gaze position")
    action: str = Field(default="", description="Dynamic physical action or interaction")
    screen_position: str = Field(default="center", description="Spatial coordinate position: left | center | right")
    pose_sensitive: bool = Field(default=False, description="Flag indicating closed eyes, sleeping, or rear-facing view requiring portrait attenuation")
    unnamed_role: str = Field(default="", description="Resolved role noun phrase, e.g. 'a little girl', 'the teenage boy', 'the cat'")

    @property
    def is_human(self) -> bool:
        return self.species.strip().lower() == "human"

    def resolve_unnamed_role(self) -> str:
        """Resolve role noun phrase based on age_group, gender, and species."""
        if not self.is_human:
            clean = self.species.strip()
            return clean if clean.startswith(("a ", "an ", "the ")) else f"a {clean}"
        return NATURAL_PERSON_LOOKUP.get((self.age_group.lower(), self.gender.lower()), "a person")

    def to_natural_description(self, include_action: bool = True) -> str:
        """Assemble natural prose description combining unnamed role, immutable anatomy, wardrobe, and action."""
        role = self.unnamed_role or self.resolve_unnamed_role()
        features = [self.immutable_features]
        if self.mutable_features:
            wear = self.mutable_features if self.mutable_features.startswith(("wearing", "in ")) else f"wearing {self.mutable_features}"
            features.append(wear)

        feature_str = ", ".join(f for f in features if f)
        base = f"{role} with {feature_str}" if feature_str else role

        if not include_action:
            return base

        actions = [a for a in (self.pose, self.expression, self.action) if a]
        if actions:
            action_str = ", ".join(actions)
            return f"{base}, {action_str}"
        return base

    @classmethod
    def from_character(cls, char: Character, char_pose: CharPose | None = None) -> CharacterIdentityToken:
        """Factory constructor converting domain Character and optional CharPose into CharacterIdentityToken."""
        look_parts = [p.strip() for p in char.look.split(",") if p.strip()]
        immutable_parts: list[str] = []
        mutable_parts: list[str] = []

        for part in look_parts:
            low = part.lower()
            if any(cw in low for cw in CLOTHING_KEYWORDS):
                mutable_parts.append(part)
            else:
                immutable_parts.append(part)

        immutable_str = ", ".join(immutable_parts) if immutable_parts else char.look
        mutable_str = ", ".join(mutable_parts)

        pose_val = char_pose.pose if char_pose else ""
        expr_val = char_pose.expression if char_pose else ""
        act_val = char_pose.action if char_pose else ""
        side_val = char_pose.side if char_pose else "center"

        all_text = f"{pose_val} {expr_val} {act_val}".lower()
        is_sensitive = any(w in all_text for w in POSE_SENSITIVE_WORDS)

        token = cls(
            id=char.id,
            name=char.name,
            role=char.role,
            species=char.species,
            gender=char.gender,
            age_group=char.age_group,
            immutable_features=immutable_str,
            mutable_features=mutable_str,
            pose=pose_val,
            expression=expr_val,
            action=act_val,
            screen_position=side_val,
            pose_sensitive=is_sensitive,
        )
        token.unnamed_role = token.resolve_unnamed_role()
        return token


# ==============================================================================
# 5. Camera Optics & Framing Directive Schema
# ==============================================================================

class CameraOptics(BaseModel):
    """Directorial camera parameters governing framing, focal mechanics, and boundary clearance."""
    shot: str = Field(default="medium", description="Shot framing code: extreme_close | close | medium | cowboy | full | full_body | wide | extreme_wide | turnaround")
    camera_angle: str = Field(default="eye_level", description="Vertical perspective: eye_level | low | high | dutch")
    lens_type: str = Field(default="standard", description="Optical lens type: macro | 35mm_prime | 50mm_standard | 85mm_portrait | 24mm_wide | anamorphic")
    depth_of_field: str = Field(default="medium", description="Focal plane depth: shallow_bokeh | medium | deep_focus")
    headroom_margin: float = Field(default=0.15, description="Clearance margin percentage above crown of head (minimum 0.15 for portraits/medium)")
    focal_lock: str = Field(default="subject", description="Focal target: irises | face | full_figure | environment")

    def to_framing_directive(self) -> str:
        """Emit concrete physical framing and headroom directive matching shot classification."""
        s = self.shot.lower().replace("-", "_").replace(" ", "_")
        pct = int(self.headroom_margin * 100)
        if s in ("extreme_close",):
            return "Extreme close-up macro framing focusing tightly on the face and eyes, perfectly centered facial composition."
        elif s in ("close",):
            return f"Centered framing focusing on the face and shoulders, with generous headroom above the hair ({pct}% clearance above crown), subject completely within frame, zero top cropping."
        elif s in ("medium", "cowboy"):
            return f"Medium shot from the waist up with generous headroom above the hair ({pct}% clearance above crown), subject completely in frame with zero top cropping."
        elif s in ("full", "full_body"):
            return "Full body shot from head to toe with visible feet resting flat on the ground plane, generous empty margins on all four sides, subject completely in frame with zero edge cropping."
        elif s in ("wide", "extreme_wide", "landscape"):
            return "Wide shot showing the whole scene and the surroundings, spacious empty room with characters fully in frame."
        elif s in ("turnaround", "turnaround_sheet"):
            return "Full length standing character reference from head to toe, four sequential orthographic views (front, three-quarter, profile side, back), unobstructed A-pose, clear limb separation, wide empty margins around all views."
        return f"{s.replace('_', ' ').capitalize()} shot, subject centered with generous headroom."


# ==============================================================================
# 6. Lighting Physics Schema
# ==============================================================================

class LightingPhysics(BaseModel):
    """Concrete photon mechanics, directionality, and shadow geometry."""
    primary_source: str = Field(default="natural_ambient", description="Primary emitter: natural_ambient | golden_hour_sunlight | lantern_glow | moonlight | studio_diffused | candle | neon")
    direction: str = Field(default="top_left", description="Key light trajectory: top_left | top_right | side | rim | overhead | diffused | front")
    color_temperature: str = Field(default="5500K daylight", description="Color temperature & ambient tone: e.g. '3000K warm amber', '5500K daylight', '6500K overcast'")
    shadow_falloff: str = Field(default="soft_contact", description="Shadow geometry: soft_contact | sharp_directional | chiaroscuro | ambient_occlusion | zero_harsh_shadows")
    ambient_bounce: str = Field(default="gentle ambient fill", description="Secondary fill light and bounce mechanics")
    specular_intensity: str = Field(default="natural matte", description="Surface reflectance: natural matte | gentle warm highlights | zero plastic sheen")

    def to_lighting_directive(self) -> str:
        """Emit physical photon mechanics directive."""
        parts: list[str] = []
        if self.primary_source:
            parts.append(f"{self.primary_source.replace('_', ' ')} illumination")
        if self.direction:
            parts.append(f"from {self.direction.replace('_', ' ')}")
        if self.color_temperature:
            parts.append(f"featuring {self.color_temperature}")
        if self.shadow_falloff:
            parts.append(f"with {self.shadow_falloff.replace('_', ' ')} shadows")
        if self.specular_intensity:
            parts.append(self.specular_intensity)
        return ", ".join(parts) + "." if parts else "Soft natural ambient lighting."


# ==============================================================================
# 7. Composition & Defect Guardrails Schema
# ==============================================================================

class CompositionGuardrails(BaseModel):
    """Directorial composition, margin clearance, and anatomical defect prevention guardrails."""
    shot: str = Field(default="medium")
    camera: str = Field(default="eye_level")
    framing_directive: str = Field(default="", description="Safe action zone & canvas boundary instructions")
    margin_directive: str = Field(default="", description="Top headroom and bottom floor clearance instructions")
    kinematic_bindings: list[str] = Field(default_factory=list, description="360-degree finger grasp and physical contact directives")
    object_grounding_directives: list[str] = Field(default_factory=list, description="Surface contact shadows and gravity support directives")
    hand_anatomy_guard: str = Field(
        default="Hands rendered with natural human anatomy, exactly five distinct separated fingers including thumb on each hand, clear articulated knuckles and joints, anatomically correct wrist connection, zero extra digits, zero fused fingers.",
        description="Invariant digit count and joint topology anchor",
    )
    spatial_partitioning_directive: str = Field(
        default="",
        description="Horizontal coordinate partitioning when 2 or more characters are in frame",
    )
    anti_clipping_guard: str = Field(
        default="Subject completely within frame, upper canvas boundary positioned at least 15% above the crown of the head, zero top clipping, zero edge truncation.",
        description="Headroom and boundary clearance guard",
    )

    def to_guardrail_prose(self) -> str:
        """Assemble all active composition guardrails into natural language prose."""
        parts: list[str] = []
        if self.framing_directive:
            parts.append(self.framing_directive.rstrip("."))
        if self.margin_directive:
            parts.append(self.margin_directive.rstrip("."))
        if self.kinematic_bindings:
            parts.append(f"Physical contact: {'; '.join(self.kinematic_bindings)}")
        if self.object_grounding_directives:
            parts.append(f"Object grounding: {'; '.join(self.object_grounding_directives)}")
        if self.spatial_partitioning_directive:
            parts.append(self.spatial_partitioning_directive.rstrip("."))
        if self.hand_anatomy_guard:
            parts.append(self.hand_anatomy_guard.rstrip("."))
        return ". ".join(p for p in parts if p) + "." if parts else ""


# ==============================================================================
# 8. Complete Directorial Prompt Specification Contract
# ==============================================================================

class DirectorialPromptSpec(BaseModel):
    """Complete tool-agnostic directorial prompt specification bridging story beats to target models."""
    target_engine: TargetModel = Field(default=TargetModel.QWEN_IMAGE_21, description="Target model architecture for compilation")
    scene_id: str = Field(default="", description="Scene identifier")
    panel_id: str = Field(default="", description="Panel identifier")
    dimensions: tuple[int, int] = Field(default=(1024, 1024), description="Pixel resolution bucket (width, height)")
    genre_key: str = Field(default="bedtime", description="Narrative genre key")
    camera: CameraOptics = Field(default_factory=CameraOptics)
    lighting: LightingPhysics = Field(default_factory=LightingPhysics)
    composition: CompositionGuardrails | None = Field(default=None)
    characters: list[CharacterIdentityToken] = Field(default_factory=list, description="Characters appearing on screen")
    environment: str = Field(default="", description="Setting details, furniture, props, time, weather")
    key_visuals: list[str] = Field(default_factory=list, description="Narrative claims and objects that must be visible")
    emphasis: list[str] = Field(default_factory=list, description="Tokens requiring elevated weighting from prior failed review")
    motion_direction: str = Field(default="push_in", description="Video camera trajectory: push_in | pull_out | pan_right | pan_left | tilt_up | orbit | static")
    motion_intensity: str = Field(default="balanced", description="Video motion pacing: subtle | balanced | action")
    fx_tags: str = Field(default="", description="Video visual effects or atmospheric particles")
    defect_prevention_guards: list[str] = Field(default_factory=list, description="List of defect codes to actively suppress (e.g. DEF-ANAT-001)")
    simplify: bool = Field(default=False, description="Whether to simplify the prompt on repeated retry attempts")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary execution context or tracking metadata")

    @classmethod
    def from_shotspec(
        cls,
        story: OriginalStory,
        spec: ShotSpec,
        location_id: str,
        target: TargetModel = TargetModel.QWEN_IMAGE_21,
        emphasis: list[str] | None = None,
        simplify: bool = False,
    ) -> DirectorialPromptSpec:
        """Construct DirectorialPromptSpec from ShotSpec and story context."""
        chars_map = {c.id: c for c in story.bible.characters}
        char_tokens = [
            CharacterIdentityToken.from_character(chars_map[cp.id], cp)
            for cp in spec.characters if cp.id in chars_map
        ][:2]

        if len(char_tokens) == 2:
            char_tokens.sort(key=lambda c: {"left": 0, "center": 1, "right": 2}.get(c.screen_position, 1))

        if getattr(spec, "is_rigging", False) or getattr(spec, "shot", "") in ("turnaround", "turnaround_sheet"):
            dims = (1536, 768)
        else:
            dims = resolve_dimensions(spec.shot, num_characters=len(char_tokens))

        camera = CameraOptics(shot=spec.shot, camera_angle=spec.camera)
        loc = next((l for l in story.bible.locations if l.id == location_id), None)
        env_parts: list[str] = []
        if loc:
            env_parts.append(f"{loc.name}: {loc.look}")
        if spec.setting:
            env_parts.append(spec.setting)

        return cls(
            target_engine=target,
            genre_key=story.bible.premise.genre,
            dimensions=dims,
            camera=camera,
            characters=char_tokens,
            environment=". ".join(env_parts),
            key_visuals=list(spec.key_visuals),
            emphasis=list(emphasis or []),
            simplify=simplify,
        )

    @classmethod
    def from_panel(
        cls,
        story: OriginalStory,
        panel: Panel,
        target: TargetModel = TargetModel.QWEN_IMAGE_21,
        emphasis: list[str] | None = None,
        attempt: int = 1,
    ) -> DirectorialPromptSpec:
        """Construct DirectorialPromptSpec from Panel data model."""
        if panel.director:
            spec = ShotSpec(**panel.director)
            emph = emphasis if emphasis is not None else panel.director.get("emphasis")
            return cls.from_shotspec(
                story, spec, panel.location_id, target=target,
                emphasis=emph, simplify=attempt >= 2,
            )
        chars_map = {c.id: c for c in story.bible.characters}
        char_tokens = [
            CharacterIdentityToken.from_character(chars_map[cid])
            for cid in panel.character_ids if cid in chars_map
        ][:2]
        dims = resolve_dimensions(panel.shot, num_characters=len(char_tokens))
        camera = CameraOptics(shot=panel.shot, camera_angle=panel.angle)
        loc = next((l for l in story.bible.locations if l.id == panel.location_id), None)
        env_text = loc.look if loc else ""

        return cls(
            target_engine=target,
            scene_id=panel.scene_id,
            panel_id=panel.id,
            genre_key=story.bible.premise.genre,
            dimensions=dims,
            camera=camera,
            characters=char_tokens,
            environment=env_text,
            key_visuals=list(panel.key_visuals),
            emphasis=list(emphasis or []),
            simplify=attempt >= 2,
        )


# ==============================================================================
# 9. Compiled Prompt Output Contract
# ==============================================================================

class CompiledPrompt(BaseModel):
    """Fully assembled, model-specific compiled prompt output ready for inference.

    Supports tuple unpacking:
        pos, neg = compiled
    and sequence indexing:
        pos = compiled[0]
        neg = compiled[1]
    as well as object attributes:
        compiled.positive, compiled.negative, compiled.dimensions, compiled.target_model
    """
    positive: str = Field(description="Sanitized, structured positive prompt")
    negative: str = Field(default="", description="Model-specific negative suppression prompt")
    target_model: TargetModel = Field(default=TargetModel.QWEN_IMAGE_21, description="Target model enum")
    dimensions: tuple[int, int] = Field(default=(1344, 768), description="Resolved resolution bucket (width, height)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Diagnostic compilation metadata")

    def __iter__(self):
        """Allow seamless unpacking as a (positive, negative) tuple."""
        yield self.positive
        yield self.negative

    def __getitem__(self, index: int) -> str:
        """Allow index access: compiled[0] -> positive, compiled[1] -> negative."""
        if index == 0:
            return self.positive
        elif index == 1:
            return self.negative
        raise IndexError(f"CompiledPrompt index out of range: {index}")

    def __len__(self) -> int:
        return 2

    def as_tuple(self) -> tuple[str, str]:
        """Explicit 2-tuple export for legacy runner signatures."""
        return self.positive, self.negative


# ==============================================================================
# 10. Directorial Reference Constants & Defect Suppression Dictionaries
# ==============================================================================

UNIVERSAL_NEGATIVE_PROMPT: str = (
    "lowres, bad anatomy, bad hands, extra digits, missing fingers, fused fingers, "
    "six fingers, polydactyly, syndactyly, deformed digits, mutated hands, broken wrists, "
    "extra limbs, polycephaly, duplicate heads, floating object, disconnected grip, "
    "cropped head, cut off feet, blurry, text, watermark, 3d render, cgi, photorealistic skin"
)

QWEN_IMAGE_21_BASE_NEGATIVE: str = (
    "bad anatomy, deformed hands, fused fingers, extra fingers, missing fingers, malformed digits, "
    "mutated hands, broken wrists, extra limbs, bad proportions, grotesque face, distorted eyes, "
    "polycephaly, duplicate heads, floating objects, disconnected grip, cropped head, cut off feet, "
    "blurry, lowres, text, watermark, signature, speech bubbles, 3d render, cgi, photorealistic skin"
)

UNIVERSAL_VIDEO_NEGATIVE_PROMPT: str = (
    "fast jerky motion, abrupt camera jump cut, morphing face, distorted hands, "
    "flickering, twitching, text, watermark, bad anatomy, jittery artifacts, "
    "melted face, blurry facial features, faceless pedestrians, temporal tearing, "
    "frame stutter, rapid zoom, disfigured limbs"
)

MINIMAX_H3_NEGATIVE: str = UNIVERSAL_VIDEO_NEGATIVE_PROMPT

RIGGING_NEGATIVE: str = (
    "occluded limbs, overlapping appendages, crossed limbs, hands in pockets, foreshortening, "
    "dramatic perspective, dynamic pose, action pose, motion blur, tilted head, bent posture, "
    "dramatic shadows, harsh directional light, deep cast shadows, complex background, "
    "background clutter, scenery, props, furniture, merged limbs, connected limbs, fused fingers, "
    "hidden hands, blurred joints, floating objects, disconnected hands, lowres, bad anatomy, "
    "bad hands, extra digits, missing fingers, text, watermark, signature"
)

RIGGING_NEGATIVE_PROMPT: str = RIGGING_NEGATIVE

CAMERA_KINEMATICS: dict[str, str] = {
    "push_in": "Slow cinematic camera push in towards the subject, smooth steady optical track",
    "pull_out": "Smooth slow camera pull back revealing the surroundings, steady fluid optical track",
    "pan_right": "Gentle camera pan from left to right across the scene, smooth mechanical track",
    "pan_left": "Gentle camera pan from right to left across the scene, smooth mechanical track",
    "tilt_up": "Slow camera tilt upwards, steady vertical tracking",
    "orbit": "Slow subtle camera orbit around the focal point, steady rotational speed",
    "static": "Static camera framing, subtle ambient motion, locked-off tripod shot",
}

MOTION_PACING: dict[str, str] = {
    "subtle": "slow subtle gentle motion, calm and delicate pace",
    "action": "dynamic energetic movement, strong visual momentum, high impact anime motion",
    "balanced": "measured cinematic pace, natural rhythm",
}

VIDEO_SECONDARY_DYNAMICS: str = "natural subtle movement, cloth and hair dynamics"

VIDEO_TEMPORAL_INVARIANCE: str = (
    "cinematic lighting, steady frame rate, consistent character appearance across all frames, "
    "24fps smooth motion"
)

VIDEO_BOKEH_DIRECTIVE: str = (
    "shallow depth of field, sharp foreground character, soft background bokeh"
)

INPAINT_CORRECTION_PROMPTS: dict[str, dict[str, Any]] = {
    "polycephaly": {
        "positive": "single head, symmetrical face, natural neck, serene anime face, perfect head proportions",
        "negative": "multiple heads, two faces, duplicate head, fused heads, conjoined head, deformed face",
        "bbox": [0.15, 0.05, 0.85, 0.45],
    },
    "extra_limbs": {
        "positive": "correct number of limbs, natural anatomical arms and legs, proper proportions, anatomically correct body",
        "negative": "extra limbs, extra arms, extra legs, mutated appendages, duplicate limbs, three arms, four arms",
        "bbox": [0.10, 0.25, 0.90, 0.90],
    },
    "missing_limbs": {
        "positive": "complete body structure, intact limbs, natural anatomy, fully rendered arms and legs",
        "negative": "missing limbs, amputated, severed limbs, truncated limbs, missing arms",
        "bbox": [0.10, 0.25, 0.90, 0.90],
    },
    "distorted_digits": {
        "positive": "detailed anatomical hand, five fingers, correct digits, natural hand pose, well-defined fingers, perfect anatomy",
        "negative": "bad anatomy, extra digits, missing fingers, fused fingers, distorted hand, polydactyly, syndactyly, deformed digits, six fingers",
        "bbox": [0.25, 0.25, 0.75, 0.75],
    },
    "limb_topology": {
        "positive": "natural limb topology, natural bending angles, plausible skeletal joints, correct anatomy",
        "negative": "bent backwards, impossible joints, twisted limbs, broken bones, unnatural angles, inverted joints",
        "bbox": [0.15, 0.30, 0.85, 0.85],
    },
    "unanchored_object": {
        "positive": "grounded object resting firmly on surface, contact shadow, stable placement, realistic physics",
        "negative": "floating object, hovering in air, unanchored object, levitating, suspended in mid-air",
        "bbox": [0.20, 0.35, 0.80, 0.85],
    },
    "disconnected_interaction": {
        "positive": "firmly gripping object, fingers wrapped around handle, direct physical contact, continuous grasp, zero gap",
        "negative": "disconnected grip, hovering near hand, floating object, detached, gap between hand and object, not touching",
        "bbox": [0.15, 0.35, 0.85, 0.85],
    },
}


# ==============================================================================
# 11. Helper: Video Dimension Resolution (Divisible by 32)
# ==============================================================================

def resolve_video_dimensions(
    spec: Any = None,
    dimensions: tuple[int, int] | None = None,
    default: tuple[int, int] = (1344, 768),
) -> tuple[int, int]:
    """Resolve dimensions strictly aligned to multiples of 32 for MiniMax H3 Turbo.

    Default video output is 16:9 widescreen (1344x768). Any custom dimension is snapped
    to the nearest multiple of 32 (minimum 32).
    """
    if dimensions:
        w, h = dimensions
    elif spec and hasattr(spec, "dimensions") and spec.dimensions:
        w, h = spec.dimensions
    else:
        w, h = default

    w_32 = max(32, int(round(w / 32.0)) * 32)
    h_32 = max(32, int(round(h / 32.0)) * 32)
    return (w_32, h_32)


# ==============================================================================
# 12. Prompt Compiler Implementation
# ==============================================================================

class PromptCompiler:
    """Centralized compiler producing model-tailored positive and negative prompts."""

    @classmethod
    def compile_image_prompt(
        cls,
        story: OriginalStory,
        spec: ShotSpec,
        location_id: str,
        target: TargetModel | str = TargetModel.QWEN_IMAGE_21,
        emphasis: list[str] | None = None,
        simplify: bool = False,
        dims: tuple[int, int] | None = None,
        fallback_action: str = "",
        extra_negative: str = "",
    ) -> CompiledPrompt:
        """Compile a ShotSpec into a target-appropriate image prompt.

        For Qwen Image 2.1 (TargetModel.QWEN_IMAGE_21):
            Assembles the canonical 7-tier natural language hierarchy:
              Tier 1: Visual Style & Medium Anchor
              Tier 2: Camera Optics, Shot Framing & Margin Directive (MARGIN_NATURAL)
              Tier 3: Spatially Partitioned Unnamed Characters (unname, immutable look, pose, expression)
              Tier 4: Action Dynamics & Kinematic Contact Bindings (compile_interaction_bindings_natural)
              Tier 5: Environment Setting & Lighting Physics
              Tier 6: Key Visual Requirements (spec.key_visuals)
              Tier 7: Technical Invariant Suffix
            Emits focused defect suppression negative prompt for Qwen Image 2.1.
            If target is 'flux' or 'natural', emits an empty negative prompt.
            If target is TargetModel.SDXL, delegates to compile_sdxl_tag_prompt.

        When simplify=True (attempt >= 2 fallback):
            Focuses on missing visuals: places emphasis clause first, omits
            kinematic and margin decorations, strips extraneous lighting/setting details.
        """
        target_str = str(target.value if isinstance(target, TargetModel) else target).lower().strip()
        if target_str in ("sdxl", "tags", TargetModel.SDXL.value):
            return cls.compile_sdxl_tag_prompt(
                story=story,
                spec=spec,
                location_id=location_id,
                emphasis=emphasis,
                fallback_action=fallback_action,
                dims=dims,
                extra_negative=extra_negative,
            )

        genre_key = story.bible.premise.genre
        genre_obj = GENRES.get(genre_key)
        preset = GENRE_STYLE_PRESETS.get(genre_key)

        chars = {c.id: c for c in story.bible.characters}
        shown = [c for c in spec.characters if c.id in chars][:2]
        if len(shown) == 2:
            shown.sort(key=lambda c: {"left": 0, "center": 1, "right": 2}.get(c.side, 1))

        # Dynamic dimension resolution (1-Megapixel aligned)
        if dims is None:
            if getattr(spec, "is_rigging", False) or getattr(spec, "shot", "") in ("turnaround", "turnaround_sheet"):
                dims = (1536, 768)
            else:
                dims = resolve_dimensions(spec.shot, num_characters=len(shown))

        un = lambda t: unname(t, story.bible.characters) if t else ""
        un_emphasis = [un(e) for e in emphasis] if emphasis else []
        un_key_visuals = [un(k) for k in spec.key_visuals] if spec.key_visuals else []
        loc = next((x for x in story.bible.locations if x.id == location_id), None)
        is_rigging = getattr(spec, "is_rigging", False) or spec.shot in ("turnaround", "turnaround_sheet")

        parts: list[str] = []

        # ----------------------------------------------------------------------
        # A. Fallback / Simplify Mode (attempt >= 2)
        # ----------------------------------------------------------------------
        if simplify:
            if un_emphasis:
                parts.append(f"Most important: the picture must clearly show {'; '.join(un_emphasis)}.")

            style_tag = next((t.strip() for t in genre_obj.art_style.split(",") if "style" in t), "anime illustration") if genre_obj else "anime illustration"
            parts.append(f"{style_tag[:1].upper() + style_tag[1:]}.")
            framing = FRAMING.get(spec.shot, "")
            if framing:
                parts.append(framing)

            if not shown:
                parts.append("There are no people in the picture.")
            for k, c in enumerate(shown):
                where = "" if len(shown) == 1 else ("On the left: " if k == 0 else "On the right: ")
                ch = chars[c.id]
                doing = un(", ".join(x for x in (c.pose, c.expression, c.action) if x))
                parts.append(f"{where}{describe_character(ch)}. {doing[:1].upper() + doing[1:]}." if doing else f"{where}{describe_character(ch)}.")

            # Simplified setting
            loc_str = (loc.name + ": " + ", ".join(_tokens(loc.look, 5))) if loc else ""
            simp_setting = spec.setting.split(".")[0][:80] if spec.setting else ""
            place = ". ".join(x for x in (loc_str, simp_setting) if x)
            if place:
                parts.append(f"Setting: {place}.")

            need = list(dict.fromkeys(un_key_visuals + un_emphasis))
            if need:
                parts.append("The picture must clearly show: " + "; ".join(need) + ".")
            if un_emphasis:
                parts.append("Pay special attention to: " + "; ".join(un_emphasis) + ".")
            if any(k in " ".join(un_key_visuals).lower() for k in ("eyes closed", "closed eyes")):
                parts.append("Her/his eyes are closed.")

            parts.append(f"Style: {', '.join(_tokens(genre_obj.art_style))}. {NATURAL_SUFFIX}" if genre_obj else NATURAL_SUFFIX)

        # ----------------------------------------------------------------------
        # B. Authoritative 7-Tier Natural Language Hierarchy
        # ----------------------------------------------------------------------
        else:
            # Tier 1: Visual Style & Medium Anchor
            style_tag = next((t.strip() for t in genre_obj.art_style.split(",") if "style" in t), "") if genre_obj else ""
            if preset:
                if style_tag and not preset.medium.lower().startswith(style_tag.lower()):
                    t1 = f"{style_tag[:1].upper() + style_tag[1:]}. {preset.medium}. {preset.line_geometry}."
                else:
                    t1 = f"{preset.medium}. {preset.line_geometry}."
            else:
                tag_label = style_tag if style_tag else "anime illustration"
                t1 = f"{tag_label[:1].upper() + tag_label[1:]}."
            parts.append(t1)

            # Tier 2: Camera Optics, Shot Framing & Margin Directive
            framing_str = FRAMING.get(spec.shot, "")
            if framing_str:
                parts.append(framing_str)

            margin_phrase = MARGIN_NATURAL.get(spec.shot)
            if margin_phrase:
                parts.append(margin_phrase)

            if spec.camera in ("low", "high"):
                angle_desc = {"low": "Shot from a low camera angle looking up.", "high": "Shot from a high camera angle looking down."}.get(spec.camera)
                if angle_desc:
                    parts.append(angle_desc)

            if spec.shot in ("close", "medium", "cowboy"):
                parts.append("Character head and face fully in frame with generous headroom above the hair, no cropping at top.")

            # Tier 3: Spatially Partitioned Unnamed Characters
            if not shown:
                parts.append("There are no people in the picture.")
            else:
                for k, c in enumerate(shown):
                    where = "" if len(shown) == 1 else ("On the left: " if k == 0 else "On the right: ")
                    ch = chars[c.id]
                    doing = un(", ".join(x for x in (c.pose, c.expression, c.action) if x))
                    char_desc = describe_character(ch)
                    if doing:
                        parts.append(f"{where}{char_desc}. {doing[:1].upper() + doing[1:]}.")
                    else:
                        parts.append(f"{where}{char_desc}.")

                if len(shown) == 2:
                    parts.append("Clear horizontal separation between characters, distinct individual identities, zero feature blending.")

                if is_rigging:
                    parts.append("Unobstructed neutral A-pose with arms angled 45 degrees downward away from torso, hands open with fingers spread and clearly separated, visible articulated joints at elbows, wrists, hips, and knees. Clean horizontal alignment across all views, zero overlapping limbs.")

            # Tier 4: Action Dynamics & Kinematic Contact Bindings
            action_texts = [c.action for c in shown if c.action] + [c.pose for c in shown if c.pose] + spec.key_visuals
            binding_phrases = compile_interaction_bindings_natural(action_texts)
            if binding_phrases:
                parts.append(f"Physical contact: {'; '.join(binding_phrases)}.")

            if any(chars[c.id].species == "human" for c in shown if c.id in chars):
                parts.append("Hands drawn with natural human anatomy, exactly five distinct separated fingers, no extra digits.")

            # Tier 5: Environment Setting & Lighting Physics
            loc_str = (loc.name + ": " + ", ".join(_tokens(loc.look, 5))) if loc else ""
            place = ". ".join(x for x in (loc_str, spec.setting) if x)
            if place:
                parts.append(f"Setting: {place}.")

            if spec.lighting or spec.mood:
                parts.append(f"Lighting: {spec.lighting or 'natural'}. Mood: {spec.mood or 'calm'}.")
            elif preset:
                parts.append(f"Palette: {preset.palette}. Lighting: {preset.lighting_physics}.")

            # Tier 6: Key Visual Requirements
            need = list(dict.fromkeys(un_key_visuals + un_emphasis))
            if need:
                parts.append("The picture must clearly show: " + "; ".join(need) + ".")
            if un_emphasis:
                parts.append("Pay special attention to: " + "; ".join(un_emphasis) + ".")

            all_vis_text = " ".join(un_key_visuals + [c.expression for c in shown]).lower()
            if any(k in all_vis_text for k in ("eyes closed", "closed eyes", "asleep", "sleeping")):
                parts.append("Her/his eyes are closed.")

            # Tier 7: Technical Invariant Suffix
            if is_rigging:
                parts.append("Single clean character sheet, no text, no labels, no watermark.")
            else:
                parts.append(f"Style: {', '.join(_tokens(genre_obj.art_style))}. {NATURAL_SUFFIX}" if genre_obj else NATURAL_SUFFIX)

        positive = " ".join(p for p in parts if p)

        # ----------------------------------------------------------------------
        # Target-Appropriate Negative Prompt Generation
        # ----------------------------------------------------------------------
        if target_str in ("natural", "flux"):
            negative = ""
        elif is_rigging:
            negative = RIGGING_NEGATIVE
        else:
            neg_tokens = [t.strip() for t in QWEN_IMAGE_21_BASE_NEGATIVE.split(",") if t.strip()]
            if preset and preset.negative_prompt:
                for pt in preset.negative_prompt.split(","):
                    pt = pt.strip()
                    if pt and pt not in neg_tokens:
                        neg_tokens.append(pt)
            if pose_sensitive(spec):
                vis_and_pose = " ".join([c.pose + " " + c.expression + " " + c.action for c in spec.characters] + spec.key_visuals).lower()
                if any(w in vis_and_pose for w in ("closed", "asleep", "sleeping")):
                    for extra in ("open eyes", "looking at viewer"):
                        if extra not in neg_tokens:
                            neg_tokens.append(extra)
                elif any(w in vis_and_pose for w in ("from behind", "facing away", "turned away", "back to")):
                    if "looking at viewer" not in neg_tokens:
                        neg_tokens.append("looking at viewer")
            negative = ", ".join(neg_tokens)

        if extra_negative and extra_negative.strip():
            negative = f"{negative}, {extra_negative.strip()}" if negative else extra_negative.strip()

        target_enum = TargetModel.QWEN_IMAGE_21
        if isinstance(target, TargetModel):
            target_enum = target
        elif target_str in TargetModel._value2member_map_:
            target_enum = TargetModel(target_str)

        return CompiledPrompt(
            positive=positive,
            negative=negative,
            target_model=target_enum,
            dimensions=dims,
            metadata={
                "shot": spec.shot,
                "camera": spec.camera,
                "genre": genre_key,
                "characters_count": len(shown),
                "simplify": simplify,
            },
        )

    @classmethod
    def compile_sdxl_tag_prompt(
        cls,
        story: OriginalStory,
        spec: ShotSpec,
        location_id: str,
        emphasis: list[str] | None = None,
        fallback_action: str = "",
        dims: tuple[int, int] | None = None,
        extra_negative: str = "",
    ) -> CompiledPrompt:
        """Compile a ShotSpec into Danbooru/SDXL tag-style prompts for legacy and ControlNet pipelines."""
        genre = GENRES[story.bible.premise.genre]
        chars = {c.id: c for c in story.bible.characters}
        loc = next((x for x in story.bible.locations if x.id == location_id), None)
        shown = [c for c in spec.characters if c.id in chars][:2]
        if len(shown) == 2:
            shown.sort(key=lambda c: {"left": 0, "center": 1, "right": 2}.get(c.side, 1))
        emphasis = emphasis or []

        if dims is None:
            if getattr(spec, "is_rigging", False) or getattr(spec, "shot", "") in ("turnaround", "turnaround_sheet"):
                dims = (1536, 768)
            else:
                dims = resolve_dimensions(spec.shot, num_characters=len(shown))

        groups: list[list[str]] = [[{0: "no humans", 1: "solo", 2: "2others"}.get(len(shown), "multiple others")]]
        for c in shown:
            ch = chars[c.id]
            detail = list(dict.fromkeys(
                tags_for(c.expression, EXPRESSIONS)
                + tags_for(c.pose, POSES)
                + tags_for(c.action, POSES)
                + tags_for(c.action, EXPRESSIONS)
            ))
            groups.append(_tokens(person_tags(ch)) + _tokens(ch.look, 6) + detail + [x for x in (c.pose, c.action) if x])

        # Kinematic interaction binding tags
        action_texts = [c.action for c in shown if c.action] + [c.pose for c in shown if c.pose] + spec.key_visuals
        interaction_tags = compile_interaction_bindings_tags(action_texts)
        if interaction_tags:
            groups.append(interaction_tags)

        groups.append([f"({e}:1.4)" for e in emphasis if e not in spec.key_visuals])
        groups.append([f"({k}:1.3)" if k in emphasis else k for k in spec.key_visuals])
        groups.append(_tokens(spec.setting) + _tokens(loc.look, 5 if loc else 0))
        groups.append(light_tags(spec.lighting + " " + spec.mood) + _tokens(spec.lighting) + _tokens(spec.mood))

        margin_tags = MARGIN_TAGS.get(spec.shot, [])
        groups.append([CAMERA.get(spec.shot, ""), ANGLE.get(spec.camera, "")] + margin_tags)

        tokens: list[str] = []
        words = 0
        for group in groups:
            for t in group:
                t = t.strip()
                if not t:
                    continue
                w = f"({t}:1.3)" if t in WEIGHTED and not t.startswith("(") else t
                n = len(t.split())
                if w in tokens or words + n > WORD_BUDGET:
                    continue
                tokens.append(w)
                words += n

        tokens += [t for t in _tokens(genre.art_style) + _tokens(QUALITY) if t not in tokens]

        neg = NEGATIVE
        if any("closed eyes" in t for t in tokens):
            neg += EYES_CLOSED_NEGATIVE
        elif any(t.strip("()").split(":")[0] in ("from behind", "facing away") for t in tokens):
            neg += LOOK_AT_VIEWER_NEGATIVE

        if extra_negative and extra_negative.strip():
            neg = f"{neg}, {extra_negative.strip()}"

        return CompiledPrompt(
            positive=", ".join(tokens),
            negative=neg,
            target_model=TargetModel.SDXL,
            dimensions=dims,
            metadata={
                "shot": spec.shot,
                "camera": spec.camera,
                "genre": story.bible.premise.genre,
                "characters_count": len(shown),
            },
        )

    @classmethod
    def compile_tag_prompt(cls, *args, **kwargs) -> CompiledPrompt:
        """Alias for compile_sdxl_tag_prompt."""
        return cls.compile_sdxl_tag_prompt(*args, **kwargs)

    @classmethod
    def compile_video_prompt(
        cls,
        spec: Any = None,
        target: TargetModel | str = TargetModel.MINIMAX_H3,
        camera_direction: str = "push_in",
        custom_prompt: str = "",
        action_hint: str = "",
        intensity: str = "balanced",
        fx_tags: list[str] | str | None = None,
        style_6_heading: bool = False,
        subject_definitions: str | None = None,
        summary: str | None = None,
        retention_analysis: str | None = None,
        soundscape: str | None = None,
        music: str | None = None,
        bokeh_background: bool = False,
        dimensions: tuple[int, int] | None = None,
        extra_negative: str = "",
    ) -> CompiledPrompt:
        """Compile an Image-to-Video directorial prompt tailored for MiniMax Fast H3 Turbo.

        Adheres strictly to the Kinematic Delta paradigm:
        - Describes camera kinematics, subject motion delta, and secondary dynamics.
        - Avoids redundant static pixel re-description to prevent facial morphing (DEF-VID-001).
        - Snaps output dimensions to nearest multiple of 32 (default: 1344x768).
        - Emits standard temporal anti-morphing negative prompt.
        - Supports both unified motion prose and native 6-heading schema.

        Args:
            spec: ShotSpec or DirectorialPromptSpec containing scene/character context.
            target: TargetModel enum or string identifier (defaults to MINIMAX_H3).
            camera_direction: Standardized key ('push_in', 'pull_out', 'pan_right', 'pan_left', 'tilt_up', 'orbit', 'static').
            custom_prompt: Explicit prompt override for motion actions.
            action_hint: Secondary action hint if custom_prompt is absent.
            intensity: Motion pacing ('subtle', 'balanced', 'action').
            fx_tags: Optical atmosphere or camera fx tags (e.g. 'film_grain', 'vignette').
            style_6_heading: True to compile native 6-heading schema matching chronoflow/pipeline.py.
            subject_definitions: Optional explicit subject_definitions block for 6-heading schema.
            summary: Optional explicit summary block for 6-heading schema.
            retention_analysis: Optional explicit retention_analysis block for 6-heading schema.
            soundscape: Optional diegetic audio soundscape.
            music: Optional non-diegetic musical description.
            bokeh_background: Force shallow depth of field / soft background bokeh.
            dimensions: Optional dimensions tuple (snapped to multiple of 32).
            extra_negative: Additional negative prompt tokens to append.

        Returns:
            CompiledPrompt with positive, negative, target_model, and multiple-of-32 dimensions.
        """
        # 1. Resolve dimensions (multiple of 32)
        dims = resolve_video_dimensions(spec, dimensions=dimensions)

        # 2. Resolve camera kinematics
        if camera_direction == "push_in" and spec and hasattr(spec, "motion_direction") and spec.motion_direction:
            camera_direction = spec.motion_direction
        cam = CAMERA_KINEMATICS.get(camera_direction, CAMERA_KINEMATICS["push_in"])

        # 3. Check for wide shot bokeh requirement
        is_wide = False
        if spec:
            shot_name = getattr(spec, "shot", "")
            cam_obj = getattr(spec, "camera", None)
            cam_shot = getattr(cam_obj, "shot", "") if cam_obj and not isinstance(cam_obj, str) else str(cam_obj or "")
            is_wide = shot_name in ("wide", "extreme_wide") or cam_shot in ("wide", "extreme_wide")
        include_bokeh = is_wide or bokeh_background

        # 4. Resolve motion elements (Kinematic Delta)
        motion_elements: list[str] = []
        if custom_prompt and custom_prompt.strip():
            motion_elements.append(custom_prompt.strip())
        elif action_hint and action_hint.strip():
            motion_elements.append(action_hint.strip())
        elif spec and hasattr(spec, "characters") and spec.characters:
            acts = []
            for ch in spec.characters:
                desc = ", ".join(x for x in (getattr(ch, "action", ""), getattr(ch, "pose", ""), getattr(ch, "expression", "")) if x)
                if desc:
                    acts.append(desc)
            if acts:
                motion_elements.append("character " + "; ".join(acts))
            mood = getattr(spec, "mood", "")
            if mood:
                motion_elements.append(f"{mood} atmosphere")

        # 5. Process FX tags
        fx_parts: list[str] = []
        if fx_tags:
            if isinstance(fx_tags, (list, tuple, set)):
                fx_parts.extend(str(x).strip() for x in fx_tags if str(x).strip())
            elif isinstance(fx_tags, str) and fx_tags.strip():
                fx_parts.append(fx_tags.strip())

        # 6. Branch: Native 6-Heading Schema vs Unified Motion Paragraph
        if style_6_heading:
            # Heading 1: subject_definitions
            if subject_definitions:
                s_defs = subject_definitions.strip()
            elif spec and hasattr(spec, "characters") and spec.characters:
                lines = []
                for i, c in enumerate(spec.characters, 1):
                    c_id = getattr(c, "id", f"c{i}")
                    state = ", ".join(x for x in (getattr(c, "action", ""), getattr(c, "pose", ""), getattr(c, "expression", "")) if x)
                    detail = f": {state}" if state else ""
                    lines.append(f"- Subject {i}: Character ({c_id}){detail}. Facial features and attire locked to reference frame.")
                s_defs = "\n".join(lines)
            else:
                s_defs = "- Subject 1: Primary subject in frame. Visual appearance locked to reference frame."

            # Heading 2: summary
            if summary:
                s_sum = summary.strip()
            else:
                cam_short = cam.split(",")[0]
                act_sum = "; ".join(motion_elements) if motion_elements else "natural movement"
                s_sum = f"The camera performs a {cam_short.lower()} as {act_sum}."

            # Heading 3: retention_analysis
            if retention_analysis:
                s_ret = retention_analysis.strip()
            else:
                s_ret = (
                    "Retain exact facial geometry, hair shape, attire textures, and environment features from the reference image. "
                    "Zero morphing of facial features, zero digit deformities, zero clothing alteration across all frames."
                )

            # Heading 4: detailed_description
            det_lines = [f"camera_movement: {cam}."]
            subject_delta = "; ".join(motion_elements) if motion_elements else "Natural subtle movement"
            det_lines.append(f"subject_description: {subject_delta}, {VIDEO_SECONDARY_DYNAMICS}.")
            env_details = ["steady environmental scene"]
            if include_bokeh:
                env_details.append(VIDEO_BOKEH_DIRECTIVE)
            if fx_parts:
                env_details.extend(fx_parts)
            env_joined = ", ".join(env_details)
            det_lines.append(f"environmental_details: {env_joined}.")
            lighting_and_atmo = getattr(spec, "lighting", "") if spec else ""
            mood = getattr(spec, "mood", "") if spec else ""
            light_atmo_str = f"{lighting_and_atmo} lighting, {mood} atmosphere".strip(", ") if (lighting_and_atmo or mood) else "Consistent cinematic lighting, stable shadows"
            det_lines.append(f"lighting_and_atmosphere: {light_atmo_str}, steady 24fps smooth motion.")
            s_det = "\n".join(det_lines)

            # Heading 5: overall_soundscape
            if soundscape:
                s_snd = soundscape.strip()
            else:
                mood_str = f" {getattr(spec, 'mood', '')}" if (spec and getattr(spec, "mood", "")) else ""
                s_snd = f"Subtle ambient environmental room tone,{mood_str} atmospheric resonance. Zero human speech."

            # Heading 6: non_diegetic_music
            if music:
                s_mus = music.strip()
            else:
                mood_str = f"{getattr(spec, 'mood', '')} " if (spec and getattr(spec, "mood", "")) else "cinematic "
                s_mus = f"Subtle {mood_str}instrumental background score with gentle progression."

            positive_prompt = (
                f"subject_definitions:\n{s_defs}\n\n"
                f"summary:\n{s_sum}\n\n"
                f"retention_analysis:\n{s_ret}\n\n"
                f"detailed_description:\n{s_det}\n\n"
                f"overall_soundscape:\n{s_snd}\n\n"
                f"non_diegetic_music:\n{s_mus}"
            )
        else:
            # Unified Motion Paragraph format
            parts = [cam]

            # Motion Pacing
            if intensity == "subtle":
                parts.append(MOTION_PACING["subtle"])
            elif intensity == "action":
                parts.append(MOTION_PACING["action"])
            elif intensity in MOTION_PACING and intensity != "balanced":
                parts.append(MOTION_PACING[intensity])

            # Atmosphere / FX
            if fx_parts:
                parts.append(", ".join(fx_parts))

            # Motion delta elements
            if motion_elements:
                parts.extend(motion_elements)

            # Bokeh directive on wide shots
            if include_bokeh:
                parts.append(VIDEO_BOKEH_DIRECTIVE)

            # Secondary dynamics & temporal anti-morphing suffix
            parts.append(f"{VIDEO_SECONDARY_DYNAMICS}, {VIDEO_TEMPORAL_INVARIANCE}")
            positive_prompt = ", ".join(parts)

        # 7. Negative prompt
        negative_prompt = MINIMAX_H3_NEGATIVE
        if extra_negative and extra_negative.strip():
            negative_prompt = f"{negative_prompt}, {extra_negative.strip()}"

        target_enum = TargetModel.MINIMAX_H3 if str(target).lower() in ("minimax_h3", "minimax") else target
        return CompiledPrompt(
            positive=positive_prompt,
            negative=negative_prompt,
            target_model=target_enum,
            dimensions=dims,
            metadata={
                "camera_direction": camera_direction,
                "intensity": intensity,
                "style_6_heading": style_6_heading,
                "is_wide": is_wide,
            },
        )

    @classmethod
    def build_directorial_prompt(
        cls,
        story: OriginalStory,
        panel: Panel,
        target: TargetModel | str = TargetModel.QWEN_IMAGE_21,
        attempt: int = 1,
        runner: Any = None,
    ) -> CompiledPrompt:
        """Central directorial prompt dispatch bridging story panel and runner to CompiledPrompt."""
        resolved_target = target
        if runner is not None:
            runner_style = getattr(runner, "style", None)
            runner_engine = getattr(runner, "engine", None)
            if runner_style == "tags" or runner_engine == "sdxl":
                resolved_target = TargetModel.SDXL
            elif runner_engine in ("flux", "natural"):
                resolved_target = "flux"
            elif runner_engine in ("qwen", "qwen_image_21"):
                resolved_target = TargetModel.QWEN_IMAGE_21

        if not panel.director:
            return CompiledPrompt(
                positive=panel.action,
                negative="",
                target_model=resolved_target if isinstance(resolved_target, TargetModel) else TargetModel.QWEN_IMAGE_21,
                dimensions=(1024, 1024),
                metadata={"panel_id": panel.id, "scene_id": panel.scene_id, "fallback": True},
            )

        spec = ShotSpec(**panel.director)
        emphasis = panel.director.get("emphasis") or []
        fallback_action = panel.action or ""

        target_str = str(resolved_target.value if isinstance(resolved_target, TargetModel) else resolved_target).lower().strip()
        if target_str in ("sdxl", "tags", TargetModel.SDXL.value):
            return cls.compile_sdxl_tag_prompt(
                story=story,
                spec=spec,
                location_id=panel.location_id,
                emphasis=emphasis,
                fallback_action=fallback_action,
            )

        return cls.compile_image_prompt(
            story=story,
            spec=spec,
            location_id=panel.location_id,
            target=resolved_target,
            emphasis=emphasis,
            simplify=attempt >= 2,
        )


# ==============================================================================
# 13. Module-Level Convenience Functions
# ==============================================================================

def compile_image_prompt(
    story: OriginalStory,
    spec: ShotSpec,
    location_id: str,
    target: TargetModel | str = TargetModel.QWEN_IMAGE_21,
    emphasis: list[str] | None = None,
    simplify: bool = False,
    dims: tuple[int, int] | None = None,
    fallback_action: str = "",
    extra_negative: str = "",
) -> CompiledPrompt:
    """Convenience wrapper for PromptCompiler.compile_image_prompt."""
    return PromptCompiler.compile_image_prompt(
        story=story,
        spec=spec,
        location_id=location_id,
        target=target,
        emphasis=emphasis,
        simplify=simplify,
        dims=dims,
        fallback_action=fallback_action,
        extra_negative=extra_negative,
    )


def compile_video_prompt(
    spec: Any = None,
    target: TargetModel | str = TargetModel.MINIMAX_H3,
    camera_direction: str = "push_in",
    custom_prompt: str = "",
    action_hint: str = "",
    intensity: str = "balanced",
    fx_tags: list[str] | str | None = None,
    style_6_heading: bool = False,
    subject_definitions: str | None = None,
    summary: str | None = None,
    retention_analysis: str | None = None,
    soundscape: str | None = None,
    music: str | None = None,
    bokeh_background: bool = False,
    dimensions: tuple[int, int] | None = None,
    extra_negative: str = "",
) -> CompiledPrompt:
    """Convenience wrapper for PromptCompiler.compile_video_prompt."""
    return PromptCompiler.compile_video_prompt(
        spec=spec,
        target=target,
        camera_direction=camera_direction,
        custom_prompt=custom_prompt,
        action_hint=action_hint,
        intensity=intensity,
        fx_tags=fx_tags,
        style_6_heading=style_6_heading,
        subject_definitions=subject_definitions,
        summary=summary,
        retention_analysis=retention_analysis,
        soundscape=soundscape,
        music=music,
        bokeh_background=bokeh_background,
        dimensions=dimensions,
        extra_negative=extra_negative,
    )


def compile_sdxl_tag_prompt(
    story: OriginalStory,
    spec: ShotSpec,
    location_id: str,
    emphasis: list[str] | None = None,
    fallback_action: str = "",
    dims: tuple[int, int] | None = None,
    extra_negative: str = "",
) -> CompiledPrompt:
    """Convenience wrapper for PromptCompiler.compile_sdxl_tag_prompt."""
    return PromptCompiler.compile_sdxl_tag_prompt(
        story=story,
        spec=spec,
        location_id=location_id,
        emphasis=emphasis,
        fallback_action=fallback_action,
        dims=dims,
        extra_negative=extra_negative,
    )


def compile_tag_prompt(*args: Any, **kwargs: Any) -> CompiledPrompt:
    """Alias for compile_sdxl_tag_prompt."""
    return PromptCompiler.compile_sdxl_tag_prompt(*args, **kwargs)


def build_directorial_prompt(
    story: OriginalStory,
    panel: Panel,
    target: TargetModel | str = TargetModel.QWEN_IMAGE_21,
    attempt: int = 1,
    runner: Any = None,
) -> CompiledPrompt:
    """Convenience wrapper for PromptCompiler.build_directorial_prompt."""
    return PromptCompiler.build_directorial_prompt(
        story=story,
        panel=panel,
        target=target,
        attempt=attempt,
        runner=runner,
    )


# Convenience aliases for shotspec backwards compatibility
compose_image_prompt = compile_image_prompt
compose_video_prompt = compile_video_prompt
compose_motion_prompt = compile_video_prompt


__all__ = [
    # Enums and Schemas
    "TargetModel",
    "StyleAnchor",
    "CharacterIdentityToken",
    "CameraOptics",
    "LightingPhysics",
    "CompositionGuardrails",
    "DirectorialPromptSpec",
    "CompiledPrompt",
    # Presets & Mappings
    "GENRE_STYLE_PRESETS",
    "NATURAL_PERSON_LOOKUP",
    "CLOTHING_KEYWORDS",
    "POSE_SENSITIVE_WORDS",
    "CAMERA_KINEMATICS",
    "MOTION_PACING",
    "VIDEO_SECONDARY_DYNAMICS",
    "VIDEO_TEMPORAL_INVARIANCE",
    "VIDEO_BOKEH_DIRECTIVE",
    "INPAINT_CORRECTION_PROMPTS",
    # Negative Prompts
    "UNIVERSAL_NEGATIVE_PROMPT",
    "QWEN_IMAGE_21_BASE_NEGATIVE",
    "UNIVERSAL_VIDEO_NEGATIVE_PROMPT",
    "MINIMAX_H3_NEGATIVE",
    "RIGGING_NEGATIVE",
    "RIGGING_NEGATIVE_PROMPT",
    # Resolution Helpers
    "resolve_video_dimensions",
    # Compilers & Functions
    "PromptCompiler",
    "compile_image_prompt",
    "compile_video_prompt",
    "compile_sdxl_tag_prompt",
    "compile_tag_prompt",
    "build_directorial_prompt",
    "compose_image_prompt",
    "compose_video_prompt",
    "compose_motion_prompt",
]
