"""Animation-Ready Rigging Pipeline: Orthographic Character Turnarounds & Rigging Specifications.

Provides structured models, prompt compilers, slice utilities, and generation pipelines for orthographic
A-pose and T-pose reference sheets and views. Supports dual-engine prompt compilation (Danbooru tags
for SDXL Animagine, and natural language descriptions for FLUX and Qwen).
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import Any, Literal, Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
import scipy.ndimage as ndi

from engine.original.genres import GENRES
from engine.original.models import Character, OriginalStory

RiggingPose = Literal["a_pose", "t_pose", "neutral_standing"]
RiggingView = Literal["front", "three_quarter", "side", "back"]


class RiggingSpec(BaseModel):
    """Specification for animation-ready orthographic character turnaround and rigging references."""

    pose: RiggingPose = "a_pose"
    views: list[RiggingView] = Field(
        default_factory=lambda: ["front", "three_quarter", "side", "back"]
    )
    orthographic: bool = True
    limb_separation: bool = True
    visible_joints: bool = True
    neutral_background: bool = True
    flat_lighting: bool = True
    background_color: str = "neutral gray"

    def __init__(self, **data: Any):
        if "pose_type" in data and "pose" not in data:
            data["pose"] = data.pop("pose_type")
        super().__init__(**data)

    @property
    def pose_type(self) -> str:
        return self.pose


class TurnaroundSheet(BaseModel):
    """Turnaround sheet asset metadata and sliced view registry."""

    character_id: str
    image_path: str | None = None
    views: dict[str, str] = Field(default_factory=dict)
    pose: str = "a_pose"
    orthographic: bool = True

    def __fspath__(self) -> str:
        return str(self.image_path) if self.image_path else ""

    def __str__(self) -> str:
        return str(self.image_path) if self.image_path else ""

    def exists(self) -> bool:
        return Path(self.image_path).exists() if self.image_path else False

    @property
    def path(self) -> Path:
        return Path(self.image_path) if self.image_path else Path("")


class MattingResult(BaseModel):
    """Result of neural alpha matting and defringing."""

    rgba_bytes: bytes
    mask_bytes: bytes
    has_alpha: bool
    halo_free: bool = True
    width: int
    height: int

    def to_image(self) -> Image.Image:
        return Image.open(io.BytesIO(self.rgba_bytes))

    def to_mask_image(self) -> Image.Image:
        return Image.open(io.BytesIO(self.mask_bytes))


class DecomposedLayer(BaseModel):
    """Single decomposed plane for parallax movement or 2D skeletal mesh animation."""

    name: str
    layer_type: str  # "foreground_subject", "prop", "background_plate"
    image_bytes: bytes
    mask_bytes: bytes | None = None
    z_index: int = 0
    depth_estimate: float = 0.0

    def to_image(self) -> Image.Image:
        """Decode image_bytes into a PIL Image."""
        return Image.open(io.BytesIO(self.image_bytes))

    def to_mask_image(self) -> Image.Image | None:
        """Decode mask_bytes into a PIL Image in mode 'L' if mask exists."""
        if self.mask_bytes is not None:
            return Image.open(io.BytesIO(self.mask_bytes))
        return None

    @property
    def role(self) -> str:
        return self.layer_type


class LayerStack(BaseModel):
    """Collection of decomposed layers representing a panel scene."""

    panel_id: str
    width: int
    height: int
    layers: list[DecomposedLayer] = Field(default_factory=list)

    def get_layer(self, name: str) -> DecomposedLayer | None:
        """Retrieve a decomposed layer by name."""
        for lay in self.layers:
            if lay.name == name:
                return lay
        if name == "prop":
            props = self.props
            return props[0] if props else None
        return None

    @property
    def background(self) -> DecomposedLayer | None:
        """Returns the background plate layer if present."""
        return self.get_layer("background_plate")

    @property
    def foreground_subject(self) -> DecomposedLayer | None:
        """Returns the primary foreground subject layer if present."""
        return self.get_layer("foreground_subject")

    @property
    def props(self) -> list[DecomposedLayer]:
        """Returns all interactive prop layers."""
        return [
            lay for lay in self.layers
            if lay.layer_type == "prop" or lay.name.startswith("prop")
        ]

    @property
    def prop(self) -> DecomposedLayer | None:
        """Returns the primary prop layer if present (for single-prop callers)."""
        props = self.props
        return props[0] if props else None

    def to_parallax_plan(self, default_depths: dict[str, float] | None = None) -> Any:
        """Bridge directly to engine.motion.models.layers.ParallaxPlan and LayerInstruction.

        Gracefully falls back to dict serialization if engine.motion models are not importable.
        """
        try:
            from engine.motion.models.enums import LayerType
            from engine.motion.models.layers import LayerInstruction, ParallaxPlan
            has_motion = True
        except Exception:
            has_motion = False

        if has_motion:
            plan_layers = []
            for lay in self.layers:
                if lay.layer_type == "foreground_subject" or lay.name == "foreground_subject":
                    ltype = LayerType.CHARACTER
                    motion_factor = 1.0
                elif lay.layer_type == "prop" or lay.name.startswith("prop"):
                    ltype = LayerType.FOREGROUND
                    if lay.name.startswith("prop_"):
                        try:
                            p_num = int(lay.name.split("_")[-1])
                        except ValueError:
                            p_num = 1
                        motion_factor = round(1.10 + 0.05 * (p_num - 1), 2)
                    else:
                        motion_factor = 1.10
                elif lay.layer_type == "background_plate" or lay.name == "background_plate":
                    ltype = LayerType.BACKGROUND
                    motion_factor = 0.6
                else:
                    ltype = LayerType.FOREGROUND
                    motion_factor = 1.0

                depth = lay.depth_estimate
                if default_depths is not None:
                    if lay.name in default_depths:
                        depth = default_depths[lay.name]
                    elif lay.layer_type in default_depths:
                        depth = default_depths[lay.layer_type]
                    elif ltype.value in default_depths:
                        depth = default_depths[ltype.value]

                instruction = LayerInstruction(
                    layer_id=f"lay_{lay.name}",
                    layer_type=ltype,
                    source_uri=f"memory://layers/{self.panel_id}/{lay.name}.png",
                    depth=float(depth),
                    motion_factor=motion_factor,
                    relative_scale=1.0,
                    relative_offset_x=0.0,
                    relative_offset_y=0.0,
                    opacity=1.0,
                    blend_mode="NORMAL",
                )
                plan_layers.append(instruction)

            return ParallaxPlan(
                enabled=len(self.layers) > 1,
                layers=plan_layers,
                fallback_flat=len(self.layers) <= 1,
                max_parallax_offset=0.08,
            )

        # Graceful dictionary fallback
        raw_layers = []
        for lay in self.layers:
            if lay.layer_type == "foreground_subject" or lay.name == "foreground_subject":
                ltype_str = "CHARACTER"
                motion_factor = 1.0
            elif lay.layer_type == "prop" or lay.name.startswith("prop"):
                ltype_str = "FOREGROUND"
                if lay.name.startswith("prop_"):
                    try:
                        p_num = int(lay.name.split("_")[-1])
                    except ValueError:
                        p_num = 1
                    motion_factor = round(1.10 + 0.05 * (p_num - 1), 2)
                else:
                    motion_factor = 1.10
            elif lay.layer_type == "background_plate" or lay.name == "background_plate":
                ltype_str = "BACKGROUND"
                motion_factor = 0.6
            else:
                ltype_str = "FOREGROUND"
                motion_factor = 1.0

            depth = lay.depth_estimate
            if default_depths is not None:
                if lay.name in default_depths:
                    depth = default_depths[lay.name]
                elif lay.layer_type in default_depths:
                    depth = default_depths[lay.layer_type]
                elif ltype_str in default_depths:
                    depth = default_depths[ltype_str]

            raw_layers.append({
                "layer_id": f"lay_{lay.name}",
                "layer_type": ltype_str,
                "source_uri": f"memory://layers/{self.panel_id}/{lay.name}.png",
                "depth": float(depth),
                "motion_factor": motion_factor,
                "relative_scale": 1.0,
                "relative_offset_x": 0.0,
                "relative_offset_y": 0.0,
                "opacity": 1.0,
                "blend_mode": "NORMAL",
            })

        return {
            "enabled": len(self.layers) > 1,
            "layers": raw_layers,
            "fallback_flat": len(self.layers) <= 1,
            "max_parallax_offset": 0.08,
        }


# Vocabulary mappings for Danbooru tag-based diffusion models (SDXL / Animagine XL 4.0)
RIGGING_POSES_TAGS: dict[str, list[str]] = {
    "a_pose": [
        "a-pose",
        "standing",
        "arms angled down 45 degrees",
        "hands away from body",
        "palms visible",
        "feet shoulder-width apart",
        "clean limb separation",
    ],
    "t_pose": [
        "t-pose",
        "standing",
        "arms outstretched horizontally",
        "arms at 90 degrees",
        "hands open",
        "feet shoulder-width apart",
        "clean limb separation",
    ],
    "neutral_standing": [
        "neutral standing pose",
        "standing straight",
        "arms relaxed at sides with visible gap",
        "unobstructed silhouette",
        "clean limb separation",
    ],
    "neutral": [
        "neutral standing pose",
        "standing straight",
        "arms relaxed at sides with visible gap",
        "unobstructed silhouette",
        "clean limb separation",
    ],
}

RIGGING_VIEWS_TAGS: dict[str, list[str]] = {
    "turnaround": [
        "character sheet",
        "turnaround",
        "model sheet",
        "reference sheet",
        "multiple views",
        "front view",
        "three-quarter view",
        "side view",
        "back view",
    ],
    "front": [
        "front view",
        "facing camera",
        "straight-on",
        "looking at viewer",
        "symmetrical",
    ],
    "three_quarter": [
        "three-quarter view",
        "3/4 angle",
        "quarter view",
        "angled view",
    ],
    "side": [
        "side view",
        "profile view",
        "full profile",
        "90 degree profile",
    ],
    "back": [
        "back view",
        "from behind",
        "facing away",
        "rear view",
    ],
}

RIGGING_SPEC_TAGS: list[str] = [
    "orthographic",
    "orthographic view",
    "flat projection",
    "architectural drawing",
    "full body",
    "head to toe",
    "visible feet",
    "feet on ground",
    "visible joints",
    "articulated joints",
    "clear silhouette",
    "limb separation",
    "zero limb overlap",
    "simple background",
    "plain background",
    "solid neutral gray background",
    "flat lighting",
    "diffused studio lighting",
    "even lighting",
    "no harsh shadows",
    "no cast shadows",
]

# Negative prompt for character rigging turnarounds:
# Explicitly suppresses occluded limbs, overlapping appendages, crossed limbs, hands in pockets,
# foreshortening, and background clutter, while strictly omitting multi-view/reference sheet prohibitions.
RIGGING_NEGATIVE: str = (
    "lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, cropped, "
    "worst quality, low quality, bad score, average score, signature, watermark, username, blurry, nsfw, nude, "
    "occluded limbs, overlapping appendages, overlapping limbs, crossed limbs, crossed arms, crossed legs, "
    "hands in pockets, foreshortening, dramatic perspective, dynamic pose, motion blur, tilted head, bent posture, "
    "dramatic shadows, harsh directional light, deep cast shadows, complex background, background clutter, "
    "scenery, props, furniture, merged limbs, connected limbs, fused fingers, hidden hands, blurred joints, "
    "floating objects, disconnected hands"
)

RIGGING_NATURAL_TEMPLATES: dict[str, str] = {
    "turnaround": (
        "Professional 2D animation character turnaround model sheet for {character_desc}. "
        "Four sequential orthographic views from left to right: front view, three-quarter 3/4 view, "
        "side profile view, and back rear view. "
        "The character is posed in a standard orthographic {pose_desc} from head to toe with complete limb separation, "
        "arms held away from the torso with relaxed open hands, and feet shoulder-width apart resting on the ground. "
        "Every anatomical joint (shoulders, elbows, wrists, hips, knees, ankles) is distinctly articulated against a "
        "clean unobstructed silhouette with zero overlapping limbs or occluded geometry. "
        "Flat, even, diffused studio lighting with no dramatic directional shadows. "
        "Solid, seamless neutral gray studio background with no environment, scenery, or props. "
        "Consistent height markers, costume details, and character proportions across all four views. "
        "Full length illustration completely in frame with generous empty margins. "
        "No text, no captions, no speech bubbles, no watermark."
    ),
    "single_view": (
        "Professional 2D animation orthographic rigging reference for {character_desc}, shown in {view_desc}. "
        "The character is posed in a clean orthographic {pose_desc} from head to toe with complete limb separation, "
        "arms held away from the body with open hands, and feet shoulder-width apart on the ground. "
        "Clear silhouette with visible articulated joints at the shoulders, elbows, hips, and knees, with zero self-occlusion. "
        "Flat, diffused studio lighting with no harsh cast shadows. "
        "Solid neutral plain background with no props or scenery. "
        "Full body shot completely in frame with generous empty margins. "
        "No text, no captions, no speech bubbles, no watermark."
    ),
}


def _seed_for(story: OriginalStory, key: str, attempt: int = 0) -> int:
    h = hashlib.sha256(f"{story.bible.premise.title}|{key}".encode()).digest()
    return int.from_bytes(h[:6], "big") + attempt * 7919


def compile_turnaround_prompt(
    char: Character,
    story: OriginalStory,
    spec: RiggingSpec | str | None = None,
    style_kind: str = "tags",
    **kwargs: Any,
) -> str | tuple[str, str]:
    """Compiles prompt for an orthographic multi-view character turnaround sheet.

    Supports Danbooru tag format (for Animagine XL / SDXL) and natural language descriptions
    (for FLUX.1 Schnell / Qwen Image 2.1). Returns the positive prompt string (or a (pos, neg)
    tuple if return_negative=True).
    """
    from engine.original import shotspec

    if isinstance(spec, str):
        if spec in ("tags", "natural"):
            style_kind = spec
            rigging_spec = RiggingSpec()
        else:
            rigging_spec = RiggingSpec(pose=spec)  # type: ignore[arg-type]
    elif spec is None:
        rigging_spec = RiggingSpec()
    else:
        rigging_spec = spec

    genre = GENRES.get(story.bible.premise.genre)
    art_style = genre.art_style if genre else "masterpiece anime illustration"

    if style_kind == "natural":
        pose_desc = (
            "A-pose with arms angled 45 degrees downward away from the body"
            if rigging_spec.pose == "a_pose"
            else "T-pose with arms outstretched horizontally"
            if rigging_spec.pose == "t_pose"
            else "neutral standing pose with arms relaxed away from torso"
        )
        pos = (
            RIGGING_NATURAL_TEMPLATES["turnaround"].format(
                character_desc=shotspec.describe_character(char),
                pose_desc=pose_desc,
            )
            + f" Style: {art_style}."
        )
        if kwargs.get("return_negative", False) or kwargs.get("with_negative", False):
            return pos, ""
        return pos

    # Danbooru tag taxonomy
    tokens: list[str] = [
        "solo",
        shotspec.person_tags(char),
        *(t.strip() for t in char.look.split(",") if t.strip()),
        *RIGGING_VIEWS_TAGS.get("turnaround", []),
        *RIGGING_POSES_TAGS.get(rigging_spec.pose, RIGGING_POSES_TAGS["a_pose"]),
        *RIGGING_SPEC_TAGS,
        *(t.strip() for t in art_style.split(",") if t.strip()),
        shotspec.QUALITY,
    ]
    # Preserve order while deduplicating
    deduped = list(dict.fromkeys(t for t in tokens if t))
    positive = ", ".join(deduped)

    if kwargs.get("return_negative", False) or kwargs.get("with_negative", False):
        return positive, RIGGING_NEGATIVE
    return positive


def compile_rigging_view_prompt(
    char: Character,
    view: RiggingView | str,
    story: OriginalStory,
    spec: RiggingSpec | str | None = None,
    style_kind: str = "tags",
    **kwargs: Any,
) -> str | tuple[str, str]:
    """Compiles prompt for an isolated orthographic rigging view (front, 3/4, side, or back)."""
    from engine.original import shotspec

    if isinstance(spec, str):
        if spec in ("tags", "natural"):
            style_kind = spec
            rigging_spec = RiggingSpec()
        else:
            rigging_spec = RiggingSpec(pose=spec)  # type: ignore[arg-type]
    elif spec is None:
        rigging_spec = RiggingSpec()
    else:
        rigging_spec = spec

    genre = GENRES.get(story.bible.premise.genre)
    art_style = genre.art_style if genre else "masterpiece anime illustration"

    if style_kind == "natural":
        pose_desc = (
            "A-pose with arms held 45 degrees downward away from torso"
            if rigging_spec.pose == "a_pose"
            else "T-pose with arms outstretched horizontally"
            if rigging_spec.pose == "t_pose"
            else "neutral standing pose with visible limb separation"
        )
        view_str = str(view).lower().replace("-", "_").replace(" ", "_")
        view_desc = {
            "front": "front view facing directly forward",
            "three_quarter": "three-quarter 3/4 angled view",
            "side": "90-degree side profile view",
            "back": "back view facing away from camera",
        }.get(view_str, f"{view_str} view")

        pos = (
            RIGGING_NATURAL_TEMPLATES["single_view"].format(
                character_desc=shotspec.describe_character(char),
                view_desc=view_desc,
                pose_desc=pose_desc,
            )
            + f" Style: {art_style}."
        )
        if kwargs.get("return_negative", False) or kwargs.get("with_negative", False):
            return pos, ""
        return pos

    view_str = str(view).lower().replace("-", "_").replace(" ", "_")
    view_tags = RIGGING_VIEWS_TAGS.get(view_str, [f"{view_str} view"])

    tokens = [
        "solo",
        shotspec.person_tags(char),
        *(t.strip() for t in char.look.split(",") if t.strip()),
        *view_tags,
        *RIGGING_POSES_TAGS.get(rigging_spec.pose, RIGGING_POSES_TAGS["a_pose"]),
        *RIGGING_SPEC_TAGS,
        *(t.strip() for t in art_style.split(",") if t.strip()),
        shotspec.QUALITY,
    ]
    deduped = list(dict.fromkeys(t for t in tokens if t))
    positive = ", ".join(deduped)

    if kwargs.get("return_negative", False) or kwargs.get("with_negative", False):
        return positive, RIGGING_NEGATIVE
    return positive


def slice_turnaround_sheet(
    sheet: Image.Image | Path | str | bytes,
    views: Sequence[RiggingView | str] | None = None,
) -> dict[str, Image.Image]:
    """Crops a horizontal multi-view turnaround sheet into individual orthographic view images."""
    if isinstance(sheet, (str, Path)):
        img = Image.open(sheet)
    elif isinstance(sheet, bytes):
        img = Image.open(io.BytesIO(sheet))
    elif isinstance(sheet, Image.Image):
        img = sheet
    else:
        raise TypeError(f"Unsupported sheet type: {type(sheet)}")

    view_list = list(views) if views is not None else ["front", "three_quarter", "side", "back"]
    num_views = len(view_list)
    if num_views == 0:
        return {}

    w, h = img.size
    slice_w = w // num_views
    result: dict[str, Image.Image] = {}

    for idx, v in enumerate(view_list):
        left = idx * slice_w
        right = (idx + 1) * slice_w if idx < num_views - 1 else w
        box = (left, 0, right, h)
        result[str(v)] = img.crop(box)

    return result


def _create_offline_turnaround_image(
    char: Character,
    spec: RiggingSpec,
    dims: tuple[int, int] = (1536, 768),
) -> Image.Image:
    """Create a high-quality offline orthographic turnaround reference image."""
    w, h = dims
    img = Image.new("RGB", (w, h), color=(180, 180, 180))
    draw = ImageDraw.Draw(img)
    num_views = len(spec.views) or 4
    slice_w = w // num_views

    # Draw vertical separator lines and alignment guides
    for i in range(num_views):
        x_left = i * slice_w
        x_right = (i + 1) * slice_w if i < num_views - 1 else w
        view_name = spec.views[i] if i < len(spec.views) else f"view_{i}"

        # Guide borders
        draw.rectangle([x_left + 8, 8, x_right - 8, h - 8], outline=(150, 150, 150), width=1)
        # Head / shoulder / waist / feet alignment lines across the sheet
        draw.line([0, int(h * 0.15), w, int(h * 0.15)], fill=(160, 160, 160), width=1)
        draw.line([0, int(h * 0.30), w, int(h * 0.30)], fill=(160, 160, 160), width=1)
        draw.line([0, int(h * 0.55), w, int(h * 0.55)], fill=(160, 160, 160), width=1)
        draw.line([0, int(h * 0.90), w, int(h * 0.90)], fill=(160, 160, 160), width=1)

        # Draw character silhouette with clear limb separation and articulated joints
        cx = (x_left + x_right) // 2
        # Head
        head_r = int(h * 0.07)
        head_cy = int(h * 0.18)
        draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=(60, 60, 70))
        # Torso
        torso_top = head_cy + head_r + 4
        torso_bottom = int(h * 0.55)
        torso_half_w = int(head_r * 1.2)
        draw.rectangle([cx - torso_half_w, torso_top, cx + torso_half_w, torso_bottom], fill=(60, 60, 70))

        # Limbs depending on pose
        arm_start_y = torso_top + 10
        if spec.pose == "t_pose":
            # T-pose arms outstretched horizontally
            draw.line([cx - torso_half_w, arm_start_y, x_left + 20, arm_start_y], fill=(60, 60, 70), width=12)
            draw.line([cx + torso_half_w, arm_start_y, x_right - 20, arm_start_y], fill=(60, 60, 70), width=12)
        else:
            # A-pose arms angled downward at 45 degrees with clean separation
            draw.line([cx - torso_half_w, arm_start_y, cx - torso_half_w - 60, arm_start_y + 120], fill=(60, 60, 70), width=12)
            draw.line([cx + torso_half_w, arm_start_y, cx + torso_half_w + 60, arm_start_y + 120], fill=(60, 60, 70), width=12)

        # Legs: clean separation shoulder-width apart
        leg_y_top = torso_bottom
        leg_y_bottom = int(h * 0.90)
        draw.line([cx - 25, leg_y_top, cx - 35, leg_y_bottom], fill=(60, 60, 70), width=14)
        draw.line([cx + 25, leg_y_top, cx + 35, leg_y_bottom], fill=(60, 60, 70), width=14)

        # Label view
        draw.text((x_left + 15, h - 30), f"{char.name}: {view_name} ({spec.pose})", fill=(40, 40, 40))

    return img


def generate_turnaround_sheet(
    char: Character,
    story: OriginalStory,
    ws: Path,
    runner: Any | None = None,
    spec: RiggingSpec | None = None,
    slice_views: bool = True,
) -> TurnaroundSheet:
    """Generates (or reuses) a character turnaround sheet and optionally slices it into individual views.

    Coordinates with ComfyRunner if available and ready; otherwise generates offline reference sheets.
    """
    from engine.original import shotspec

    spec = spec or RiggingSpec()
    rigging_dir = ws / "rigging"
    rigging_dir.mkdir(parents=True, exist_ok=True)
    out_file = rigging_dir / f"{char.id}_turnaround.png"

    style_kind = getattr(runner, "style", "tags") if runner else "tags"
    w, h = shotspec.resolve_dimensions("turnaround", default=(1536, 768))

    if not out_file.exists():
        if runner is not None and hasattr(runner, "generate"):
            pos = compile_turnaround_prompt(char, story, spec=spec, style_kind=style_kind)
            neg = RIGGING_NEGATIVE if style_kind != "natural" else ""
            seed = _seed_for(story, f"turnaround_{char.id}_{spec.pose}")
            png_bytes = runner.generate(
                pos=pos,
                neg=neg,
                seed=seed,
                width=w,
                height=h,
                prefix=f"turnaround_{char.id}",
            )
            out_file.write_bytes(png_bytes)
        else:
            img = _create_offline_turnaround_image(char, spec, (w, h))
            img.save(out_file, format="PNG")

    # Slice the sheet into individual views if requested
    views_dict: dict[str, str] = {}
    if slice_views and out_file.exists():
        with Image.open(out_file) as sheet_img:
            slices = slice_turnaround_sheet(sheet_img, views=spec.views)
            for view_name, slice_img in slices.items():
                view_path = rigging_dir / f"{char.id}_{view_name}.png"
                if not view_path.exists():
                    slice_img.save(view_path, format="PNG")
                views_dict[view_name] = str(view_path)

    return TurnaroundSheet(
        character_id=char.id,
        image_path=str(out_file),
        views=views_dict,
        pose=spec.pose,
        orthographic=spec.orthographic,
    )


def generate_rigging_views(
    char: Character,
    story: OriginalStory,
    ws: Path,
    runner: Any | None = None,
    spec: RiggingSpec | None = None,
) -> dict[str, Path]:
    """Generates and returns individual orthographic rigging views for a character."""
    spec = spec or RiggingSpec()
    sheet = generate_turnaround_sheet(char, story, ws, runner=runner, spec=spec, slice_views=True)
    return {v: Path(p) for v, p in sheet.views.items()}


def guided_filter_alpha(
    guide_rgb: np.ndarray,
    alpha: np.ndarray,
    radius: int = 4,
    eps: float = 1e-4,
) -> np.ndarray:
    """Refine and anti-alias alpha boundaries using the He et al. Guided Filter.

    Uses cv2.boxFilter and NumPy to smooth edges without blur or staircasing artifacts,
    aligning the matte transitions with the luminance gradient of the guide image.
    """
    if guide_rgb.ndim == 3:
        if guide_rgb.shape[2] == 4:
            guide_rgb = guide_rgb[:, :, :3]
        guide = cv2.cvtColor(guide_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    else:
        guide = guide_rgb.astype(np.float32) / 255.0

    p = alpha.astype(np.float32) / 255.0
    ksize = (2 * radius + 1, 2 * radius + 1)

    mean_I = cv2.boxFilter(guide, -1, ksize, normalize=True)
    mean_p = cv2.boxFilter(p, -1, ksize, normalize=True)
    corr_Ip = cv2.boxFilter(guide * p, -1, ksize, normalize=True)
    cov_Ip = corr_Ip - mean_I * mean_p

    mean_II = cv2.boxFilter(guide * guide, -1, ksize, normalize=True)
    var_I = mean_II - mean_I * mean_I

    a = cov_Ip / (var_I + eps)
    b = mean_p - a * mean_I

    mean_a = cv2.boxFilter(a, -1, ksize, normalize=True)
    mean_b = cv2.boxFilter(b, -1, ksize, normalize=True)

    q = mean_a * guide + mean_b
    return np.clip(q * 255.0, 0, 255).astype(np.uint8)


def defringe_alpha(
    rgb: np.ndarray,
    alpha: np.ndarray,
    threshold: int = 240,
) -> tuple[np.ndarray, np.ndarray]:
    """Eliminates color fringe and white/light halos from alpha matte edges.

    Uses morphological color decontamination: solid foreground RGB values (where alpha >= threshold)
    are propagated into semi-transparent boundary pixels and padding gutters via nearest-neighbor
    Euclidean distance transform. This replaces background-polluted edge colors with authentic
    foreground pigments, guaranteeing zero halo when composited over arbitrary backgrounds.
    """
    if rgb.ndim == 3 and rgb.shape[2] == 4:
        alpha = rgb[:, :, 3]
        rgb = rgb[:, :, :3]

    if alpha.ndim != 2:
        alpha = alpha.squeeze()

    solid_mask = (alpha >= threshold)

    # If no pixels meet the threshold, try lower threshold
    if not np.any(solid_mask):
        if np.any(alpha > 0):
            solid_mask = (alpha > 0)
        else:
            return rgb.copy(), alpha.copy()

    if np.all(solid_mask):
        return rgb.copy(), alpha.copy()

    # Nearest-neighbor coordinate lookup for solid foreground pixels
    indices = ndi.distance_transform_edt(~solid_mask, return_indices=True, return_distances=False)
    decontaminated_rgb = rgb[indices[0], indices[1]]

    # Ensure solid foreground pixels remain unchanged
    decontaminated_rgb[solid_mask] = rgb[solid_mask]

    return decontaminated_rgb, alpha


def _local_matting(pil_img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Local-first segmentation using OpenCV GrabCut, hole-filling, and He et al. Guided Filter."""
    # Check if image already has transparency
    if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
        rgba = np.array(pil_img.convert("RGBA"))
        alpha = rgba[:, :, 3]
        if np.any(alpha < 250):
            rgb = rgba[:, :, :3]
            refined_alpha = guided_filter_alpha(rgb, alpha, radius=4)
            return rgb, refined_alpha

    rgb = np.array(pil_img.convert("RGB"))
    h, w = rgb.shape[:2]
    bw = max(2, int(w * 0.04))
    bh = max(2, int(h * 0.04))
    borders = np.concatenate([
        rgb[:bh, :].reshape(-1, 3),
        rgb[-bh:, :].reshape(-1, 3),
        rgb[:, :bw].reshape(-1, 3),
        rgb[:, -bw:].reshape(-1, 3),
    ], axis=0)
    bg_color = np.median(borders, axis=0)
    bg_dist = np.linalg.norm(rgb.astype(np.float32) - bg_color.astype(np.float32), axis=2)
    threshold = max(15.0, float(np.std(borders)) * 1.5)
    diff_mask = bg_dist > threshold

    gc_mask = np.full((h, w), cv2.GC_PR_BGD, dtype=np.uint8)
    gc_mask[diff_mask] = cv2.GC_PR_FGD
    gc_mask[:bh, :] = cv2.GC_BGD
    gc_mask[-bh:, :] = cv2.GC_BGD
    gc_mask[:, :bw] = cv2.GC_BGD
    gc_mask[:, -bw:] = cv2.GC_BGD
    center_box = (slice(int(h * 0.15), int(h * 0.85)), slice(int(w * 0.15), int(w * 0.85)))
    gc_mask[center_box][diff_mask[center_box]] = cv2.GC_FGD

    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(rgb, gc_mask, None, bgdModel, fgdModel, 2, cv2.GC_INIT_WITH_MASK)
        raw_mask = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    except Exception:
        raw_mask = (diff_mask * 255).astype(np.uint8)

    if np.count_nonzero(raw_mask) == 0:
        raw_mask = (diff_mask * 255).astype(np.uint8)
        if np.count_nonzero(raw_mask) == 0:
            raw_mask[int(h * 0.2):int(h * 0.8), int(w * 0.2):int(w * 0.8)] = 255

    # Fill internal holes (e.g. solid clothing matching background tone)
    filled = ndi.binary_fill_holes(raw_mask > 0).astype(np.uint8) * 255

    # Refine boundaries with Guided Filter
    refined_alpha = guided_filter_alpha(rgb, filled, radius=4, eps=1e-4)
    return rgb, refined_alpha


