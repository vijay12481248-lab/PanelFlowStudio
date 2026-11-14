"""ChronoFlow colour grades reach the export as baked 3D LUTs (.cube) that FFmpeg's lut3d applies per clip."""
import shutil
import subprocess

import pytest

import engine.chronoflow.pipeline as pipeline_mod
from engine.chronoflow.pipeline import ChronoFlowPipeline

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")

GOOD_ID = "0123456789abcdef"


def cube(scale: float, size: int = 9) -> str:
    """A .cube table that multiplies every channel by `scale` (red varies fastest, as the format requires)."""
    rows = [f"LUT_3D_SIZE {size}"]
    for b in range(size):
        for g in range(size):
            for r in range(size):
                rows.append(" ".join(f"{(v / (size - 1)) * scale:.6f}" for v in (r, g, b)))
    return "\n".join(rows) + "\n"


@pytest.fixture()
def studio(tmp_path, monkeypatch):
    out = tmp_path / "studio"
    out.mkdir()
    for name in ("STUDIO_OUTPUT_DIR", "COMFY_OUTPUT_DIR", "COMFY_INPUT_DIR"):
        monkeypatch.setattr(pipeline_mod, name, out)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "smptebars=s=320x240:d=1.5:r=24", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-t", "1.5", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac", str(out / "bars.mp4")],
        check=True,
    )
    return out


def render(studio, clip_extra=None, luts=None):
    clip = {"filename": "bars.mp4", "in_point": 0.0, "out_point": 1.0, "speed": 1.0, "volume": 1.0, **(clip_extra or {})}
    master = studio / "master.mp4"
    master.unlink(missing_ok=True)
    result = ChronoFlowPipeline().render_timeline_edl([clip], master, None, luts)
    assert result and master.exists(), "render produced no file"
    return master


def mean_luma(video) -> float:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(video), "-frames:v", "1", "-vf", "format=gray", "-f", "rawvideo", "-"],
        check=True, capture_output=True,
    ).stdout
    assert raw, "no frame decoded"
    return sum(raw) / len(raw)


def test_a_grade_lut_changes_the_picture_by_the_amount_the_lut_says(studio):
    plain = mean_luma(render(studio))
    half = mean_luma(render(studio, {"lut": GOOD_ID}, {GOOD_ID: cube(0.5)}))
    assert 0.35 * plain < half < 0.65 * plain, f"half-brightness LUT gave {half:.1f} from {plain:.1f}"


def test_an_identity_lut_leaves_the_picture_alone(studio):
    plain = mean_luma(render(studio))
    same = mean_luma(render(studio, {"lut": GOOD_ID}, {GOOD_ID: cube(1.0)}))
    assert abs(same - plain) < 4, f"identity LUT moved brightness {plain:.1f} -> {same:.1f}"


def test_a_clip_naming_an_unknown_grade_renders_ungraded(studio):
    plain = mean_luma(render(studio))
    other = mean_luma(render(studio, {"lut": "ffffffffffffffff"}, {GOOD_ID: cube(0.5)}))
    assert abs(other - plain) < 4


def test_bad_grade_input_is_refused_not_rendered(studio):
    with pytest.raises(ValueError, match="invalid grade id"):
        render(studio, None, {"../evil": cube(1.0)})
    with pytest.raises(ValueError, match="not a usable .cube"):
        render(studio, None, {GOOD_ID: "hello"})
    with pytest.raises(ValueError, match="not a usable .cube"):
        render(studio, None, {GOOD_ID: "LUT_3D_SIZE 2\n" + "0 0 0\n" * 1_000_000})   # 6 MB, over the 4 MB cap
    assert not list(studio.glob("timeline_tmp_*")), "temp folder left behind after a refused grade"
