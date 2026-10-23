"""
Frame composition and visual rendering pipeline for PanelFlow Production Renderer.
Renders deterministic, broadcast-quality RGB frames from RenderPlan instructions.
"""
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import math
from collections import OrderedDict
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops, ImageOps, ImageColor

from engine.motion.camera.interpolator import interpolate_camera
from engine.motion.models.camera import CameraState, NormalizedRect
from engine.motion.models.enums import MotionType, EasingFunction, EffectType, TransitionType, LayerType
from engine.motion.models.effects import EffectInstruction
from engine.motion.models.transitions import TransitionInstruction
from engine.motion.models.cues import CaptionCue
from engine.render.models.render_plan import RenderPlan, RenderShotPlan
from engine.render.models.enums import ScalePolicy, BackgroundFillPolicy
from engine.render.clock import RenderFrameClock
from engine.render.models.background import BackgroundSettings


def crop_layer_source(source: Image.Image, layer: Dict[str, Any]) -> Image.Image:
    """Crop once, before either branch; extracted panel files already contain their crop."""
    crop = layer.get("crop")
    if layer.get("already_cropped") or not isinstance(crop, dict):
        return source
    x, y = float(crop.get("x", 0)), float(crop.get("y", 0))
    w, h = float(crop.get("width", 0)), float(crop.get("height", 0))
    if w <= 0 or h <= 0:
        return source
    if w <= 1 and h <= 1:
        box = (round(x * source.width), round(y * source.height), round((x + w) * source.width), round((y + h) * source.height))
    else:
        box = (round(x), round(y), round(x + w), round(y + h))
    box = (max(0, box[0]), max(0, box[1]), min(source.width, box[2]), min(source.height, box[3]))
    return source.crop(box) if box[2] > box[0] and box[3] > box[1] else source


def background_sigma(sigma_1080: float, width: int, height: int) -> float:
    """CSS-equivalent sigma normalized against the output height at 1080p."""
    return sigma_1080 * height / 1080.0


def build_background(source: Optional[Image.Image], settings: BackgroundSettings,
                     size: Tuple[int, int], progress: float = 0, occupies_canvas: Optional[bool] = None) -> Image.Image:
    """Pure canvas fill builder. Never reads a composed frame, captions, or scene camera."""
    w, h = size
    base = Image.new("RGBA", size, settings.color)
    preset = settings.preset
    if preset == "none":
        return base
    derived = preset in ("duplicate_blur", "mirror", "edge_stretch", "gradient")
    if occupies_canvas is None:
        occupies_canvas = (source is not None and abs(source.width / source.height - w / h) < .001)
    if derived and source is not None and settings.auto_only_when_needed and occupies_canvas:

        return base
    if preset == "gradient":
        first = np.array(ImageColor.getrgb(settings.color), dtype=np.float32)
        second = np.array(ImageColor.getrgb(settings.color_secondary), dtype=np.float32)
        t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
        rows = (first[None, None, :] * (1 - t) + second[None, None, :] * t).astype(np.uint8)
        fill = Image.fromarray(np.repeat(rows, w, axis=1)).convert("RGBA")
    elif preset == "solid" or source is None:
        fill = Image.new("RGBA", size, settings.color)
    else:
        zoom, fx = settings.zoom, settings.focal_x
        if settings.motion == "slow_zoom":
            zoom *= 1 + settings.motion_amount * progress
        elif settings.motion in ("pan_left", "pan_right"):
            zoom *= 1 + settings.motion_amount
            sign = 1 if settings.motion == "pan_right" else -1
            fx = max(0, min(1, fx + sign * settings.motion_amount * (progress - .5)))
        if preset == "edge_stretch":
            sw, sh = max(w, round(w * zoom)), max(h, round(h * zoom))
        else:
            scale = max(w / source.width, h / source.height) * zoom
            sw, sh = max(w, round(source.width * scale)), max(h, round(source.height * scale))
        fill = source.resize((sw, sh), Image.Resampling.LANCZOS)
        left, top = round((sw - w) * fx), round((sh - h) * settings.focal_y)
        fill = fill.crop((left, top, left + w, top + h))
        if preset == "mirror":
            fill = ImageOps.mirror(fill)
        # Flatten transparency before blur, so RGB in transparent PNG pixels cannot bleed.
        flat = Image.new("RGBA", size, settings.color)
        flat.alpha_composite(fill.convert("RGBA"))
        fill = flat
    sigma = background_sigma(settings.blur_sigma, w, h)
    if sigma > 0:
        fill = fill.filter(ImageFilter.GaussianBlur(sigma))
    rgb = ImageEnhance.Color(fill.convert("RGB")).enhance(settings.saturation)
    if settings.brightness:
        offset = settings.brightness * 255
        rgb = rgb.point(lambda value: max(0, min(255, round(value + offset))))
    fill = rgb.convert("RGBA")
    if settings.tint_opacity:
        fill = Image.blend(fill, Image.new("RGBA", size, settings.tint), settings.tint_opacity)
    if settings.glow:
        light = fill.filter(ImageFilter.GaussianBlur(background_sigma(40, w, h)))
        fill = Image.blend(fill, ImageChops.screen(fill, light), settings.glow)
    if settings.vignette:
        yy, xx = np.ogrid[-1:1:complex(h), -1:1:complex(w)]
        amount = np.clip((xx * xx + yy * yy) / 2, 0, 1) * settings.vignette
        dark = Image.new("RGBA", size, (0, 0, 0, 0))
        dark.putalpha(Image.fromarray((amount * 255).astype(np.uint8)))
        fill.alpha_composite(dark)
    if settings.opacity < 1.0:
        fill_r, fill_g, fill_b, fill_a = fill.split()
        fill_a = fill_a.point(lambda value: int(round(value * max(0.0, settings.opacity))))
        fill = Image.merge("RGBA", (fill_r, fill_g, fill_b, fill_a))
    base.alpha_composite(fill)
    return base


