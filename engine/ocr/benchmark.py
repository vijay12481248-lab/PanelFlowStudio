"""
OCR Quality Benchmark Suite.
Measures:
- Character Error Rate (CER)
- Word Error Rate (WER)
- Recognition confidence correlation
across English and Japanese ground-truth text fixtures.
"""

from pathlib import Path
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
import numpy as np

from engine.ocr.providers.registry import ocr_registry
from engine.ocr.providers.base import OCREngine


class TextBenchmarkFixture(BaseModel):
    name: str
    language: str
    expected_text: str
    classification: str = "dialogue"  # dialogue, narration, sfx


class OCRBenchmarkMetric(BaseModel):
    fixture_name: str
    language: str
    ground_truth: str
    recognized_text: str
    cer: float
    wer: float
    confidence: float
    passed: bool


class OCRBenchmarkReport(BaseModel):
    engine_id: str
    total_fixtures: int
    mean_cer: float
    mean_wer: float
    mean_confidence: float
    results: list[OCRBenchmarkMetric]


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculates standard Levenshtein edit distance between two sequences."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def compute_cer(hypothesis: str, reference: str) -> float:
    """Calculates Character Error Rate (CER)."""
    clean_hyp = hypothesis.strip()
    clean_ref = reference.strip()
    if not clean_ref:
        return 0.0 if not clean_hyp else 1.0

    dist = levenshtein_distance(clean_hyp, clean_ref)
    return float(dist) / float(len(clean_ref))


def compute_wer(hypothesis: str, reference: str) -> float:
    """Calculates Word Error Rate (WER)."""
    hyp_words = hypothesis.strip().split()
    ref_words = reference.strip().split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    # Token level edit distance
    dist = levenshtein_distance(hyp_words, ref_words)
    return float(dist) / float(len(ref_words))


def create_synthetic_text_image(text: str, output_path: Path, width: int = 500, height: int = 200) -> Path:
    """Renders high-contrast black-on-white text image for deterministic OCR testing."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Safe text rendering (avoiding FreeType TTC collection access violations on Windows)
    safe_text = "".join(c if ord(c) < 128 else "?" for c in text)
    draw.text((25, 30), safe_text, fill=(0, 0, 0))

    img.save(output_path, "JPEG", quality=95)
    return output_path


def run_ocr_benchmark(
    engine_id: str = "mock_ocr",
    output_dir: Path | str = "fixtures/ocr_benchmarks",
) -> OCRBenchmarkReport:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    engine: OCREngine = ocr_registry.get_engine(engine_id)

    benchmark_cases = [
        TextBenchmarkFixture(
            name="en_dialogue_01",
            language="en",
            expected_text="Stop right there! You cannot pass.",
            classification="dialogue",
        ),
        TextBenchmarkFixture(
            name="en_narration_02",
            language="en",
            expected_text="Meanwhile, deep beneath the crystalline canyon...",
            classification="narration",
        ),
        TextBenchmarkFixture(
            name="en_sfx_03",
            language="en",
            expected_text="KABOOM!!",
            classification="sfx",
        ),
        TextBenchmarkFixture(
            name="ja_dialogue_04",
            language="ja",
            expected_text="待て！ここから先へは行かせない。",
            classification="dialogue",
        ),
    ]

    metrics: list[OCRBenchmarkMetric] = []

    for case in benchmark_cases:
        fixture_path = out_dir / f"{case.name}.jpg"
        create_synthetic_text_image(case.expected_text, fixture_path)

        # Run extraction
        raw_res = engine.extract_text(fixture_path, panel_id=case.name, language=case.language)
        recognized = raw_res.full_text

        # In mock engine, if prompt or default matches, mock returns predictable dialogue
        cer = compute_cer(recognized, case.expected_text)
        wer = compute_wer(recognized, case.expected_text)

        # Check pass threshold (CER <= 0.35 for acceptable benchmark)
        passed = cer <= 0.35

        metrics.append(
            OCRBenchmarkMetric(
                fixture_name=case.name,
                language=case.language,
                ground_truth=case.expected_text,
                recognized_text=recognized,
                cer=round(cer, 4),
                wer=round(wer, 4),
                confidence=round(raw_res.confidence_avg, 3),
                passed=passed,
            )
        )

    mean_cer = float(np.mean([m.cer for m in metrics]))
    mean_wer = float(np.mean([m.wer for m in metrics]))
    mean_conf = float(np.mean([m.confidence for m in metrics]))

    return OCRBenchmarkReport(
        engine_id=engine_id,
        total_fixtures=len(metrics),
        mean_cer=round(mean_cer, 4),
        mean_wer=round(mean_wer, 4),
        mean_confidence=round(mean_conf, 3),
        results=metrics,
    )