def remove_background(
    image: Image.Image | bytes | Path | str,
    runner: Any | None = None,
    defringe: bool = True,
) -> MattingResult:
    """Removes image background, outputting transparent RGBA PNG with clean alpha and zero halo.

    If runner is provided and has an active matting workflow ('anime_alpha_matting'), delegates to
    the ComfyUI runner. Otherwise, seamlessly falls back to the local Python matting engine
    (OpenCV GrabCut + Guided Filter + morphological color decontamination) without cloud calls.
    """
    if isinstance(image, (str, Path)):
        pil_img = Image.open(image)
    elif isinstance(image, bytes):
        pil_img = Image.open(io.BytesIO(image))
    elif isinstance(image, Image.Image):
        pil_img = image
    elif isinstance(image, np.ndarray):
        pil_img = Image.fromarray(image)
    else:
        raise TypeError(f"Unsupported image type: {type(image)}")

    w, h = pil_img.size

    # Check if runner is ready with matting workflow
    if runner is not None and getattr(runner, "matting_wf", None) is not None:
        try:
            rgba_bytes = runner.remove_background(pil_img, defringe=defringe)
            res_pil = Image.open(io.BytesIO(rgba_bytes)).convert("RGBA")
            np_rgba = np.array(res_pil)
            alpha = np_rgba[:, :, 3]
            mask_pil = Image.fromarray(alpha, "L")
            buf_m = io.BytesIO()
            mask_pil.save(buf_m, format="PNG")
            return MattingResult(
                rgba_bytes=rgba_bytes,
                mask_bytes=buf_m.getvalue(),
                has_alpha=True,
                halo_free=defringe,
                width=w,
                height=h,
            )
        except Exception:
            # Fall back cleanly to local engine
            pass

    rgb, alpha = _local_matting(pil_img)

    if defringe:
        rgb, alpha = defringe_alpha(rgb, alpha)

    rgba = np.dstack([rgb, alpha])
    final_rgba = Image.fromarray(rgba, "RGBA")
    buf_rgba = io.BytesIO()
    final_rgba.save(buf_rgba, format="PNG")
    rgba_bytes = buf_rgba.getvalue()

    mask_pil = Image.fromarray(alpha, "L")
    buf_mask = io.BytesIO()
    mask_pil.save(buf_mask, format="PNG")
    mask_bytes = buf_mask.getvalue()

    return MattingResult(
        rgba_bytes=rgba_bytes,
        mask_bytes=mask_bytes,
        has_alpha=True,
        halo_free=defringe,
        width=w,
        height=h,
    )


