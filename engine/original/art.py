"""Art engine: story panels -> ComfyUI images (cached, resumable), character sheets and a vision-based consistency check.

Consistency baseline (no extra models): every panel prompt repeats each character's exact `look` tags, and a vision model
checks the result against those tags; a panel scoring below THRESHOLD is regenerated with a new seed and the missing tags
emphasised, keeping the best attempt. The measured score is stored per panel so the approach can be judged (and replaced,
e.g. by IP-Adapter) with data.
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Callable

from PIL import Image
from pydantic import BaseModel, Field

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.art import ART_WORKFLOW_ID, ArtEngine, _patch_workflow
from engine.original.genres import GENRES
from engine.original.models import Character, OriginalStory, Panel
from engine.original import review as review_mod
from engine.original import shotspec
from engine.original.rigging import (
    RIGGING_NEGATIVE,
    RiggingPose,
    RiggingView,
    RiggingSpec,
    TurnaroundSheet,
    MattingResult,
    DecomposedLayer,
    LayerStack,
    compile_turnaround_prompt,
    compile_rigging_view_prompt,
    generate_turnaround_sheet,
    generate_rigging_views,
    slice_turnaround_sheet,
    remove_background,
    defringe_alpha,
    guided_filter_alpha,
    extract_subject_and_prop_masks,
    inpaint_background_plate,
    decompose_layers,
)

W, H = 1344, 768  # SDXL-friendly 16:9, the video frame shape
THRESHOLD = 0.6
SHOT_TAGS = {"wide": "wide shot, scenery, from a distance", "full": "full body shot, head to toe, visible feet",
             "full_body": "full body shot, head to toe, visible feet", "medium": "cowboy shot",
             "close": "close-up, portrait", "extreme_close": "extreme close-up, detail focus",
             "over_shoulder": "from behind, over the shoulder"}
ANGLE_TAGS = {"eye_level": "", "low": "from below", "high": "from above", "dutch": "dutch angle"}
POSE_KEYS = {"eyes closed", "sleeping", "yawning", "smiling", "tears"}  # deterministic requirements from the narration
QUALITY = "safe, masterpiece, high score, great score, absurdres"
NEGATIVE = ("lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, cropped, worst quality, "
            "low quality, low score, bad score, average score, signature, watermark, username, blurry, nsfw, nude, "
            "suggestive, revealing clothes, speech bubble, floating objects, disconnected hands")


def build_prompt(story: OriginalStory, panel: Panel, emphasis: list[str] | None = None, style: str = "tags",
                 must: list[str] | None = None, attempt: int = 0) -> tuple[str, str]:
    if panel.director:  # a directed shot: the composer writes the detailed prompt from the structured spec
        spec = shotspec.ShotSpec(**panel.director)
        if style == "natural":
            spec = spec.model_copy(update={"key_visuals": list(dict.fromkeys(spec.key_visuals + (must or [])))[:8]})  # the narration's own facts
            if attempt >= 2:  # last attempt: widen the frame so the objects the narration names fit in with the character
                spec = spec.model_copy(update={"shot": {"close": "medium", "extreme_close": "medium", "medium": "wide"}.get(spec.shot, spec.shot)})
            return shotspec.compose_natural(story, spec, panel.location_id, emphasis, simplify=attempt >= 2)
        return shotspec.compose(story, spec, panel.location_id, emphasis)
    genre = GENRES[story.bible.premise.genre]
    chars = {c.id: c for c in story.bible.characters}
    shown = [chars[c] for c in panel.character_ids if c in chars][:2]
    loc = next((x for x in story.bible.locations if x.id == panel.location_id), None)
    if style == "natural":
        char_descs = [f"{c.name}: {c.look}" for c in shown]
        char_str = f"Featuring {', '.join(char_descs)}. " if char_descs else ""
        loc_str = f"Setting: {loc.look}. " if loc else ""
        shot_str = f"{panel.shot.replace('_', ' ')} shot, {panel.angle.replace('_', ' ')} angle. "
        bindings_nat = shotspec.compile_interaction_bindings_natural([panel.action] + panel.key_visuals)
        contact_str = f"Physical contact: {'; '.join(bindings_nat)}. " if bindings_nat else ""
        margin_str = f"{shotspec.MARGIN_NATURAL.get(panel.shot, '')} " if shotspec.MARGIN_NATURAL.get(panel.shot) else ""
        pos = f"{panel.action.rstrip('.')}. {contact_str}{margin_str}{char_str}{loc_str}{shot_str}{genre.art_style}"
        neg = "blurry, distorted, low quality, bad anatomy, text, watermark, extra limbs, floating objects, disconnected hands"
        return pos, neg
    looks = []
    for c in shown:
        tags = c.look
        for t in emphasis or []:
            tags = tags.replace(t, f"({t}:1.3)")
        looks.append(tags)
    count = {0: "no humans", 1: "solo", 2: "2others"}.get(len(shown), "multiple others")
    keys = [f"({k}:1.4)" if (k in (emphasis or []) or k in POSE_KEYS) else k for k in panel.key_visuals]
    bindings = shotspec.compile_interaction_bindings_tags([panel.action] + panel.key_visuals)
    margins = shotspec.MARGIN_TAGS.get(panel.shot, [])
    parts = [count, *looks, *keys, panel.action.rstrip("."), *bindings, SHOT_TAGS.get(panel.shot, ""), *margins, ANGLE_TAGS.get(panel.angle, ""),
             loc.look if loc else "", genre.art_style, QUALITY]
    neg = NEGATIVE + (", open eyes, looking at viewer" if "eyes closed" in panel.key_visuals else "")
    return ", ".join(p for p in parts if p), neg


SHEET_NEGATIVE = NEGATIVE + ", multiple views, split screen, collage, reference sheet, multiple characters, 2girls, 2boys"


def sheet_prompt(c: Character, story: OriginalStory, style_kind: str = "tags") -> str:
    """One clean portrait per character: it is also the IP-Adapter reference, so it must show exactly one subject."""
    style = GENRES[story.bible.premise.genre].art_style
    if style_kind == "natural":
        return (f"Character reference portrait, upper body, facing the viewer, plain background, {style}. "
                f"{shotspec.describe_character(c)}. {shotspec.NATURAL_SUFFIX}")
    return f"solo, {shotspec.person_tags(c)}, {c.look}, upper body, portrait, looking at viewer, simple plain background, {style}, {QUALITY}"


def seed_for(story: OriginalStory, key: str, attempt: int = 0) -> int:
    h = hashlib.sha256(f"{story.bible.premise.title}|{key}".encode()).digest()
    return int.from_bytes(h[:6], "big") + attempt * 7919


class ComfyRunner:
    """Text to image through the central ArtEngine (qwen_image_21); the SDXL tools (ControlNet, inpaint, matting, IP-Adapter) run on the same poll loop. Returns PNG bytes."""

    def __init__(self, client: ComfyUIClient | None = None, workflow_id: str = "anime_sdxl", ipa_id: str = "anime_sdxl_ipa",
                 ipa2_id: str = "anime_sdxl_ipa2", engine: str | None = None, inpaint_id: str = "anime_sdxl_inpaint",
                 controlnet_id: str = "anime_sdxl_controlnet"):
        self.client = client or ComfyUIClient()
        reg = ComfyWorkflowRegistry(self.client)
        self.art = ArtEngine(self.client, reg)  # the one text-to-image engine; every submit/poll/download below goes through it
        engine = engine or os.environ.get("PANELFLOW_IMAGE_ENGINE", "qwen")  # qwen (default) | sdxl (the legacy base the ControlNet/IP-Adapter tools were built on)
        if engine in ("auto", "qwen", "qwen21", ART_WORKFLOW_ID):
            try:
                self.art.require_ready()
            except Exception as exc:
                raise RuntimeError(f"Qwen Image 2.1 ({ART_WORKFLOW_ID}) is not ready: {exc}") from exc
            self.engine, self.style = "qwen", "natural"  # a prompt-following model: it reads sentences, so objects and actions in the narration survive
            self.workflow = self.meta = None
        elif engine == "sdxl":
            pre = reg.preflight(workflow_id)
            if not pre["ready"]:
                raise RuntimeError(f"ComfyUI workflow not ready: missing nodes {pre['missing_nodes']}, models {pre['missing_models']}")
            self.engine, self.style = "sdxl", "tags"
            self.workflow, self.meta = reg.load(workflow_id)[0], reg.metadata(workflow_id)
        else:
            raise ValueError(f"Unknown image engine {engine!r}: the art workflow is {ART_WORKFLOW_ID!r} (FLUX and the other text-to-image workflows were removed)")
        self.ipa = None  # optional: without its nodes/models panels fall back to prompt-only consistency
        try:
            if reg.preflight(ipa_id)["ready"]:
                self.ipa = (reg.load(ipa_id)[0], reg.metadata(ipa_id))
        except Exception:
            self.ipa = None
        self.ipa2 = None  # two-character panels: left/right masked references; falls back to the single-reference workflow
        try:
            if reg.preflight(ipa2_id)["ready"]:
                self.ipa2 = (reg.load(ipa2_id)[0], reg.metadata(ipa2_id))
        except Exception:
            self.ipa2 = None
        self.inpaint_wf = None
        try:
            if reg.preflight(inpaint_id)["ready"]:
                self.inpaint_wf = (reg.load(inpaint_id)[0], reg.metadata(inpaint_id))
        except Exception:
            self.inpaint_wf = None
        self.sdxl_controlnet = None
        try:
            if reg.preflight(controlnet_id)["ready"]:
                self.sdxl_controlnet = (reg.load(controlnet_id)[0], reg.metadata(controlnet_id))
        except Exception:
            self.sdxl_controlnet = None
        self.controlnet_ready = self.sdxl_controlnet is not None
        matting_id = "anime_alpha_matting"
        self.matting_wf = None
        try:
            if reg.preflight(matting_id)["ready"]:
                self.matting_wf = (reg.load(matting_id)[0], reg.metadata(matting_id))
        except Exception:
            self.matting_wf = None
        self.matting_ready = self.matting_wf is not None

    @functools.cached_property
    def art(self) -> ArtEngine:
        """The central engine. Built on first use so a runner assembled without __init__ (tests, tools) still has one."""
        return ArtEngine(self.client)

    def _upload_bytes(self, data: bytes, suffix: str = ".png") -> str:
        """Upload raw image bytes into ComfyUI's input folder."""
        import urllib.request

        digest = hashlib.sha256(data).hexdigest()
        name, boundary = f"pf_{digest[:16]}{suffix}", "pfboundary" + digest[:8]
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n").encode()
        tail = (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n").encode()
        req = urllib.request.Request(self.client.base_url + "upload/image", data=head + data + tail,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["name"]

    def _upload(self, path: Path) -> str:
        """Copy a reference image into ComfyUI's input folder (name derived from content, so reruns reuse it)."""
        return self._upload_bytes(path.read_bytes())

    def _resolve_upload(self, item: Path | str | bytes | Image.Image | None) -> str | None:
        """Resolve conditioning or reference input into an uploaded ComfyUI image filename."""
        if item is None:
            return None
        if isinstance(item, Image.Image):
            buf = io.BytesIO()
            item.save(buf, format="PNG")
            return self._upload_bytes(buf.getvalue())
        if isinstance(item, bytes):
            return self._upload_bytes(item)
        if isinstance(item, Path):
            return self._upload(item)
        if isinstance(item, str):
            p = Path(item)
            try:
                if p.exists() and p.is_file():
                    return self._upload(p)
            except OSError:
                pass
            return item
        return str(item)

    def inpaint(self, base_image: Path | bytes, mask_image: Path | bytes, prompt: str, neg: str, seed: int,
                denoise: float = 0.75, timeout: float = 300.0,
                is_cancelled: Callable[[], bool] = lambda: False, **kw) -> bytes:
        if self.inpaint_wf is None:
            raise RuntimeError("ComfyUI inpainting workflow anime_sdxl_inpaint is not available")
        if isinstance(base_image, Path):
            ref_name = self._upload(base_image)
        elif isinstance(base_image, bytes):
            ref_name = self._upload_bytes(base_image)
        else:
            raise TypeError(f"Unsupported base_image type: {type(base_image)}")

        if isinstance(mask_image, Path):
            mask_name = self._upload(mask_image)
        elif isinstance(mask_image, bytes):
            mask_name = self._upload_bytes(mask_image)
        else:
            raise TypeError(f"Unsupported mask_image type: {type(mask_image)}")

        wf = _patch_workflow(
            self.inpaint_wf[0],
            self.inpaint_wf[1]["patch_slots"],
            prompt=prompt,
            negative_prompt=neg,
            width=0,
            height=0,
            seed=seed,
            prefix="panelflow_inpaint",
            reference_image=ref_name,
            mask_image=mask_name,
            denoise=denoise,
        )
        return self.art.run(wf, timeout=timeout, is_cancelled=is_cancelled)[0]

    def generate(self, pos: str, neg: str, seed: int, width: int, height: int, prefix: str, timeout: float = 300.0,
                 is_cancelled: Callable[[], bool] = lambda: False, reference: Path | None = None,
                 reference_b: Path | None = None, reference_weight: float | None = None,
                 pose_image: Path | str | bytes | None = None, depth_image: Path | str | bytes | None = None,
                 pose_weight: float | None = None, depth_weight: float | None = None) -> bytes:
        has_controlnet = (pose_image is not None or depth_image is not None)
        if has_controlnet and getattr(self, "sdxl_controlnet", None) is not None:
            pose_name = self._resolve_upload(pose_image)
            depth_name = self._resolve_upload(depth_image)
            p_weight = pose_weight if pose_weight is not None else 0.75
            d_weight = depth_weight if depth_weight is not None else 0.6
            if depth_name is None and pose_name is not None:
                depth_name = pose_name
                d_weight = 0.0
            elif pose_name is None and depth_name is not None:
                pose_name = depth_name
                p_weight = 0.0
            wf = _patch_workflow(
                self.sdxl_controlnet[0],
                self.sdxl_controlnet[1]["patch_slots"],
                pos, neg, width, height, seed, prefix,
                pose_image=pose_name,
                depth_image=depth_name,
                pose_weight=p_weight,
                depth_weight=d_weight,
            )
        elif self.engine == "qwen":
            return self.art.generate(pos, neg, width, height, seed, prefix, timeout=timeout, is_cancelled=is_cancelled).png
        elif reference is not None and reference_b is not None and self.ipa2 is not None and (width, height) == (W, H):
            wf = _patch_workflow(self.ipa2[0], self.ipa2[1]["patch_slots"], pos, neg, width, height, seed, prefix,
                                 reference_image=self._upload(reference), reference_image_b=self._upload(reference_b))
        elif reference is not None and self.ipa is not None:
            wf = _patch_workflow(self.ipa[0], self.ipa[1]["patch_slots"], pos, neg, width, height, seed, prefix,
                                 reference_image=self._upload(reference), reference_weight=reference_weight)
        else:
            wf = _patch_workflow(self.workflow, self.meta["patch_slots"], pos, neg, width, height, seed, prefix)
        return self.art.run(wf, timeout=timeout, is_cancelled=is_cancelled)[0]

    def generate_turnaround(self, char: Character, story: OriginalStory, ws: Path,
                            spec: RiggingSpec | None = None) -> TurnaroundSheet:
        """Generate or retrieve a character turnaround sheet using this runner."""
        return generate_turnaround_sheet(char, story, ws, runner=self, spec=spec)

    def remove_background(
        self,
        image: Path | bytes | Image.Image | str,
        timeout: float = 120.0,
        is_cancelled: Callable[[], bool] = lambda: False,
        defringe: bool = True,
    ) -> bytes:
        """Remove background to produce transparent RGBA PNG bytes with clean alpha and zero halo."""
        from engine.original import rigging

        if getattr(self, "matting_wf", None) is not None:
            try:
                img_name = self._resolve_upload(image)
                wf = _patch_workflow(
                    self.matting_wf[0],
                    self.matting_wf[1]["patch_slots"],
                    prompt="",
                    negative_prompt="",
                    width=0,
                    height=0,
                    seed=0,
                    prefix="panelflow_alpha",
                    reference_image=img_name,
                )
                raw_png = self.art.run(wf, timeout=timeout, is_cancelled=is_cancelled)[0]
                if defringe:
                    return rigging.remove_background(raw_png, runner=None, defringe=True).rgba_bytes
                return raw_png
            except Exception:
                pass  # Fall back cleanly to local engine

        # Offline / graceful fallback to local Python engine
        result = rigging.remove_background(image, runner=None, defringe=defringe)
        return result.rgba_bytes

    def inpaint_background_plate(
        self,
        base_image: Image.Image | bytes | Path | str,
        occlusion_mask: Image.Image | bytes | Path | str,
        dilation_px: int = 12,
        prompt_hint: str = "",
    ) -> Image.Image:
        """Inpaint occluded background plate with dilated mask and hole-free guarantee."""
        from engine.original import rigging

        return rigging.inpaint_background_plate(
            base_image=base_image,
            occlusion_mask=occlusion_mask,
            runner=self,
            dilation_px=dilation_px,
            prompt_hint=prompt_hint,
        )

    def decompose_layers(
        self,
        image: Image.Image | bytes | Path | str,
        panel_id: str = "panel_0",
        prompt_hint: str = "",
    ) -> LayerStack:
        """Decompose a panel into multi-plane LayerStack using this runner for matting and inpainting."""
        from engine.original import rigging

        return rigging.decompose_layers(
            image=image,
            panel_id=panel_id,
            runner=self,
            prompt_hint=prompt_hint,
        )


class _TagCheck(BaseModel):
    tag: str
    visible: bool


class _Check(BaseModel):
    results: list[_TagCheck]


VISIBLE_TAGS = {"close": 2, "extreme_close": 2}  # tags are ordered hair, eyes, build, outfit, item: only the first ones identify
CORE_TAGS = 3  # the local vision model is too noisy on the rest (it denied a clearly visible "fox cub"), so only the core identity is checked
MAX_ATTEMPTS = 2


async def check_panel(provider, image: Path, chars: list[Character], shot: str = "medium") -> tuple[float, list[str]]:
    """Score 0..1: per expected character, the share of its look tags the vision model confirms as visible.

    One call per character with an explicit tag list: asking for per-character matches by *name* made the model answer with
    tag names instead of character names, so everything scored 0 on the first real run.
    """
    if not chars:
        return 1.0, []
    scores, missing = [], []
    for c in chars:
        tags = [t.strip() for t in c.look.split(",") if t.strip()][:VISIBLE_TAGS.get(shot, CORE_TAGS)]
        prompt = ("Look at this illustration. For each visual tag below, say whether it is clearly visible on the character "
                  f"described as '{c.name}' ({tags[0]}). Return every tag exactly as written, with visible true or false. "
                  "If the character is not in the picture, every tag is false.\nTags:\n" + "\n".join(f"- {t}" for t in tags))
        raw = await provider.analyze_vision(image, prompt, format_schema=_Check.model_json_schema(), max_tokens=600, temperature=0.0)
        try:
            res = _Check.model_validate_json(raw)
        except Exception:
            scores.append(0.0)  # an unparseable answer must not be mistaken for a pass
            continue
        seen = {r.tag.strip().lower(): r.visible for r in res.results}
        bad = [t for t in tags if not seen.get(t.lower(), False)]
        scores.append(1 - len(bad) / len(tags))
        missing += bad
    return sum(scores) / len(scores), sorted(set(missing))


POSE_WORDS = ("closed", "asleep", "sleeping", "from behind", "back to", "turned away", "facing away", "looking up", "looking down")
MATCH_THRESHOLD = 0.7
DIRECTED_ATTEMPTS = 3
POSE_WEIGHT = 0.3  # the portrait looks at the viewer with open eyes; a lower pin lets "eyes closed" or "from behind" through


def pose_sensitive(panel: Panel) -> bool:
    if panel.director:
        return shotspec.pose_sensitive(shotspec.ShotSpec(**panel.director))
    text = " ".join(panel.key_visuals + [panel.action]).lower()
    return any(w in text for w in POSE_WORDS)


async def check_match(provider, image: Path, keys: list[str]) -> tuple[float, list[str]]:
    """Share of the narration's key visuals the vision model can see (0..1) and the ones it cannot."""
    if not keys:
        return 1.0, []
    prompt = ("Look at this illustration. For each item below say whether it is clearly visible in the picture. Return every "
              "item exactly as written with visible true or false.\nItems:\n" + "\n".join(f"- {k}" for k in keys))
    raw = await provider.analyze_vision(image, prompt, format_schema=_Check.model_json_schema(), max_tokens=500, temperature=0.0)
    try:
        res = _Check.model_validate_json(raw)
    except Exception:
        return 0.0, list(keys)
    seen = {r.tag.strip().lower(): r.visible for r in res.results}
    bad = [k for k in keys if not seen.get(k.lower(), False)]
    return 1 - len(bad) / len(keys), bad


class _Judgement(BaseModel):
    score: float = Field(description="share of the required items the description shows, 0 to 1")
    missing: list[str] = Field(default_factory=list, description="required items not shown or contradicted, as short phrases")


async def describe_image(provider, image: Path) -> str:
    """What a viewer would say the picture shows: free text is something the vision model does well, unlike yes/no lists."""
    return (await provider.analyze_vision(
        image, "Describe this illustration in detail for someone who cannot see it: each character (kind of creature, hair or fur, "
        "clothes), their body pose, their facial expression and whether their eyes are open or closed, what they are doing, objects "
        "they hold, the place, the lighting and mood. Be literal, do not guess what is not visible, and use at most 90 words.", max_tokens=1000, temperature=0.0)).strip()


async def judge_shot(provider, required: str, description: str) -> tuple[float, list[str]]:
    """Text-only comparison of what the shot REQUIRES with what the picture was described as showing."""
    prompt = (f"REQUIRED in the picture:\n{required}\n\nWHAT THE PICTURE ACTUALLY SHOWS (a literal description):\n{description}\n\n"
              "Which required items are NOT shown or are contradicted by the description? Different wording for the same thing counts as shown "
              "(a fox cub is the orange fox). List only real misses, as short phrases. score = share of required items that are shown.")
    out = await provider.generate_structured(prompt, _Judgement, system_prompt="You are a strict, literal reviewer.", temperature=0.0,
                                             max_tokens=400, num_ctx=8192)
    return max(0.0, min(1.0, out.score)), [m.strip() for m in out.missing if m.strip()]


class ArtRecord(BaseModel):
    panel_id: str
    image: str
    prompt_hash: str
    seed: int
    attempts: int
    score: float | None = None
    match_score: float | None = None  # does the picture show what the narration says (described, then judged against the shot spec)
    description: str = ""  # what the accepted picture was described as showing
    status: str = ""  # accept | accept_low | needs_review | unverified (only set for directed shots)
    review: dict = Field(default_factory=dict)  # the full Review: every requirement, both witnesses, confidence, decision
    claims: list[dict] = Field(default_factory=list)  # what the narration asserts that must be visible
    missing: list[str] = Field(default_factory=list)


def _hash(pos: str, neg: str, ref: str = "", dims: tuple[int, int] | None = None) -> str:
    w, h = dims if dims else (W, H)
    return hashlib.sha256(f"{pos}\n{neg}\n{w}x{h}\n{ref}".encode()).hexdigest()[:16]


def generate_art(story: OriginalStory, ws: Path, runner: ComfyRunner, provider=None, limit: int | None = None,
                 progress: Callable[[float, str], None] = lambda p, m: None,
                 is_cancelled: Callable[[], bool] = lambda: False) -> dict:
    """Character sheets first, then panels in story order. Existing images with an unchanged prompt are reused."""
    (ws / "sheets").mkdir(parents=True, exist_ok=True)
    (ws / "panels").mkdir(exist_ok=True)
    db_path = ws / "art.json"
    db = {r["panel_id"]: ArtRecord(**r) for r in json.loads(db_path.read_text())} if db_path.exists() else {}

    def save():
        db_path.write_text(json.dumps([r.model_dump() for r in db.values()], indent=1), encoding="utf-8")

    sheet_dims = shotspec.resolve_dimensions("character_sheet", default=(832, 1216))
    for c in story.bible.characters:
        f = ws / "sheets" / f"{c.id}.png"
        if not f.exists():
            f.write_bytes(runner.generate(sheet_prompt(c, story, getattr(runner, "style", "tags")),
                                          "" if getattr(runner, "style", "tags") == "natural" else SHEET_NEGATIVE,
                                          seed_for(story, "sheet_" + c.id),
                                          sheet_dims[0], sheet_dims[1], f"sheet_{c.id}"))
    chars = {c.id: c for c in story.bible.characters}
    panels = story.panels[:limit] if limit else story.panels
    done = reused = 0
    for n, p in enumerate(panels, 1):
        if is_cancelled():
            raise RuntimeError("cancelled")
        progress(n / len(panels), f"Panel {n}/{len(panels)}")
        style, engine = getattr(runner, "style", "tags"), getattr(runner, "engine", "sdxl")
        pos, neg = build_prompt(story, p, style=style)
        shown = [chars[c] for c in p.character_ids if c in chars][:2]
        spec = shotspec.ShotSpec(**p.director) if p.director else None
        spec_shot = spec.shot if spec else p.shot
        pw, ph = shotspec.resolve_dimensions(spec_shot, num_characters=len(shown), default=(W, H))
        # the first character on screen has its face pinned to its sheet
        ref = ws / "sheets" / f"{shown[0].id}.png" if shown and getattr(runner, "ipa", None) is not None else None
        # two characters: the first is pinned to the left half, the second to the right half (needs the masked workflow)
        ref_b = ws / "sheets" / f"{shown[1].id}.png" if len(shown) == 2 and getattr(runner, "ipa2", None) is not None else None
        pose_img = None
        depth_img = None
        pose_wt = None
        depth_wt = None
        cond_sig = ""
        if spec is not None:
            cond = shotspec.compile_controlnet_conditioning(spec, (pw, ph))
            pose_raw = cond.get("pose_image")
            depth_raw = cond.get("depth_image")
            pose_wt = cond.get("pose_weight")
            depth_wt = cond.get("depth_weight")
            if pose_raw:
                if hasattr(runner, "_upload") and isinstance(pose_raw, Path):
                    pose_img = runner._upload(pose_raw)
                elif hasattr(runner, "_upload_bytes") and isinstance(pose_raw, bytes):
                    pose_img = runner._upload_bytes(pose_raw)
                elif hasattr(runner, "_upload") and isinstance(pose_raw, str) and Path(pose_raw).exists():
                    pose_img = runner._upload(Path(pose_raw))
                else:
                    pose_img = pose_raw
            if depth_raw:
                if hasattr(runner, "_upload") and isinstance(depth_raw, Path):
                    depth_img = runner._upload(depth_raw)
                elif hasattr(runner, "_upload_bytes") and isinstance(depth_raw, bytes):
                    depth_img = runner._upload_bytes(depth_raw)
                elif hasattr(runner, "_upload") and isinstance(depth_raw, str) and Path(depth_raw).exists():
                    depth_img = runner._upload(Path(depth_raw))
                else:
                    depth_img = depth_raw
            if pose_raw or depth_raw:
                cond_sig = f"|pose:{pose_raw}:{pose_wt}|depth:{depth_raw}:{depth_wt}"

        rec, img = db.get(p.id), ws / "panels" / f"{p.id}.png"
        ref_sig = engine + (ref.name if ref else "") + (ref_b.name if ref_b else "") + cond_sig
        if rec and rec.prompt_hash == _hash(pos, neg, ref_sig, dims=(pw, ph)) and img.exists():
            reused += 1
            continue
        best: tuple | None = None
        emphasis: list[str] = []
        claims: list[review_mod.Claim] = []
        if provider is not None and spec is not None and p.caption:
            try:  # the narration's own visible facts, extracted independently of the shot director
                claims = asyncio.run(review_mod.extract_claims(provider, p.caption))
            except Exception:
                claims = []
        must = [c.text for c in claims if c.critical]
        for attempt in range(DIRECTED_ATTEMPTS if p.director else MAX_ATTEMPTS):
            seed = seed_for(story, p.id, attempt)
            pos_i, _ = build_prompt(story, p, emphasis, style, must, attempt)
            if attempt >= 2 and p.director and style == "natural":
                widened_shot = {"close": "medium", "extreme_close": "medium", "medium": "wide"}.get(spec_shot, spec_shot)
                pw, ph = shotspec.resolve_dimensions(widened_shot, num_characters=len(shown), default=(W, H))
            png = runner.generate(pos_i, neg, seed, pw, ph, f"panel_{p.id}", reference=ref, reference_b=ref_b,
                                  reference_weight=POSE_WEIGHT if (pose_sensitive(p) or attempt > 0) else None,
                                  pose_image=pose_img, depth_image=depth_img,
                                  pose_weight=pose_wt, depth_weight=depth_wt)
            score, missing, match, unmatched, desc, rev = 1.0, [], 1.0, [], "", None
            if provider is not None and (shown or p.key_visuals):
                tmp = ws / "panels" / f"_try_{p.id}.png"
                tmp.write_bytes(png)
                if spec is not None:
                    try:
                        rev = asyncio.run(review_mod.review_image(provider, tmp, claims, spec, chars))
                        match, desc = rev.score, rev.description
                    except Exception as e:  # a model hiccup must not stop a whole episode: keep the picture, mark it unverified
                        desc = f"(not verified: {str(e)[:80]})"
                    if rev is not None and hasattr(runner, "inpaint") and (not rev.anatomy_passed or not rev.spatial_contact_passed or rev.defects):
                        mask = review_mod.extract_defect_mask((pw, ph), rev.items)
                        if mask is not None:
                            try:
                                pos_inpaint, neg_inpaint = review_mod.build_inpaint_correction_prompt(rev.items, pos_i)
                                buf_m = io.BytesIO()
                                mask.save(buf_m, format="PNG")
                                repaired_bytes = runner.inpaint(
                                    base_image=png,
                                    mask_image=buf_m.getvalue(),
                                    prompt=pos_inpaint,
                                    neg=neg_inpaint,
                                    seed=seed + 1,
                                    denoise=0.75,
                                )
                                base_pil = Image.open(io.BytesIO(png))
                                rep_pil = Image.open(io.BytesIO(repaired_bytes))
                                spliced_pil = review_mod.splice_repaired_image(base_pil, rep_pil, mask)
                                buf_s = io.BytesIO()
                                spliced_pil.save(buf_s, format="PNG")
                                candidate_png = buf_s.getvalue()

                                tmp_rep = ws / "panels" / f"_try_rep_{p.id}.png"
                                tmp_rep.write_bytes(candidate_png)
                                try:
                                    rep_rev = asyncio.run(review_mod.review_image(provider, tmp_rep, claims, spec, chars))
                                finally:
                                    tmp_rep.unlink(missing_ok=True)

                                score_improved = (
                                    (rep_rev.anatomy_passed and rep_rev.spatial_contact_passed and (rep_rev.score >= rev.score - 0.05))
                                    or (len(rep_rev.defects) < len(rev.defects) and rep_rev.score > rev.score)
                                )
                                if score_improved:
                                    png = candidate_png
                                    rev = rep_rev
                                    match, desc = rev.score, rev.description
                            except Exception:
                                pass  # Repair failed; keep original panel and fall back
                else:
                    if shown:
                        score, missing = asyncio.run(check_panel(provider, tmp, shown, p.shot))
                    match, unmatched = asyncio.run(check_match(provider, tmp, p.key_visuals))
                tmp.unlink(missing_ok=True)
            rank = review_mod.RANK[rev.decision] if rev is not None else (1.5 if spec is not None else (2 if match >= MATCH_THRESHOLD else 0))
            key = (rank, match)
            if best is None or key > best[0]:
                best = (key, png, seed, missing, score, match, unmatched, desc, rev)
            if provider is None or rank >= 2 or (rev is None and spec is not None):
                break  # accepted, or unverifiable (a model error): do not burn attempts on a judge that is not answering
            emphasis = (rev.missing_critical + [i.item for i in rev.items if not i.critical and i.verdict != "shown"][:2]) if rev else missing + unmatched
        key, png, seed, missing, score, match, unmatched, desc, rev = best
        img.write_bytes(png)
        status = ("" if spec is None else "unverified" if rev is None else {"accept": "accept", "accept_low": "accept_low"}.get(rev.decision, "needs_review"))
        db[p.id] = ArtRecord(panel_id=p.id, image=str(img), prompt_hash=_hash(pos, neg, ref_sig, dims=(pw, ph)),
                             seed=seed, attempts=attempt + 1, score=score if provider is not None and shown and spec is None else None,
                             match_score=match if provider is not None and (p.key_visuals or spec is not None) and (rev is not None or spec is None) else None,
                             missing=(rev.missing_critical if rev else missing + unmatched), description=desc, status=status,
                             review=rev.model_dump() if rev else {}, claims=[c.model_dump() for c in claims])
        save()
        done += 1
    scores = [r.score for r in db.values() if r.score is not None]
    recs = list(db.values())
    review_mod.write_report(panels, ws, [r.model_dump() for r in recs])
    return {"generated": done, "reused": reused, "panels": len(panels),
            "mean_score": round(sum(scores) / len(scores), 3) if scores else None,
            "mean_match": round(sum(m) / len(m), 3) if (m := [r.match_score for r in recs if r.match_score is not None]) else None,
            "accepted": [r.panel_id for r in recs if r.status == "accept"],
            "accepted_low_confidence": [r.panel_id for r in recs if r.status == "accept_low"],
            "needs_review": [r.panel_id for r in recs if r.status == "needs_review"],
            "below_threshold": [r.panel_id for r in recs if r.status == "needs_review"
                                or (not r.status and r.match_score is not None and r.match_score < MATCH_THRESHOLD)]}
