"""Tests for DAW Timeline Interchange: FCPXML v1.10, CMX 3600 EDL, and delivery packaging.
"""
from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.export_daw import (
    generate_cmx3600_edl,
    generate_fcpxml,
    package_daw_delivery,
)
from engine.audio.studio.plan import Cue, PlanStore
from engine.audio.studio.sources.synth import SynthProvider

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def plan_with_sourced_cues(tmp_path):
    store = PlanStore(tmp_path / "store")
    engine = AudioEngine(store, [SynthProvider()])

    video_p = tmp_path / "test_vid.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=4:r=24",
           "-f", "lavfi", "-i", "sine=frequency=300:duration=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", str(video_p)]
    subprocess.run(cmd, check=True)

    plan = engine.create_plan(video_p)
    plan.cues = [
        Cue(id="cue_01", track="dialogue", kind="speech", intent="Hello world", t_in=0.5, t_out=2.5, gain_db=-2.0, pan=-0.2),
        Cue(id="cue_02", track="sfx", kind="impact", intent="Metal hit", hit_t=1.5, gain_db=1.0, pan=0.3),
        Cue(id="cue_03", track="music", kind="riser", intent="Tension riser", hit_t=3.0),
    ]
    engine.store.save(plan)

    # Source the cues
    for c in ["cue_02", "cue_03"]:
        plan = engine.source_cue(plan.id, c, mode="auto")

    return plan


def test_generate_fcpxml_structure(plan_with_sourced_cues, tmp_path):
    out_xml = tmp_path / "test.fcpxml"
    xml_str = generate_fcpxml(plan_with_sourced_cues, out_xml)

    assert out_xml.is_file()
    assert '<?xml version="1.0"' in xml_str
    assert '<fcpxml version="1.10">' in xml_str

    # Parse and validate XML DOM
    root = ET.fromstring(xml_str)
    assert root.tag == "fcpxml"
    assert root.attrib["version"] == "1.10"

    # Resources check
    resources = root.find("resources")
    assert resources is not None
    format_elem = resources.find("format")
    assert format_elem is not None
    assert format_elem.attrib["frameDuration"] == "1/24s"

    # Assets check
    assets = resources.findall("asset")
    assert len(assets) >= 2  # At least cue_02 and cue_03 have chosen takes

    # Library / sequence check
    seq = root.find(".//sequence")
    assert seq is not None

    # Asset clips check
    gap = seq.find(".//gap")
    assert gap is not None
    clips = gap.findall("asset-clip")
    assert len(clips) >= 2

    # Check lanes and roles
    sfx_clip = next((c for c in clips if "SFX" in c.attrib["name"]), None)
    assert sfx_clip is not None
    assert sfx_clip.attrib["lane"] == "-3"
    assert sfx_clip.attrib["role"] == "effects.sfx"

    # Volume and pan adjust check
    vol = sfx_clip.find("adjust-volume")
    assert vol is not None and vol.attrib["amount"] == "1.0dB"
    pan = sfx_clip.find("adjust-pan")
    assert pan is not None and pan.attrib["amount"] == "0.30"


def test_generate_cmx3600_edl(plan_with_sourced_cues, tmp_path):
    out_edl = tmp_path / "test.edl"
    edl_str = generate_cmx3600_edl(plan_with_sourced_cues, out_edl)

    assert out_edl.is_file()
    assert "TITLE:" in edl_str
    assert "FCM:     NON-DROP FRAME" in edl_str

    # Event lines
    lines = [ln for ln in edl_str.splitlines() if ln.strip()]
    event_lines = [ln for ln in lines if ln.startswith("001") or ln.startswith("002")]
    assert len(event_lines) >= 2

    # Check track labels
    assert "* ROLE: SFX" in edl_str
    assert "* AUDIO GAIN: 1.0 dB  PAN: 0.30" in edl_str


def test_package_daw_delivery(plan_with_sourced_cues, tmp_path):
    out_dir = tmp_path / "daw_delivery"
    res = package_daw_delivery(
        plan_with_sourced_cues,
        out_dir,
        standard="youtube",
        make_zip=True,
    )

    assert out_dir.is_dir()
    files = res["files"]

    # Verify key delivery files
    expected = [
        "01_Dialogue_DX.wav",
        "02_Music_MX.wav",
        "03_SoundEffects_SFX.wav",
        "06_MusicAndEffects_ME.wav",
        "07_Master_Final.wav",
        "timeline.fcpxml",
        "timeline.edl",
        "cuesheet.json",
        "cuesheet.csv",
        "credits.txt",
        "delivery_manifest.json",
    ]
    for exp in expected:
        assert exp in files, f"Missing {exp} in DAW delivery"
        assert (out_dir / exp).is_file()

    # Verify manifest
    manifest = res["manifest"]
    assert manifest["plan_id"] == plan_with_sourced_cues.id
    assert manifest["standard"] == "youtube"
    assert manifest["sample_rate"] == 48000
    assert manifest["broadcast_compliance"]["compliant"] is True

    # Verify zip archive
    zip_path = Path(res["zip_path"])
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        for exp in expected:
            assert exp in namelist