class CameraRenderer:
    """
    Renders high-quality camera pans, zooms, and crops with anti-shimmer resampling and aspect fitting.
    """

    def render_camera_view(
        self,
        source_img: Image.Image,
        shot_plan: RenderShotPlan,
        t_normalized: float,
        target_w: int,
        target_h: int,
    ) -> Image.Image:
        """
        Interpolates camera at normalized time t, crops source visual, and fits onto target canvas.
        """
        src_w, src_h = source_img.size
        target_aspect = target_w / max(1, target_h)
        src_aspect = src_w / max(1, src_h)

        # 1. Interpolate camera state
        cam_t = interpolate_camera(
            start=shot_plan.camera_start,
            end=shot_plan.camera_end,
            t=t_normalized,
            easing=shot_plan.easing,
        )

        # 2. Compute visible frustum in normalized source space
        if shot_plan.scale_policy == ScalePolicy.CONTAIN:
            base_rect = cam_t.crop or shot_plan.frame_region or NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0)
            z = max(cam_t.zoom, 0.5)
            vis_w = min(1.0, base_rect.width / z)
            vis_h = min(1.0, base_rect.height / z)
            left = max(0.0, min(1.0 - vis_w, cam_t.center_x - vis_w / 2.0))
            top = max(0.0, min(1.0 - vis_h, cam_t.center_y - vis_h / 2.0))
            vis_rect = NormalizedRect(x=round(left, 4), y=round(top, 4), width=round(vis_w, 4), height=round(vis_h, 4))
        else:
            vis_rect = cam_t.visible_rect(target_aspect=target_aspect, source_aspect=src_aspect)

        # Pillow resize accepts a floating source box. Preserve subpixel camera
        # movement instead of snapping each frame to a newly rounded pixel crop.
        l_px, t_px = vis_rect.x * src_w, vis_rect.y * src_h
        r_px, b_px = vis_rect.right * src_w, vis_rect.bottom * src_h

        # 3. Clamp pixel bounds safely
        l_px = max(0, min(src_w - 1, l_px))
        t_px = max(0, min(src_h - 1, t_px))
        r_px = max(l_px + 1, min(src_w, r_px))
        b_px = max(t_px + 1, min(src_h, b_px))

        source_box = (l_px, t_px, r_px, b_px)

        # 4. Fit cropped view onto target canvas according to scale policy
        if shot_plan.scale_policy == ScalePolicy.COVER:
            # Scale to fill entire target canvas cleanly
            fitted = source_img.resize((target_w, target_h), Image.Resampling.LANCZOS, box=source_box)
            if fitted.mode != "RGB":
                fitted = fitted.convert("RGB")
            return fitted

        elif shot_plan.scale_policy == ScalePolicy.CONTAIN:
            # Maintain aspect ratio, letterbox / pillarbox if needed
            crop_w, crop_h = r_px - l_px, b_px - t_px
            crop_aspect = crop_w / max(1, crop_h)

            if crop_aspect >= target_aspect:
                scaled_w = target_w
                scaled_h = int(round(target_w / crop_aspect))
            else:
                scaled_h = target_h
                scaled_w = int(round(target_h * crop_aspect))

            scaled_img = source_img.resize((max(1, scaled_w), max(1, scaled_h)), Image.Resampling.LANCZOS, box=source_box)

            # Create canvas with background fill policy
            canvas = self._create_background_fill(source_img, shot_plan.fill_policy, target_w, target_h)
            paste_x = (target_w - scaled_w) // 2
            paste_y = (target_h - scaled_h) // 2
            canvas.paste(scaled_img, (paste_x, paste_y))
            if canvas.mode != "RGB":
                canvas = canvas.convert("RGB")
            return canvas

        else:  # SMART_CROP
            fitted = source_img.resize((target_w, target_h), Image.Resampling.LANCZOS, box=source_box)
            if fitted.mode != "RGB":
                fitted = fitted.convert("RGB")
            return fitted

    def _create_background_fill(
        self,
        source_img: Image.Image,
        fill_policy: BackgroundFillPolicy,
        target_w: int,
        target_h: int,
    ) -> Image.Image:
        if fill_policy == BackgroundFillPolicy.BLURRED_SOURCE:
            # Blurred expansion of source image
            bg = source_img.resize((target_w, target_h), Image.Resampling.BILINEAR)
            bg = bg.filter(ImageFilter.GaussianBlur(radius=25))
            # Dim slightly to enhance contrast with foreground
            enhancer = ImageEnhance.Brightness(bg)
            return enhancer.enhance(0.5)

        elif fill_policy == BackgroundFillPolicy.SOLID_COLOR:
            return Image.new("RGB", (target_w, target_h), color=(20, 22, 28))

        else:  # BLACK
            return Image.new("RGB", (target_w, target_h), color=(0, 0, 0))


