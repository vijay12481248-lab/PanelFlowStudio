import subprocess
from pathlib import Path

import pytest

from engine.imaging.content_cleanup import CleanupRules
from engine.ocr.providers.base import OCRRegion, RawOCRResult
from engine.render import promo_gate
from engine.render.encoder import FFmpegEncoder

FFMPEG = FFmpegEncoder().ffmpeg_path


class FrameOCR:
    engine_id = "test_frames"

    def is_available(self):
        return True

    def extract_text(self, path, panel_id):
        text = "MANHUAPLU5.COM" if Path(path).stem == "f_00002" else "Run away!"
        return RawOCRResult(panel_id=panel_id, engine_id=self.engine_id,
                            regions=[OCRRegion(id="r", detected_text=text, confidence=0.9, bbox=[1, 1, 50, 10])])


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_gate_reports_promotion_with_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(promo_gate, "load_rules", CleanupRules)
    video = tmp_path / "v.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x240:d=3", "-r", "10",
                    str(video)], check=True)
    hits = promo_gate.scan_video_for_promotion(video, ocr_engine=FrameOCR())
    assert [(h["time_sec"], h["text"]) for h in hits] == [(1.0, "MANHUAPLU5.COM")]
    assert "0:01.0" in promo_gate.describe_hits(hits)
