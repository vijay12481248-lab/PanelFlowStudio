import hashlib
import io
import json
from pathlib import Path
import pytest
from PIL import Image

from engine.comfyui import art as comfy_art
from engine.original import art, refine

WF_DIR = Path(comfy_art.__file__).parent
ENTRY = next(e for e in json.loads((WF_DIR / "workflow_registry.json").read_text(encoding="utf-8")) if e["id"] == art.QWEN_INPAINT_ID)
GRAPH = json.loads((WF_DIR / "workflows" / ENTRY["filename"]).read_text(encoding="utf-8"))


def _make_dummy_png(width: int = 672, height: int = 384) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class FakeArt:
    def __init__(self, out_bytes: bytes):
        self.out_bytes = out_bytes
        self.last_patched = None

    def run(self, patched, timeout=300.0, is_cancelled=lambda: False):
        self.last_patched = patched
        return [self.out_bytes], "pid", {}


def test_upscale_2x_doubles_dimensions_and_enforces_multiple_of_16():
    draft = _make_dummy_png(672, 384)
    scaled_bytes, (w, h) = refine.upscale_2x(draft)

    assert (w, h) == (1344, 768)
    assert w % 16 == 0
    assert h % 16 == 0

    img = Image.open(io.BytesIO(scaled_bytes))
    assert img.size == (1344, 768)


def test_calculate_refiner_sigmas_scheduling_and_clamping():
    # Normal schedule: steps=4 produces 5 values (start, step 1, step 2, step 3, end 0.0)
    sigmas_str = refine.calculate_refiner_sigmas(start_sigma=0.35, steps=4)
    vals = [float(v.strip()) for v in sigmas_str.split(",") if v.strip()]
    assert len(vals) == 5
    assert vals[0] == pytest.approx(0.35, abs=0.01)
    assert vals[-1] == 0.0
    # Strictly descending
    assert all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))

    # Over-clamp test: sigma > 0.40 clamped to 0.40
    over_sigmas_str = refine.calculate_refiner_sigmas(start_sigma=0.75, steps=4)
    over_vals = [float(v.strip()) for v in over_sigmas_str.split(",") if v.strip()]
    assert over_vals[0] == pytest.approx(0.40, abs=0.01)

    # Under-clamp test: sigma < 0.05 clamped to 0.05
    under_sigmas_str = refine.calculate_refiner_sigmas(start_sigma=0.01, steps=3)
    under_vals = [float(v.strip()) for v in under_sigmas_str.split(",") if v.strip()]
    assert under_vals[0] == pytest.approx(0.05, abs=0.01)


def test_scale_and_refine_panel_orchestration():
    dummy_out = _make_dummy_png(1344, 768)
    fake_art = FakeArt(dummy_out)

    r = art.ComfyRunner.__new__(art.ComfyRunner)
    r.qwen_inpaint_wf = (GRAPH, ENTRY)
    r.art = fake_art
    r._upload_bytes = lambda data, suffix=".png": "up_" + hashlib.sha256(data).hexdigest()[:8] + suffix

    draft = _make_dummy_png(672, 384)
    refined_bytes, meta = refine.scale_and_refine_panel(
        r,
        draft,
        prompt="beautiful scenery",
        neg="blurry",
        seed=42,
        sigma=0.35,
        steps=4,
    )

    assert meta["upscaled_size"] == (1344, 768)
    assert meta["refiner_sigma"] == 0.35
    assert meta["refiner_steps"] == 4
    assert meta["seed"] == 42
    assert meta["scale_factor"] == 2.0
    assert refined_bytes is not None
    assert fake_art.last_patched is not None
    assert "7" in fake_art.last_patched
    assert fake_art.last_patched["7"]["inputs"]["sigmas"].startswith("0.35")