class EffectRenderer:
    """
    Applies bounded cinematic visual effects (impact shakes, flashes, vignettes, blurs).
    """

    def apply_effects(
        self,
        canvas: Image.Image,
        effects: List[EffectInstruction],
        timestamp_sec: float,
        target_w: int,
        target_h: int,
    ) -> Image.Image:
        out = canvas
        for eff in effects:
            if not (eff.start_time <= timestamp_sec <= eff.end_time):
                continue

            rel_t = (timestamp_sec - eff.start_time) / max(0.001, eff.end_time - eff.start_time)

            if eff.effect_type == EffectType.IMPACT_SHAKE:
                # Decaying sinusoidal shake
                decay = 1.0 - rel_t
                freq = eff.parameters.get("frequency_hz", 24.0)
                amp = eff.parameters.get("amplitude_px", 10.0) * eff.intensity * decay
                dx = int(round(amp * math.sin(2.0 * math.pi * freq * (timestamp_sec - eff.start_time))))
                dy = int(round((amp * 0.6) * math.cos(2.0 * math.pi * freq * (timestamp_sec - eff.start_time))))
                if dx != 0 or dy != 0:
                    out = ImageChops.offset(out, dx, dy)

            elif eff.effect_type == EffectType.FLASH:
                # Brightness/color flash fading out
                decay = 1.0 - rel_t
                alpha = int(round(255 * eff.intensity * decay))
                if alpha > 0:
                    flash_layer = Image.new("RGB", (target_w, target_h), color=(255, 255, 255))
                    out = Image.blend(out, flash_layer, alpha / 255.0)

            elif eff.effect_type == EffectType.VIGNETTE:
                # Subtle dark vignette mask
                radius = eff.parameters.get("radius", 0.75)
                out = self._apply_vignette_mask(out, intensity=eff.intensity * 0.6)

            elif eff.effect_type == EffectType.BLUR_PULSE:
                blur_rad = int(round(eff.intensity * 6.0 * (1.0 - rel_t)))
                if blur_rad > 0:
                    out = out.filter(ImageFilter.GaussianBlur(radius=blur_rad))

            elif eff.effect_type == EffectType.FOCUS_GLOW:
                # Subtle brightness boost
                boost = 1.0 + (eff.intensity * 0.25 * (1.0 - rel_t))
                enhancer = ImageEnhance.Brightness(out)
                out = enhancer.enhance(boost)

        return out

    def _apply_vignette_mask(self, img: Image.Image, intensity: float = 0.4) -> Image.Image:
        """Applies radial edge darkening."""
        w, h = img.size
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse([(-w * 0.2, -h * 0.2), (w * 1.2, h * 1.2)], fill=int(round(255 * (1.0 - intensity))))
        mask = mask.filter(ImageFilter.GaussianBlur(radius=w // 8))
        dark = Image.new("RGB", (w, h), (0, 0, 0))
        return Image.composite(img, dark, mask)


class CaptionRenderer:
    """
    Renders professional, accessible subtitles locked to approved script dialogue.
    """

    def _get_font(self, size: int = 34) -> ImageFont.ImageFont:
        for font_name in ["arial.ttf", "segoeui.ttf", "calibri.ttf", "C:/Windows/Fonts/arial.ttf"]:
            try:
                return ImageFont.truetype(font_name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _sanitize_text(self, text: str) -> str:
        replacements = {
            "\u201e": '"',
            "\u201c": '"',
            "\u201d": '"',
            "\u2018": "'",
            "\u2019": "'",
            "\u201a": "'",
            "\u2014": "--",
            "\u2013": "-",
            "\u2026": "...",
            "\u00a0": " ",
            "\ufeff": "",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text.encode("latin-1", "replace").decode("latin-1")

    def render_captions(
        self,
        canvas: Image.Image,
        captions: List[CaptionCue],
        timestamp_sec: float,
        target_w: int,
        target_h: int,
    ) -> Image.Image:
        active_captions = [c for c in captions if c.start_time <= timestamp_sec <= c.end_time]
        if not active_captions:
            return canvas

        out = canvas.copy()
        draw = ImageDraw.Draw(out, "RGBA")

        # Professional, broadcast-ready TrueType typography (scaled to resolution)
        font_size = max(24, int(target_h * 0.033))  # 35px on 1080p
        font = self._get_font(font_size)

        # Combine text of active cues
        for cap in active_captions:
            raw_text = self._sanitize_text(cap.text.strip())
            if not raw_text:
                continue

            # Word wrap text for readability (~45-50 chars per line max on 1080p)
            max_chars_per_line = max(28, int(target_w / (font_size * 0.58)))
            words = raw_text.split()
            lines = []
            curr_line = []
            curr_len = 0
            for w in words:
                if curr_len + len(w) + 1 > max_chars_per_line:
                    lines.append(" ".join(curr_line))
                    curr_line = [w]
                    curr_len = len(w)
                else:
                    curr_line.append(w)
                    curr_len += len(w) + 1
            if curr_line:
                lines.append(" ".join(curr_line))

            # Measure exact dimensions of lines
            line_bboxes = [draw.textbbox((0, 0), ln, font=font) for ln in lines]
            line_widths = [b[2] - b[0] for b in line_bboxes]
            max_line_w = max(line_widths) if line_widths else 0
            line_height = int(font_size * 1.35)
            total_text_h = len(lines) * line_height

            # Bottom-safe positioning
            bottom_margin = int(target_h * 0.08)
            box_bottom = target_h - bottom_margin
            box_h = total_text_h + 24
            box_top = box_bottom - box_h

            box_w = max_line_w + 48
            box_left = (target_w - box_w) // 2
            box_right = box_left + box_w

            # Semi-transparent dark pill background for guaranteed contrast
            draw.rounded_rectangle(
                [(box_left, box_top), (box_right, box_bottom)],
                radius=10,
                fill=(12, 16, 24, 215),
                outline=(255, 255, 255, 55),
                width=1,
            )

            # Render text lines with crisp shadow
            for idx, ln in enumerate(lines):
                lw = line_widths[idx]
                text_x = (target_w - lw) // 2
                text_y = box_top + 12 + (idx * line_height)
                try:
                    # Shadow
                    draw.text((text_x + 2, text_y + 2), ln, font=font, fill=(0, 0, 0, 240))
                    # Foreground
                    draw.text((text_x, text_y), ln, font=font, fill=(255, 255, 255, 255))
                except UnicodeEncodeError:
                    safe_ln = ln.encode("ascii", "replace").decode("ascii")
                    draw.text((text_x + 2, text_y + 2), safe_ln, font=font, fill=(0, 0, 0, 240))
                    draw.text((text_x, text_y), safe_ln, font=font, fill=(255, 255, 255, 255))
                except Exception:
                    pass

        return out


class LayerStackRenderer:
    """
    Renders multi-layer visual stack with independent crops, transforms, keyframes,
    motion presets, scene camera movement, and scene transitions, precisely matching
    the frontend animationEngine.ts and VideoCompositionCanvas.tsx.
    """

    @staticmethod
    def apply_easing(t: float, easing: str = "ease_in_out", control_points: Optional[List[float]] = None) -> float:
        clamped = max(0.0, min(1.0, float(t)))
        if easing == "linear":
            return clamped
        elif easing == "ease_in":
            return clamped * clamped
        elif easing == "ease_out":
            return clamped * (2.0 - clamped)
        elif easing == "ease_in_out":
            if clamped < 0.5:
                return 2.0 * clamped * clamped
            else:
                return -1.0 + (4.0 - 2.0 * clamped) * clamped
        elif easing == "cubic_bezier" and control_points and len(control_points) >= 4:
            p1x, p1y, p2x, p2y = control_points[:4]
            u = 1.0 - clamped
            return 3.0 * u * u * clamped * p1y + 3.0 * u * clamped * clamped * p2y + clamped * clamped * clamped
        return clamped

    @staticmethod
    def interpolate_track_keyframes(track: Dict[str, Any], time_offset_sec: float, base_value: float) -> float:
        keyframes = track.get("keyframes", [])
        if not track.get("enabled", True) or not keyframes:
            return base_value

        sorted_kfs = sorted(keyframes, key=lambda k: float(k.get("time_offset_sec", 0.0)))
        if time_offset_sec <= float(sorted_kfs[0].get("time_offset_sec", 0.0)):
            return float(sorted_kfs[0].get("value", base_value))
        if time_offset_sec >= float(sorted_kfs[-1].get("time_offset_sec", 0.0)):
            return float(sorted_kfs[-1].get("value", base_value))

        for i in range(len(sorted_kfs) - 1):
            k1 = sorted_kfs[i]
            k2 = sorted_kfs[i + 1]
            t1 = float(k1.get("time_offset_sec", 0.0))
            t2 = float(k2.get("time_offset_sec", 0.0))
            if t1 <= time_offset_sec <= t2:
                seg_dur = t2 - t1
                if seg_dur <= 0:
                    return float(k2.get("value", base_value))
                raw_p = (time_offset_sec - t1) / seg_dur
                easing = k1.get("easing", "ease_in_out")
                cps = k1.get("control_points")
                eased_p = LayerStackRenderer.apply_easing(raw_p, easing, cps)
                v1 = float(k1.get("value", base_value))
                v2 = float(k2.get("value", base_value))
                return v1 + (v2 - v1) * eased_p

        return base_value

    @classmethod
    def evaluate_layer_transform(cls, layer: Dict[str, Any], scene_dur: float, elapsed_in_scene: float) -> Dict[str, Any]:
        layer_start = float(layer.get("start_offset_sec", 0.0))
        layer_dur = float(layer.get("duration_sec", scene_dur))

        # Check active window
        is_active = (layer_start - 0.05 <= elapsed_in_scene <= layer_start + layer_dur + 0.05)
        raw_p = max(0.0, min(1.0, (elapsed_in_scene - layer_start) / max(0.001, layer_dur))) if layer_dur > 0 else 0.0

        easing = layer.get("motion_easing") or (layer.get("animation") or {}).get("easing", "ease_in_out")
        progress = cls.apply_easing(raw_p, easing)
        intensity = float((layer.get("animation") or {}).get("intensity") or layer.get("motion_intensity", 1.0))

        raw_tf = layer.get("transform", {})
        final_x = float(raw_tf.get("x", 0.0))
        final_y = float(raw_tf.get("y", 0.0))
        final_scale = float(raw_tf.get("scale", 1.0))
        final_rot = float(raw_tf.get("rotation", 0.0))
        final_op = float(raw_tf.get("opacity", 1.0))
        final_blur = 0.0

        anim_cfg = layer.get("animation") or layer.get("animation_config") or {}
        tracks_dict = anim_cfg.get("tracks") or {}
        tracks_list = list(tracks_dict.values()) if isinstance(tracks_dict, dict) else (tracks_dict if isinstance(tracks_dict, list) else [])

        if anim_cfg.get("enabled") and tracks_list:
            time_in_layer = max(0.0, min(layer_dur, elapsed_in_scene - layer_start))
            for trk in tracks_list:
                prop = trk.get("property")
                if prop == "x":
                    final_x = cls.interpolate_track_keyframes(trk, time_in_layer, final_x)
                elif prop == "y":
                    final_y = cls.interpolate_track_keyframes(trk, time_in_layer, final_y)
                elif prop == "scale":
                    final_scale = cls.interpolate_track_keyframes(trk, time_in_layer, final_scale)
                elif prop == "rotation":
                    final_rot = cls.interpolate_track_keyframes(trk, time_in_layer, final_rot)
                elif prop == "opacity":
                    final_op = cls.interpolate_track_keyframes(trk, time_in_layer, final_op)
                elif prop == "blur":
                    final_blur = cls.interpolate_track_keyframes(trk, time_in_layer, 0.0)
        else:
            preset = anim_cfg.get("preset") or layer.get("motion_preset") or "none"
            if preset == "slow_zoom_in":
                final_scale *= (1.0 + 0.16 * progress * intensity)
            elif preset == "slow_zoom_out":
                final_scale *= (1.16 - 0.16 * progress * intensity)
            elif preset == "pan_left":
                final_x += (8.0 * (0.5 - progress) * intensity)
            elif preset == "pan_right":
                final_x -= (8.0 * (0.5 - progress) * intensity)
            elif preset == "pan_up":
                final_y += (6.0 * (0.5 - progress) * intensity)
            elif preset == "pan_down":
                final_y -= (6.0 * (0.5 - progress) * intensity)
            elif preset == "diagonal_pan":
                final_x += (6.0 * (0.5 - progress) * intensity)
                final_y += (4.0 * (0.5 - progress) * intensity)
            elif preset == "slide_in_left":
                if progress < 0.4:
                    final_x -= (1.0 - progress / 0.4) * 28.0 * intensity
            elif preset == "slide_in_right":
                if progress < 0.4:
                    final_x += (1.0 - progress / 0.4) * 28.0 * intensity
            elif preset == "slide_in_top":
                if progress < 0.4:
                    final_y -= (1.0 - progress / 0.4) * 25.0 * intensity
            elif preset == "slide_in_bottom":
                if progress < 0.4:
                    final_y += (1.0 - progress / 0.4) * 25.0 * intensity
            elif preset == "slide_out_left":
                if progress > 0.6:
                    final_x -= ((progress - 0.6) / 0.4) * 30.0 * intensity
            elif preset == "slide_out_right":
                if progress > 0.6:
                    final_x += ((progress - 0.6) / 0.4) * 30.0 * intensity
            elif preset == "move_left":
                final_x -= progress * 15.0 * intensity
            elif preset == "move_right":
                final_x += progress * 15.0 * intensity
            elif preset == "move_up":
                final_y -= progress * 12.0 * intensity
            elif preset == "move_down":
                final_y += progress * 12.0 * intensity
            elif preset == "rise":
                final_y += (1.0 - progress) * 15.0 * intensity
                final_op *= min(1.0, 0.4 + 0.6 * progress)
            elif preset == "fall":
                final_y -= (1.0 - progress) * 15.0 * intensity
                final_op *= min(1.0, 0.4 + 0.6 * progress)
            elif preset == "scale_up":
                final_scale *= (0.9 + 0.25 * progress * intensity)
            elif preset == "scale_down":
                final_scale *= (1.2 - 0.25 * progress * intensity)
            elif preset == "rotate_cw":
                final_rot += progress * 15.0 * intensity
            elif preset == "rotate_ccw":
                final_rot -= progress * 15.0 * intensity
            elif preset == "fade_in":
                final_op *= (progress / 0.35 if progress < 0.35 else 1.0)
            elif preset == "fade_out":
                final_op *= (max(0.0, (1.0 - progress) / 0.35) if progress > 0.65 else 1.0)
            elif preset == "fade_in_out":
                if progress < 0.25:
                    final_op *= (progress / 0.25)
                elif progress > 0.75:
                    final_op *= max(0.0, (1.0 - progress) / 0.25)
            elif preset == "opacity_reveal":
                final_op *= (0.2 + 0.8 * progress)
                final_scale *= (0.95 + 0.05 * progress)
            elif preset == "blur":
                final_blur = (1.0 - progress) * 10.0 * intensity
            elif preset == "flash":
                if progress < 0.15:
                    final_op = 1.0
                elif progress < 0.4:
                    final_op = 0.4 + 0.6 * ((0.4 - progress) / 0.25)
            elif preset == "shake_impact":
                if progress < 0.25:
                    decay = 1.0 - progress / 0.25
                    final_x += math.sin(progress * 50.0) * 2.5 * intensity * decay
                    final_y += math.cos(progress * 50.0) * 2.5 * intensity * decay

        return {
            "x": final_x,
            "y": final_y,
            "scale": max(0.01, final_scale),
            "rotation": final_rot,
            "opacity": max(0.0, min(1.0, final_op)),
            "blur": max(0.0, final_blur),
            "is_active": is_active,
            "progress": progress,
        }

    @classmethod
    def evaluate_camera_transform(cls, cam_config: Optional[Dict[str, Any]], scene_dur: float, elapsed_in_scene: float) -> Dict[str, float]:
        if not cam_config or cam_config.get("preset") == "static":
            return {"zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0}

        dur = float(cam_config.get("duration_sec", scene_dur))
        raw_p = max(0.0, min(1.0, elapsed_in_scene / max(0.001, dur))) if dur > 0 else 0.0
        p = cls.apply_easing(raw_p, cam_config.get("easing", "ease_in_out"))
        preset = cam_config.get("preset")

        zoom = 1.0
        pan_x = 0.0
        pan_y = 0.0

        if preset == "slow_zoom_in":
            zoom = 1.0 + 0.15 * p
        elif preset == "slow_zoom_out":
            zoom = 1.15 - 0.15 * p
        elif preset == "pan_left":
            pan_x = 6.0 * (0.5 - p)
        elif preset == "pan_right":
            pan_x = -6.0 * (0.5 - p)
        elif preset == "pan_up":
            pan_y = 5.0 * (0.5 - p)
        elif preset == "pan_down":
            pan_y = -5.0 * (0.5 - p)
        elif preset == "diagonal_pan":
            pan_x = 5.0 * (0.5 - p)
            pan_y = 4.0 * (0.5 - p)
        elif preset == "custom":
            z_s = float(cam_config.get("zoom_start", 1.0))
            z_e = float(cam_config.get("zoom_end", 1.0))
            px_s = float(cam_config.get("pan_x_start", 0.0))
            px_e = float(cam_config.get("pan_x_end", 0.0))
            py_s = float(cam_config.get("pan_y_start", 0.0))
            py_e = float(cam_config.get("pan_y_end", 0.0))
            zoom = z_s + (z_e - z_s) * p
            pan_x = px_s + (px_e - px_s) * p
            pan_y = py_s + (py_e - py_s) * p

        return {"zoom": zoom, "pan_x": pan_x, "pan_y": pan_y}


class FrameComposer:
    """
    Main frame synthesis engine. Combines camera views, multi-layer stacks, parallax, effects, transitions, and captions.
    """

    def __init__(self):
        self.camera_renderer = CameraRenderer()
        self.effect_renderer = EffectRenderer()
        self.caption_renderer = CaptionRenderer()
        self.layer_renderer = LayerStackRenderer()
        self.clock = RenderFrameClock(fps=30)
        self._image_cache: Dict[str, Image.Image] = {}
        self._background_cache = OrderedDict()
        self._background_cache_bytes = 0

    def get_source_image(self, file_path: str, target_w: int, target_h: int, normalize_orientation: bool = False) -> Image.Image:
        cache_key = file_path + "|oriented" if normalize_orientation else file_path
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]

        p = Path(file_path)
        if p.exists() and p.is_file():
            with Image.open(p) as opened:
                img = (ImageOps.exif_transpose(opened) if normalize_orientation else opened).convert("RGBA")
        else:
            # Fallback canvas if missing
            img = Image.new("RGBA", (target_w, target_h), color=(40, 50, 70, 255))

        self._image_cache[cache_key] = img
        return img

    def clear_cache(self, file_path: Optional[str] = None) -> None:
        if file_path:
            self._image_cache.pop(file_path, None)
            self._image_cache.pop(file_path + "|oriented", None)
        else:
            self._image_cache.clear()
        self._background_cache.clear()
        self._background_cache_bytes = 0

    def compose_frame(
        self,
        frame_index: int,
        plan: RenderPlan,
    ) -> Image.Image:
        """
        Synthesizes a complete RGB video frame for the given discrete frame index.
        """
        target_w = plan.profile.width
        target_h = plan.profile.height
        timestamp_sec = self.clock.frame_to_time(frame_index)

        # Story Editor gaps are intentional black intervals, not held first/last shots.
        # Keep legacy motion-timeline hold behavior unchanged.
        if plan.metadata.get("compiled_from_story_editor") and not any(
            shot.start_frame <= frame_index < shot.end_frame for shot in plan.shots
        ):
            return Image.new("RGB", (target_w, target_h), color=(0, 0, 0))

        # 1. Locate active shot in plan
        shot = plan.find_shot_at_frame(frame_index)
        if not shot:
            if plan.shots:
                if frame_index < plan.shots[0].start_frame:
                    shot = plan.shots[0]
                else:
                    shot = plan.shots[-1]
            else:
                return Image.new("RGB", (target_w, target_h), color=(0, 0, 0))

        if shot.background and shot.background.enabled and shot.background.preset != "none":
            timestamp_sec = frame_index / plan.profile.fps

        # Check if shot has rich multi-layer composition
        if shot.scene_layers or (shot.background and shot.background.enabled and shot.background.preset != "none"):
            canvas = self._compose_multi_layer_shot(shot, timestamp_sec, target_w, target_h, plan)
        else:
            canvas = self._compose_legacy_camera_shot(shot, frame_index, timestamp_sec, target_w, target_h, plan)

        # Apply Captions / Subtitles if present and enabled
        if shot.captions and getattr(plan, "subtitle_enabled", False):
            canvas = self.caption_renderer.render_captions(
                canvas=canvas,
                captions=shot.captions,
                timestamp_sec=timestamp_sec,
                target_w=target_w,
                target_h=target_h,
            )

        if canvas.mode != "RGB":
            canvas = canvas.convert("RGB")
        if canvas.size != (target_w, target_h):
            canvas = canvas.resize((target_w, target_h), Image.Resampling.LANCZOS)

        return canvas

    def _compose_multi_layer_shot(
        self,
        shot: RenderShotPlan,
        timestamp_sec: float,
        target_w: int,
        target_h: int,
        plan: RenderPlan,
    ) -> Image.Image:
        """
        Renders rich multi-layer composition with independent crops, transforms, keyframes, and camera movement.
        """
        elapsed_in_scene = timestamp_sec - shot.start_time

        # Base background canvas
        canvas = Image.new("RGBA", (target_w, target_h), color=(9, 9, 11, 255))

        # Evaluate camera transform
        cam = self.layer_renderer.evaluate_camera_transform(shot.camera_config, shot.duration, elapsed_in_scene)

        # Sort layers by z_index ascending
        sorted_layers = sorted(shot.scene_layers, key=lambda l: int((l.get("transform") or {}).get("z_index", 0)))

        settings = shot.background
        smart = bool(settings and settings.enabled and settings.preset != "none")
        if smart:
            # Selection follows editor layer order, not z sorting, and uses the exact timestamp.
            source_layer = None
            for candidate in shot.scene_layers:
                if settings.source_mode == "pinned_layer" and candidate.get("id") != settings.source_layer_id:
                    continue
                if settings.source_mode == "pinned_layer" and candidate.get("disk_image_path"):
                    source_layer = candidate
                    break
                if not candidate.get("visible", True) or not candidate.get("disk_image_path"):
                    continue
                tf = self.layer_renderer.evaluate_layer_transform(candidate, shot.duration, elapsed_in_scene)
                start = float(candidate.get("start_offset_sec", 0))
                end = start + float(candidate.get("duration_sec", shot.duration))
                if start <= elapsed_in_scene < end and tf["is_active"] and tf["opacity"] > .005:
                    source_layer = candidate
                    break
            source = None
            source_key = None
            if shot.background_image_path:
                source_key = shot.background_image_path
                source = self.get_source_image(source_key, target_w, target_h, True)
            elif source_layer:
                source_key = (source_layer["disk_image_path"], str(source_layer.get("crop")), source_layer.get("already_cropped"))
                source = crop_layer_source(self.get_source_image(source_layer["disk_image_path"], target_w, target_h, True), source_layer)
            progress = max(0, min(1, elapsed_in_scene / max(.001, shot.duration)))
            occupies_canvas = False
            if source_layer and source is not None:
                source_tf = self.layer_renderer.evaluate_layer_transform(source_layer, shot.duration, elapsed_in_scene)
                aspect_matches = abs((source.width / max(1, source.height)) - (target_w / max(1, target_h))) < 0.005
                eff_scale = source_tf.get("scale", 1.0) * cam.get("zoom", 1.0)
                is_centered = (abs(source_tf.get("x", 0.0) + cam.get("pan_x", 0.0)) < 0.5
                               and abs(source_tf.get("y", 0.0) + cam.get("pan_y", 0.0)) < 0.5
                               and abs(settings.foreground_x - 0.5) < 0.005
                               and abs(settings.foreground_y - 0.5) < 0.005)
                is_unrotated = abs(source_tf.get("rotation", 0.0)) < 0.1
                is_opaque = source_tf.get("opacity", 1.0) >= 0.995
                has_alpha = False
                if source.mode in ("RGBA", "LA"):
                    extrema = source.getextrema()
                    if source.mode == "RGBA" and extrema[3][0] < 255:
                        has_alpha = True
                if aspect_matches and eff_scale >= 0.999 and is_centered and is_unrotated and is_opaque and not has_alpha:
                    occupies_canvas = True
            cache_key = (source_key, settings.model_dump_json(), target_w, target_h, occupies_canvas)
            cached = self._background_cache.get(cache_key) if settings.motion == "none" else None
            if cached is None:
                canvas = build_background(source, settings, (target_w, target_h), progress, occupies_canvas=occupies_canvas)
                if settings.motion == "none":
                    self._background_cache[cache_key] = canvas.copy()
                    self._background_cache_bytes += target_w * target_h * 4
                    while self._background_cache and (len(self._background_cache) > 8 or self._background_cache_bytes > 64 * 1024 * 1024):
                        _, evicted = self._background_cache.popitem(last=False)
                        self._background_cache_bytes -= evicted.width * evicted.height * 4
            else:
                self._background_cache.move_to_end(cache_key)
                canvas = cached.copy()

        for layer in sorted_layers:
            if layer.get("visible", True) is False:
                continue

            tf = self.layer_renderer.evaluate_layer_transform(layer, shot.duration, elapsed_in_scene)
            exact_active = float(layer.get("start_offset_sec", 0)) <= elapsed_in_scene < float(layer.get("start_offset_sec", 0)) + float(layer.get("duration_sec", shot.duration))
            if not tf["is_active"] or tf["opacity"] <= 0.005 or (smart and not exact_active):
                continue

            # Load layer source image
            img_path = layer.get("disk_image_path", "")
            if not img_path:
                continue
            src_img = self.get_source_image(img_path, target_w, target_h, smart)
            working_img = crop_layer_source(src_img, layer)

            # Base fit inside 90% of canvas
            pw, ph = working_img.size
            if pw <= 0 or ph <= 0:
                continue

            p_aspect = pw / max(1, ph)
            c_aspect = target_w / max(1, target_h)

            if smart:
                fit_scale = (max if settings.foreground_fit == "cover" else min)(target_w / pw, target_h / ph)
                base_w, base_h = pw * fit_scale, ph * fit_scale
            elif p_aspect >= c_aspect:
                base_w = target_w * 0.90
                base_h = base_w / p_aspect
            else:
                base_h = target_h * 0.90
                base_w = base_h * p_aspect

            # Apply transform scale and camera zoom
            eff_scale = tf["scale"] * cam["zoom"]
            final_w = max(1, int(round(base_w * eff_scale)))
            final_h = max(1, int(round(base_h * eff_scale)))

            scaled_img = working_img.resize((final_w, final_h), Image.Resampling.LANCZOS)

            # Apply Rotation
            if abs(tf["rotation"]) > 0.05:
                # Rotate with expansion to avoid clipping corners
                scaled_img = scaled_img.rotate(-tf["rotation"], resample=Image.Resampling.BICUBIC, expand=True)

            # Apply Blur
            if tf["blur"] > 0.5:
                scaled_img = scaled_img.filter(ImageFilter.GaussianBlur(radius=tf["blur"]))

            # Apply Opacity to Alpha
            if tf["opacity"] < 0.995:
                alpha = scaled_img.split()[-1]
                alpha = alpha.point(lambda p: int(round(p * tf["opacity"])))
                scaled_img.putalpha(alpha)

            # Placement center: 50% + offset%
            center_x = target_w * (settings.foreground_x if smart else .5) + ((tf["x"] + cam["pan_x"]) / 100.0) * target_w
            center_y = target_h * (settings.foreground_y if smart else .5) + ((tf["y"] + cam["pan_y"]) / 100.0) * target_h
            paste_x = int(round(center_x - scaled_img.width / 2.0))
            paste_y = int(round(center_y - scaled_img.height / 2.0))

            # Alpha composite onto canvas
            if smart and settings.edge_shadow:
                shadow = Image.new("RGBA", scaled_img.size, (0, 0, 0, 0))
                shadow.putalpha(scaled_img.getchannel("A").point(lambda value: round(value * settings.edge_shadow)))
                padded = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                padded.alpha_composite(shadow, (paste_x, paste_y))
                canvas.alpha_composite(padded.filter(ImageFilter.GaussianBlur(background_sigma(24, target_w, target_h))))
            canvas.alpha_composite(scaled_img, (paste_x, paste_y))

        # Scene Transitions (fade, fade_from_black, fade_to_black, impact_flash)
        trans_cfg = shot.transition_config or {}
        t_type = trans_cfg.get("type", "none")
        t_dur = float(trans_cfg.get("duration_sec", 0.5))

        if t_type and t_type not in ("none", "cut") and 0 <= elapsed_in_scene <= t_dur:
            p = elapsed_in_scene / max(0.001, t_dur)
            if t_type in ("fade", "fade_from_black"):
                overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, int(round(255 * (1.0 - p)))))
                canvas.alpha_composite(overlay)
            elif t_type == "fade_to_black":
                alpha = int(round(255 * (p * 2.0 if p < 0.5 else (1.0 - p) * 2.0)))
                overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, alpha))
                canvas.alpha_composite(overlay)
            elif t_type == "impact_flash":
                if p < 0.4:
                    alpha = int(round(255 * (1.0 - p / 0.4) * 0.8))
                    overlay = Image.new("RGBA", (target_w, target_h), (255, 255, 255, alpha))
                    canvas.alpha_composite(overlay)

        if canvas.mode != "RGB":
            canvas = canvas.convert("RGB")
        if canvas.size != (target_w, target_h):
            canvas = canvas.resize((target_w, target_h), Image.Resampling.LANCZOS)
        return canvas

    def _compose_legacy_camera_shot(
        self,
        shot: RenderShotPlan,
        frame_index: int,
        timestamp_sec: float,
        target_w: int,
        target_h: int,
        plan: RenderPlan,
    ) -> Image.Image:
        """
        Legacy fallback for single-image shots with camera pan/zoom.
        """
        if frame_index < shot.start_frame:
            t_normalized = 0.0
        elif frame_index >= shot.end_frame:
            t_normalized = 1.0
        else:
            t_normalized = self.clock.normalized_progress(frame_index, shot.start_frame, shot.end_frame)

        source_img = self.get_source_image(shot.source_asset_path, target_w, target_h)
        canvas = self.camera_renderer.render_camera_view(
            source_img=source_img,
            shot_plan=shot,
            t_normalized=t_normalized,
            target_w=target_w,
            target_h=target_h,
        )

        if shot.transition_in.transition_type == TransitionType.CROSS_DISSOLVE and shot.transition_in.duration_sec > 0:
            trans_dur_frames = self.clock.time_to_frame(shot.transition_in.duration_sec)
            frames_since_start = frame_index - shot.start_frame
            if 0 <= frames_since_start < trans_dur_frames and shot.sequence_global > 1:
                prev_shot = plan.shots[shot.sequence_global - 2]
                prev_source = self.get_source_image(prev_shot.source_asset_path, target_w, target_h)
                prev_canvas = self.camera_renderer.render_camera_view(
                    source_img=prev_source,
                    shot_plan=prev_shot,
                    t_normalized=1.0,
                    target_w=target_w,
                    target_h=target_h,
                )
                dissolve_alpha = frames_since_start / max(1, trans_dur_frames)
                canvas = Image.blend(prev_canvas, canvas, dissolve_alpha)

        if shot.effects:
            canvas = self.effect_renderer.apply_effects(
                canvas=canvas,
                effects=shot.effects,
                timestamp_sec=timestamp_sec,
                target_w=target_w,
                target_h=target_h,
            )

        if canvas.mode != "RGB":
            canvas = canvas.convert("RGB")
        if canvas.size != (target_w, target_h):
            canvas = canvas.resize((target_w, target_h), Image.Resampling.LANCZOS)

        return canvas
