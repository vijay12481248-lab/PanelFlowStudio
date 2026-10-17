"""
Lightweight frame preview generator for PanelFlow Motion Director.
Uses PIL to render preview frames for inspecting camera framing without FFmpeg dependencies.
"""
from typing import Dict, Optional, Tuple
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import io

from engine.motion.models.timeline import VisualTimeline, Shot
from engine.motion.camera.interpolator import compute_pixel_crop_at_time


class MotionPreviewGenerator:
    """
    Renders development preview frames for verifying camera framing, focus, and safe margins.
    """

    def render_shot_preview(
        self,
        shot: Shot,
        source_image: Image.Image,
        t_normalized: float = 0.5,
        target_w: int = 1920,
        target_h: int = 1080,
    ) -> Image.Image:
        """
        Renders a single preview frame at time t_normalized in [0.0, 1.0] within the shot.
        """
        src_w, src_h = source_image.size

        # Compute crop box in source image space
        left, top, right, bottom = compute_pixel_crop_at_time(
            start=shot.camera_start,
            end=shot.camera_end,
            t=t_normalized,
            source_width=src_w,
            source_height=src_h,
            target_width=target_w,
            target_height=target_h,
            easing=shot.easing,
        )

        # Clamp safely
        left = max(0, min(src_w - 1, left))
        top = max(0, min(src_h - 1, top))
        right = max(left + 1, min(src_w, right))
        bottom = max(top + 1, min(src_h, bottom))

        # Crop and resize to target resolution
        cropped = source_image.crop((left, top, right, bottom))
        resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # Draw debug watermark overlay
        draw = ImageDraw.Draw(resized)
        time_sec = shot.start_time + (shot.duration * t_normalized)
        overlay_text = (
            f"Shot: {shot.shot_id} | Time: {time_sec:.2f}s | "
            f"Motion: {shot.motion_type.value} | Zoom: {shot.camera_start.zoom:.2f} -> {shot.camera_end.zoom:.2f}"
        )
        draw.rectangle([(20, 20), (700, 60)], fill=(0, 0, 0, 180))
        draw.text((30, 30), overlay_text, fill=(255, 255, 255))

        return resized

    def export_timeline_keyframes(
        self,
        timeline: VisualTimeline,
        asset_images: Dict[str, Image.Image],
        output_dir: Path,
    ) -> Dict[str, str]:
        """
        Renders start and end keyframes for all shots in the timeline and saves them as JPEG files.
        Returns map of shot_id -> saved file path.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        rendered_paths: Dict[str, str] = {}

        for shot in timeline.all_shots():
            img = asset_images.get(shot.source_asset_id)
            if not img:
                # Generate colored dummy canvas
                img = Image.new("RGB", (1920, 1080), color=(80, 100, 130))

            preview_img = self.render_shot_preview(
                shot=shot,
                source_image=img,
                t_normalized=0.5,
                target_w=timeline.target_resolution.width,
                target_h=timeline.target_resolution.height,
            )
            out_file = output_dir / f"{shot.shot_id}_preview.jpg"
            preview_img.save(out_file, format="JPEG", quality=85)
            rendered_paths[shot.shot_id] = str(out_file)

        return rendered_paths
