import base64
import json
import logging
import uuid
from pathlib import Path
from typing import Any
import httpx

from engine.ocr.providers.base import OCREngine, RawOCRResult, OCRRegion, OCRProviderStatus

logger = logging.getLogger("panelflow.ocr.vision_llm")

class VisionLLMOCREngine(OCREngine):
    """
    Multimodal Vision LLM OCR adapter supporting local Ollama (e.g. llava, llama3.2-vision)
    or any OpenAI-compatible local vision endpoint (LM Studio, vLLM).
    """

    def __init__(self, endpoint_url: str = "http://127.0.0.1:11434/api/generate", model_name: str = "llama3.2-vision"):
        self.endpoint_url = endpoint_url
        self.model_name = model_name
        self._verified = False

    @property
    def engine_id(self) -> str:
        return "vision_llm"

    @property
    def display_name(self) -> str:
        return f"Vision LLM ({self.model_name})"

    @property
    def description(self) -> str:
        return "Multimodal vision model for simultaneous text transcription and speech bubble localization."

    def is_installed(self) -> bool:
        # Check if local endpoint is reachable
        try:
            r = httpx.get(self.endpoint_url.replace("/api/generate", "/api/tags"), timeout=0.8)
            return r.status_code == 200
        except Exception:
            return False

    def is_configured(self) -> bool:
        # Check if requested model exists on backend
        try:
            r = httpx.get(self.endpoint_url.replace("/api/generate", "/api/tags"), timeout=0.8)
            if r.status_code != 200:
                return False
            data = r.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(
                self.model_name == m or m.startswith(f"{self.model_name}:")
                for m in models
            )
        except Exception:
            return False

    def is_available(self) -> bool:
        return self.is_installed() and self.is_configured()

    def is_verified(self) -> bool:
        return self._verified

    def set_verified(self, verified: bool = True) -> None:
        self._verified = verified

    def get_status(self) -> OCRProviderStatus:
        installed = self.is_installed()
        configured = self.is_configured()
        available = self.is_available()
        verified = self.is_verified()

        if verified:
            label = "Verified"
            msg = f"Vision LLM model '{self.model_name}' active and verified."
        elif available:
            label = "Available"
            msg = f"Vision LLM model '{self.model_name}' ready for inference."
        elif not installed:
            label = "Configuration required"
            msg = "Local Ollama server not responding on http://127.0.0.1:11434. Start Ollama to enable vision OCR."
        else:
            label = "Configuration required"
            msg = f"Model '{self.model_name}' not found in Ollama. Run: ollama pull {self.model_name}"

        return OCRProviderStatus(
            provider_id=self.engine_id,
            display_name=self.display_name,
            description=self.description,
            registered=True,
            installed=installed,
            configured=configured,
            is_available=available,
            is_verified=verified,
            status_label=label,
            diagnostic_message=msg,
        )

    def extract_text(
        self,
        image_path: Path,
        panel_id: str,
        language: str = "en",
        extra_options: dict[str, Any] | None = None,
    ) -> RawOCRResult:
        if not image_path.exists():
            raise FileNotFoundError(f"Target panel image not found: {image_path}")

        # Read and base64 encode
        with open(image_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            "Analyze this comic/manga panel. Extract all readable text, dialogue bubbles, and captions. "
            "Return JSON matching: {\"regions\": [{\"text\": \"...\", \"reading_order\": 1, \"bbox\": [x, y, w, h]}]}"
        )

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "images": [b64_img],
            "format": "json",
            "stream": False,
        }

        try:
            resp = httpx.post(self.endpoint_url, json=payload, timeout=45.0)
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("response", "{}")
            parsed = json.loads(response_text)
        except Exception as e:
            logger.warning(f"Vision LLM extraction failed or timed out: {e}")
            return RawOCRResult(
                panel_id=panel_id,
                engine_id=self.engine_id,
                engine_version=self.model_name,
                regions=[],
                full_text="",
                confidence_avg=0.0,
            )

        regions: list[OCRRegion] = []
        raw_regions = parsed.get("regions", [])
        for idx, item in enumerate(raw_regions, start=1):
            text = item.get("text", "").strip()
            if not text:
                continue
            bbox = item.get("bbox", [0, 0, 100, 50])
            regions.append(
                OCRRegion(
                    id=str(uuid.uuid4()),
                    panel_id=panel_id,
                    reading_order=item.get("reading_order", idx),
                    detected_text=text,
                    confidence=0.90,
                    bbox=bbox,
                    language=language,
                )
            )

        full_text = " ".join(r.detected_text for r in regions)
        avg_conf = sum(r.confidence for r in regions) / len(regions) if regions else 1.0

        return RawOCRResult(
            panel_id=panel_id,
            engine_id=self.engine_id,
            engine_version=self.model_name,
            regions=regions,
            full_text=full_text,
            confidence_avg=round(avg_conf, 3),
        )