class MaskDict(dict):
    """Dictionary of extracted masks supporting individual prop keys and .props accessor."""

    @property
    def props(self) -> list[Image.Image]:
        """List of individual prop mask images in mode 'L'."""
        prop_keys = sorted([k for k in self.keys() if k.startswith("prop_")], key=lambda k: int(k.split("_")[-1]))
        return [self[k] for k in prop_keys]

    def __getitem__(self, key: str) -> Any:
        if key == "props" and not super().__contains__("props"):
            return self.props
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "props" and not super().__contains__("props"):
            return self.props
        return super().get(key, default)


def extract_subject_and_prop_masks(
    image: Image.Image | bytes | Path | str,
    prompt_hint: str = "",
) -> MaskDict:
    """Automated mask extraction separating character subjects, interactive props, and background plates.

    Returns a MaskDict mapping:
      - 'subject': PIL Image in mode 'L' (primary character silhouette)
      - 'prop': PIL Image in mode 'L' (all secondary props merged, or black if none)
      - 'background': PIL Image in mode 'L' (background plate, inverse of subject+props)
      - 'foreground': PIL Image in mode 'L' (combined subject + props)
      - 'prop_1', 'prop_2', ..., 'prop_k': individual prop masks for distinct props
      - 'props' (via key or property): list of PIL Images for distinct props
    """
    if isinstance(image, (str, Path)):
        pil_img = Image.open(image)
    elif isinstance(image, bytes):
        pil_img = Image.open(io.BytesIO(image))
    elif isinstance(image, Image.Image):
        pil_img = image
    elif isinstance(image, np.ndarray):
        pil_img = Image.fromarray(image)
    else:
        raise TypeError(f"Unsupported image type: {type(image)}")

    w, h = pil_img.size

    # Extract overall foreground alpha matte
    res = remove_background(pil_img, runner=None, defringe=True)
    matte = np.array(res.to_mask_image())

    # Binarize for connected component analysis
    bin_mask = (matte > 127).astype(np.uint8)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bin_mask, connectivity=8)

    prop_dict: dict[str, Image.Image] = {}

    if num_labels <= 1:
        # No foreground detected; fallback: center region is subject
        subj_mask = np.zeros((h, w), dtype=np.uint8)
        prop_mask = np.zeros((h, w), dtype=np.uint8)
        bg_mask = np.full((h, w), 255, dtype=np.uint8)
    else:
        # Filter out background label 0
        areas = stats[1:, cv2.CC_STAT_AREA]
        # Identify subject: largest component
        sorted_indices = 1 + np.argsort(areas)[::-1]
        subj_label = sorted_indices[0]

        # Any secondary components with sufficient area (>= 50 px)
        prop_labels = [idx for idx in sorted_indices[1:] if stats[idx, cv2.CC_STAT_AREA] >= 50]

        subj_mask = np.where(labels == subj_label, matte, 0).astype(np.uint8)
        if prop_labels:
            is_prop = np.isin(labels, prop_labels)
            prop_mask = np.where(is_prop, matte, 0).astype(np.uint8)
            for p_idx, l in enumerate(prop_labels, start=1):
                p_m = np.where(labels == l, matte, 0).astype(np.uint8)
                prop_dict[f"prop_{p_idx}"] = Image.fromarray(p_m, "L")
        else:
            prop_mask = np.zeros((h, w), dtype=np.uint8)

        # Background mask is 255 where neither subject nor prop
        combined_fg = np.clip(subj_mask.astype(int) + prop_mask.astype(int), 0, 255).astype(np.uint8)
        bg_mask = (255 - combined_fg).astype(np.uint8)

    ret = MaskDict({
        "subject": Image.fromarray(subj_mask, "L"),
        "prop": Image.fromarray(prop_mask, "L"),
        "background": Image.fromarray(bg_mask, "L"),
        "foreground": Image.fromarray(np.clip(subj_mask.astype(int) + prop_mask.astype(int), 0, 255).astype(np.uint8), "L"),
    })
    ret.update(prop_dict)
    return ret


