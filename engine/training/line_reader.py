"""Read one line of comic lettering with a fine-tuned TrOCR model (trained by scripts/ocr_train/train_trocr.py)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 384


def preprocess(image: Image.Image) -> np.ndarray:
    """TrOCR input: the line squeezed to 384x384, scaled to [-1, 1], channels first."""
    arr = np.asarray(image.convert("RGB").resize((SIZE, SIZE), Image.BICUBIC), dtype=np.float32) / 255.0
    return ((arr - 0.5) / 0.5).transpose(2, 0, 1)


class LineReader:
    def __init__(self, model_dir: Path | None = None, device: str | None = None, *, model=None, tokenizer=None):
        """Load from a saved folder, or wrap a model already in memory (training scores itself without a second copy)."""
        import torch
        from transformers import AutoTokenizer, VisionEncoderDecoderModel
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = model if model is not None else VisionEncoderDecoderModel.from_pretrained(str(model_dir)).to(self.device).eval()
        self.tokenizer = tokenizer if tokenizer is not None else AutoTokenizer.from_pretrained(str(model_dir))

    def read_batch(self, images: list[Image.Image], beams: int = 4) -> list[str]:
        if not images:
            return []
        torch = self.torch
        x = torch.from_numpy(np.stack([preprocess(im) for im in images])).to(self.device)
        with torch.inference_mode(), torch.autocast(self.device, dtype=torch.bfloat16, enabled=self.device == "cuda"):
            ids = self.model.generate(pixel_values=x, max_new_tokens=48, num_beams=beams)
        return [t.strip() for t in self.tokenizer.batch_decode(ids, skip_special_tokens=True)]

    def read(self, image: Image.Image) -> str:
        return self.read_batch([image])[0]
