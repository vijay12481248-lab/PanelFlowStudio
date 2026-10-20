from pathlib import Path
from PIL import Image, ImageOps
import hashlib
import io
import logging

from engine.imaging.normalization.base import BasePageNormalizer, NormalizationConfig

logger = logging.getLogger(__name__)

class PageNormalizer(BasePageNormalizer):
    def normalize_page(
        self,
        input_path: Path | str,
        output_path: Path | str,
        config: NormalizationConfig | None = None,
    ) -> dict:
        cfg = config or NormalizationConfig()
        in_p = Path(input_path)
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if not in_p.exists():
            raise FileNotFoundError(f"Source image not found: {in_p}")

        # Compute source sha256
        from engine.security.paths import read_contained_bytes
        src_bytes = read_contained_bytes(in_p.parent.parent, in_p)
        if len(src_bytes) == 0:
            raise ValueError(f"Source file {in_p} is zero bytes.")
        src_sha256 = hashlib.sha256(src_bytes).hexdigest()

        try:
            with Image.open(io.BytesIO(src_bytes)) as img:
                img.verify()
        except Exception as e:
            raise ValueError(f"Corrupted or invalid image at {in_p}: {e}")

        with Image.open(io.BytesIO(src_bytes)) as img:
            # 1. Correct EXIF orientation
            exif = img.getexif()
            orientation = int(exif.get(0x0112, 1)) if exif else 1
            orientation_corrected = orientation != 1
            if orientation_corrected:
                img = ImageOps.exif_transpose(img)

            orig_w, orig_h = img.size

            # 2. Check for webtoon tall aspect ratio
            aspect_ratio = float(orig_h) / float(orig_w) if orig_w > 0 else 1.0
            is_webtoon_strip = aspect_ratio >= 2.5 or orig_h >= 4000

            # 3. Handle color space & Alpha flattening
            alpha_flattened = False
            if img.mode in ("RGBA", "LA", "PA") or ("transparency" in img.info):
                alpha_flattened = True
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                bg.paste(img, mask=img.split()[-1])
                img = bg
            elif img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            else:
                img = img.convert("RGB")

            # 4. Dimension scaling (conservative, non-destructive working resolution)
            target_w = cfg.target_width
            scale_factor = target_w / float(orig_w) if orig_w > 0 else 1.0
            target_w = int(round(orig_w * scale_factor))
            target_h = int(round(orig_h * scale_factor))

            if cfg.target_height and target_h > cfg.target_height:
                target_h = cfg.target_height
                scale_factor = target_h / float(orig_h)
                target_w = int(round(orig_w * scale_factor))

            if (target_w, target_h) != (orig_w, orig_h):
                img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            # 5. Optional auto-contrast
            if cfg.auto_contrast:
                img = ImageOps.autocontrast(img, cutoff=0.5)

            # 6. Save derivative to normalized folder (source remains immutable!)
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=95, optimize=True)

        norm_bytes = buffer.getvalue()
        from engine.security.paths import open_contained_output
        with open_contained_output(out_p.parent.parent, out_p) as output:
            output.write(norm_bytes)
        norm_sha256 = hashlib.sha256(norm_bytes).hexdigest()

        operations = {
            "orientation_corrected": orientation_corrected,
            "alpha_flattened": alpha_flattened,
            "color_space": "sRGB",
            "working_scale": scale_factor,
            "is_webtoon_strip": is_webtoon_strip,
            "target_width": target_w,
            "target_height": target_h,
        }

        logger.info(f"Page normalized: {in_p.name} -> {out_p.name} operations={operations}")

        return {
            "width": target_w,
            "height": target_h,
            "source_width": orig_w,
            "source_height": orig_h,
            "scale_factor": scale_factor,
            "byte_size": len(norm_bytes),
            "sha256": norm_sha256,
            "source_sha256": src_sha256,
            "normalized_sha256": norm_sha256,
            "color_space": "sRGB",
            "orientation": orientation,
            "operations": operations,
            "status": "SUCCESS",
            "output_path": str(out_p.resolve()),
        }

page_normalizer = PageNormalizer()