def inpaint_background_plate(
    base_image: Image.Image | bytes | Path | str,
    occlusion_mask: Image.Image | bytes | Path | str,
    runner: Any | None = None,
    dilation_px: int = 12,
    prompt_hint: str = "",
) -> Image.Image:
    """Inpaints occluded regions in base_image to produce a clean, hole-free background plate.

    Dilates the occlusion mask by `dilation_px` (default 12px) using cv2.dilate with an elliptical
    morphological kernel to eliminate edge fringe and boundary halos around holes.
    Coordinates with ComfyRunner inpaint workflow ('anime_sdxl_inpaint') when available.
    When runner is unavailable or offline, executes genuine local OpenCV Navier-Stokes/Telea
    inpainting (cv2.inpaint(bgr, mask, 5, cv2.INPAINT_TELEA)).
    Returns an infilled, hole-free RGB Image.Image.
    """
    if isinstance(base_image, (str, Path)):
        base_pil = Image.open(base_image).convert("RGB")
    elif isinstance(base_image, bytes):
        base_pil = Image.open(io.BytesIO(base_image)).convert("RGB")
    elif isinstance(base_image, Image.Image):
        base_pil = base_image.convert("RGB")
    elif isinstance(base_image, np.ndarray):
        base_pil = Image.fromarray(base_image).convert("RGB")
    else:
        raise TypeError(f"Unsupported base_image type: {type(base_image)}")

    if isinstance(occlusion_mask, (str, Path)):
        mask_pil = Image.open(occlusion_mask).convert("L")
    elif isinstance(occlusion_mask, bytes):
        mask_pil = Image.open(io.BytesIO(occlusion_mask)).convert("L")
    elif isinstance(occlusion_mask, Image.Image):
        mask_pil = occlusion_mask.convert("L")
    elif isinstance(occlusion_mask, np.ndarray):
        mask_pil = Image.fromarray(occlusion_mask).convert("L")
    else:
        raise TypeError(f"Unsupported occlusion_mask type: {type(occlusion_mask)}")

    if mask_pil.size != base_pil.size:
        mask_pil = mask_pil.resize(base_pil.size, Image.Resampling.NEAREST)

    mask_arr = np.array(mask_pil)
    if dilation_px > 0:
        k_size = 2 * dilation_px + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        dilated_mask = cv2.dilate(mask_arr, kernel, iterations=1)
    else:
        dilated_mask = mask_arr.copy()

    if np.count_nonzero(dilated_mask) == 0:
        return base_pil.copy()

    # Attempt ComfyRunner inpaint if available and ready
    if runner is not None and hasattr(runner, "inpaint"):
        if not (hasattr(runner, "inpaint_wf") and runner.inpaint_wf is None):
            try:
                buf_base = io.BytesIO()
                base_pil.save(buf_base, format="PNG")
                buf_m = io.BytesIO()
                Image.fromarray(dilated_mask, "L").save(buf_m, format="PNG")

                prompt = prompt_hint if prompt_hint else "anime scenery, detailed background plate, masterpiece"
                neg = "lowres, text, character, person, bad quality"
                res_bytes = runner.inpaint(
                    base_image=buf_base.getvalue(),
                    mask_image=buf_m.getvalue(),
                    prompt=prompt,
                    neg=neg,
                    seed=42,
                )
                if isinstance(res_bytes, bytes):
                    return Image.open(io.BytesIO(res_bytes)).convert("RGB")
                elif isinstance(res_bytes, Image.Image):
                    return res_bytes.convert("RGB")
            except Exception:
                pass  # Fall back cleanly to local OpenCV inpainting

    # Genuine local OpenCV Navier-Stokes/Telea inpainting
    base_np = np.array(base_pil)
    bgr = cv2.cvtColor(base_np, cv2.COLOR_RGB2BGR)
    inpaint_mask = (dilated_mask > 0).astype(np.uint8) * 255

    if np.all(inpaint_mask == 255):
        med_col = np.median(base_np, axis=(0, 1)).astype(np.uint8)
        filled_np = np.full_like(base_np, med_col)
        return Image.fromarray(filled_np, "RGB")

    infilled_bgr = cv2.inpaint(bgr, inpaint_mask, 5, cv2.INPAINT_TELEA)
    infilled_rgb = cv2.cvtColor(infilled_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(infilled_rgb, "RGB")


def decompose_layers(
    image: Image.Image | bytes | Path | str,
    panel_id: str = "panel_0",
    runner: Any | None = None,
    prompt_hint: str = "",
    isolate_props: bool = False,
    separate_props: bool | None = None,
    multi_prop: bool | None = None,
    **kwargs: Any,
) -> LayerStack:
    """Decomposes a flat panel image into foreground subject, props (if detected), and clean infilled background plate.

    Segments character subject, props, and background plate via extract_subject_and_prop_masks() and
    remove_background(). Synthesizes clean infilled background plate via inpaint_background_plate().
    Assembles DecomposedLayer instances:
      - Subject layer (name="foreground_subject", layer_type="foreground_subject", z_index=20, depth_estimate=0.8)
      - Prop layers:
        - When single prop or isolate_props=False: name="prop_1", layer_type="prop", z_index=15, depth_estimate=0.6
        - When multi-prop (isolate_props=True): distinct layers name="prop_1", "prop_2", ..., "prop_k" with individual
          masks, images, distinct z_indices (e.g. 11, 12, ...), and distinct depth estimates.
      - Clean infilled background plate (name="background_plate", layer_type="background_plate", z_index=0, depth_estimate=0.1)
    """
    if isinstance(image, (str, Path)):
        pil_img = Image.open(image)
    elif isinstance(image, bytes):
        pil_img = Image.open(io.BytesIO(image))
    elif isinstance(image, Image.Image):
        pil_img = image
    elif isinstance(image, np.ndarray):
        pil_img = Image.fromarray(image)
    else:
        raise TypeError(f"Unsupported image type: {type(image)}")

    w, h = pil_img.size

    # Check prop isolation flag
    if separate_props is not None:
        isolate = separate_props
    elif multi_prop is not None:
        isolate = multi_prop
    elif isolate_props:
        isolate = True
    elif prompt_hint and any(k in prompt_hint.lower() for k in ("separate_props", "multi_prop", "isolate_props")):
        isolate = True
    else:
        isolate = False

    # 1. Segment subject and prop masks
    masks = extract_subject_and_prop_masks(pil_img, prompt_hint=prompt_hint)
    subj_mask_im = masks["subject"]
    prop_mask_im = masks["prop"]
    fg_mask_im = masks["foreground"]
    prop_masks_list: list[Image.Image] = masks.get("props", [])

    subj_mask_arr = np.array(subj_mask_im)
    prop_mask_arr = np.array(prop_mask_im)

    # 2. Extract clean defringed foreground RGBA
    matting_res = remove_background(pil_img, runner=runner, defringe=True)
    full_rgba_im = matting_res.to_image().convert("RGBA")
    full_rgba_arr = np.array(full_rgba_im)

    # 3. Build foreground_subject layer
    if np.count_nonzero(subj_mask_arr) == 0 and np.count_nonzero(full_rgba_arr[:, :, 3]) > 0:
        subj_mask_arr = full_rgba_arr[:, :, 3]

    subj_alpha = np.minimum(full_rgba_arr[:, :, 3], subj_mask_arr)
    subj_rgba = np.dstack([full_rgba_arr[:, :, :3], subj_alpha])
    subj_pil = Image.fromarray(subj_rgba, "RGBA")

    buf_subj = io.BytesIO()
    subj_pil.save(buf_subj, format="PNG")
    buf_subj_mask = io.BytesIO()
    Image.fromarray(subj_alpha, "L").save(buf_subj_mask, format="PNG")

    subj_layer = DecomposedLayer(
        name="foreground_subject",
        layer_type="foreground_subject",
        image_bytes=buf_subj.getvalue(),
        mask_bytes=buf_subj_mask.getvalue(),
        z_index=20,
        depth_estimate=0.8,
    )

    layers: list[DecomposedLayer] = []

    # 4. Synthesize infilled background plate
    bg_infilled_pil = inpaint_background_plate(
        base_image=pil_img,
        occlusion_mask=fg_mask_im,
        runner=runner,
        dilation_px=12,
        prompt_hint=prompt_hint,
    )
    buf_bg = io.BytesIO()
    bg_infilled_pil.save(buf_bg, format="PNG")

    bg_layer = DecomposedLayer(
        name="background_plate",
        layer_type="background_plate",
        image_bytes=buf_bg.getvalue(),
        mask_bytes=None,
        z_index=0,
        depth_estimate=0.1,
    )
    layers.append(bg_layer)

    # 5. Build prop layers
    if isolate and len(prop_masks_list) > 1:
        k = len(prop_masks_list)
        for idx, p_mask_im in enumerate(prop_masks_list, start=1):
            p_mask_arr = np.array(p_mask_im)
            if np.count_nonzero(p_mask_arr) == 0:
                continue
            p_alpha = np.minimum(full_rgba_arr[:, :, 3], p_mask_arr)
            p_rgba = np.dstack([full_rgba_arr[:, :, :3], p_alpha])
            p_pil = Image.fromarray(p_rgba, "RGBA")

            buf_p = io.BytesIO()
            p_pil.save(buf_p, format="PNG")
            buf_p_mask = io.BytesIO()
            Image.fromarray(p_alpha, "L").save(buf_p_mask, format="PNG")

            p_depth = round(0.42 + (idx / (k + 1)) * 0.32, 3)
            p_z = 10 + idx

            prop_layer = DecomposedLayer(
                name=f"prop_{idx}",
                layer_type="prop",
                image_bytes=buf_p.getvalue(),
                mask_bytes=buf_p_mask.getvalue(),
                z_index=p_z,
                depth_estimate=p_depth,
            )
            layers.append(prop_layer)
    else:
        if np.count_nonzero(prop_mask_arr) > 0:
            prop_alpha = np.minimum(full_rgba_arr[:, :, 3], prop_mask_arr)
            prop_rgba = np.dstack([full_rgba_arr[:, :, :3], prop_alpha])
            prop_pil = Image.fromarray(prop_rgba, "RGBA")

            buf_prop = io.BytesIO()
            prop_pil.save(buf_prop, format="PNG")
            buf_prop_mask = io.BytesIO()
            Image.fromarray(prop_alpha, "L").save(buf_prop_mask, format="PNG")

            prop_layer = DecomposedLayer(
                name="prop_1",
                layer_type="prop",
                image_bytes=buf_prop.getvalue(),
                mask_bytes=buf_prop_mask.getvalue(),
                z_index=15,
                depth_estimate=0.6,
            )
            layers.append(prop_layer)

    layers.append(subj_layer)

    # Sort layers by z_index
    layers.sort(key=lambda l: l.z_index)

    return LayerStack(
        panel_id=panel_id,
        width=w,
        height=h,
        layers=layers,
    )

