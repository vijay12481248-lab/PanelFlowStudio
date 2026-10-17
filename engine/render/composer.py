"""
Frame composition and visual rendering pipeline for PanelFlow Production Renderer.
Renders deterministic, broadcast-quality RGB frames from RenderPlan instructions.
"""
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

from engine.motion.camera.interpolator import interpolate_camera
from engine.motion.models.camera import CameraState, NormalizedRect
from engine.motion.models.enums import MotionType, EasingFunction, EffectType, TransitionType, LayerType
from engine.motion.models.effects import EffectInstruction
from engine.motion.models.transitions import TransitionInstruction
from engine.motion.models.cues import CaptionCue
from engine.render.models.render_plan import RenderPlan, RenderShotPlan
from engine.render.models.enums import ScalePolicy, BackgroundFillPolicy
from engine.render.clock import RenderFrameClock


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

        l_px, t_px, r_px, b_px = vis_rect.to_pixel_box(src_w, src_h)

        # 3. Clamp pixel bounds safely
        l_px = max(0, min(src_w - 1, l_px))
        t_px = max(0, min(src_h - 1, t_px))
        r_px = max(l_px + 1, min(src_w, r_px))
        b_px = max(t_px + 1, min(src_h, b_px))

        cropped = source_img.crop((l_px, t_px, r_px, b_px))

        # 4. Fit cropped view onto target canvas according to scale policy
        if shot_plan.scale_policy == ScalePolicy.COVER:
            # Scale to fill entire target canvas cleanly
            fitted = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
            return fitted

        elif shot_plan.scale_policy == ScalePolicy.CONTAIN:
            # Maintain aspect ratio, letterbox / pillarbox if needed
            crop_w, crop_h = cropped.size
            crop_aspect = crop_w / max(1, crop_h)

            if crop_aspect >= target_aspect:
                scaled_w = target_w
                scaled_h = int(round(target_w / crop_aspect))
            else:
                scaled_h = target_h
                scaled_w = int(round(target_h * crop_aspect))

            scaled_img = cropped.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

            # Create canvas with background fill policy
            canvas = self._create_background_fill(source_img, shot_plan.fill_policy, target_w, target_h)
            paste_x = (target_w - scaled_w) // 2
            paste_y = (target_h - scaled_h) // 2
            canvas.paste(scaled_img, (paste_x, paste_y))
            return canvas

        else:  # SMART_CROP
            return cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)

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

        # Use default bitmap font with clean spacing
        font = ImageFont.load_default()

        # Combine text of active cues
        for cap in active_captions:
            raw_text = cap.text.strip()
            if not raw_text:
                continue

            # Word wrap text for readability
            max_chars_per_line = max(30, int(target_w / 28))
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

            # Bottom-safe positioning
            line_height = 24
            total_text_h = len(lines) * line_height
            bottom_margin = int(target_h * 0.10)
            box_bottom = target_h - bottom_margin
            box_top = box_bottom - total_text_h - 16

            max_line_w = max(len(ln) * 9 for ln in lines)
            box_w = max_line_w + 32
            box_left = (target_w - box_w) // 2
            box_right = box_left + box_w

            # Semi-transparent dark pill background for guaranteed contrast
            draw.rounded_rectangle(
                [(box_left, box_top), (box_right, box_bottom)],
                radius=8,
                fill=(0, 0, 0, 185),
                outline=(255, 255, 255, 40),
                width=1,
            )

            # Render text lines with crisp shadow
            for idx, ln in enumerate(lines):
                text_y = box_top + 8 + (idx * line_height)
                text_x = (target_w - (len(ln) * 9)) // 2
                # Shadow
                draw.text((text_x + 1, text_y + 1), ln, font=font, fill=(0, 0, 0, 240))
                # Foreground
                draw.text((text_x, text_y), ln, font=font, fill=(255, 255, 255, 255))

        return out


class FrameComposer:
    """
    Main frame synthesis engine. Combines camera views, parallax, effects, transitions, and captions.
    """

    def __init__(self):
        self.camera_renderer = CameraRenderer()
        self.effect_renderer = EffectRenderer()
        self.caption_renderer = CaptionRenderer()
        self.clock = RenderFrameClock(fps=30)
        self._image_cache: Dict[str, Image.Image] = {}

    def get_source_image(self, file_path: str, target_w: int, target_h: int) -> Image.Image:
        if file_path in self._image_cache:
            return self._image_cache[file_path]

        p = Path(file_path)
        if p.exists() and p.is_file():
            img = Image.open(p).convert("RGB")
        else:
            # Fallback canvas if missing
            img = Image.new("RGB", (target_w, target_h), color=(40, 50, 70))

        self._image_cache[file_path] = img
        return img

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

        # 1. Locate active shot in plan
        shot = plan.find_shot_at_frame(frame_index)
        if not shot:
            return Image.new("RGB", (target_w, target_h), color=(0, 0, 0))

        # 2. Normalized progress t in shot
        t_normalized = self.clock.normalized_progress(frame_index, shot.start_frame, shot.end_frame)

        # 3. Load source asset
        source_img = self.get_source_image(shot.source_asset_path, target_w, target_h)

        # 4. Render camera framing
        canvas = self.camera_renderer.render_camera_view(
            source_img=source_img,
            shot_plan=shot,
            t_normalized=t_normalized,
            target_w=target_w,
            target_h=target_h,
        )

        # 5. Handle Transition In (e.g. Cross Dissolve from previous shot)
        if shot.transition_in.transition_type == TransitionType.CROSS_DISSOLVE and shot.transition_in.duration_sec > 0:
            trans_dur_frames = self.clock.time_to_frame(shot.transition_in.duration_sec)
            frames_since_start = frame_index - shot.start_frame
            if 0 <= frames_since_start < trans_dur_frames and shot.sequence_global > 1:
                # Find previous shot
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

        # 6. Apply Active Effects (Impact shake, flash, vignette)
        if shot.effects:
            canvas = self.effect_renderer.apply_effects(
                canvas=canvas,
                effects=shot.effects,
                timestamp_sec=timestamp_sec,
                target_w=target_w,
                target_h=target_h,
            )

        # 7. Render Captions
        if shot.captions:
            canvas = self.caption_renderer.render_captions(
                canvas=canvas,
                captions=shot.captions,
                timestamp_sec=timestamp_sec,
                target_w=target_w,
                target_h=target_h,
            )

        return canvas
