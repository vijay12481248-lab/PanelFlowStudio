import subprocess

import pytest

from engine.acquisition.rights.models import RightsDeclaration, RightsStatus
from engine.anime.review import analysis, ingest

OK = RightsDeclaration(status=RightsStatus.COMMENTARY_REVIEW, permission_notes="Critical review with commentary")


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    d = tmp_path_factory.mktemp("clip")
    srt = d / "s.srt"
    srt.write_text("1\n00:00:00,500 --> 00:00:02,000\nHe draws the sword.\n\n2\n00:00:04,000 --> 00:00:05,500\n<i>Run!</i>\n")
    out = d / "ep.mkv"
    # three flat colour shots of 2s each -> two hard cuts, plus a tone and an embedded subtitle stream
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=red:s=640x360:d=2,format=yuv420p",
                    "-f", "lavfi", "-i", "color=blue:s=640x360:d=2,format=yuv420p",
                    "-f", "lavfi", "-i", "color=green:s=640x360:d=2,format=yuv420p",
                    "-f", "lavfi", "-i", "sine=f=440:d=6", "-i", str(srt),
                    "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a", "-map", "4:s",
                    "-c:v", "libx264", "-c:a", "aac", "-c:s", "srt", str(out)], check=True, capture_output=True)
    return out


def test_unknown_rights_refused_before_any_work(clip, tmp_path):
    with pytest.raises(ValueError, match="UNKNOWN"):
        ingest.ingest(str(clip), tmp_path / "ws", RightsDeclaration())
    assert not (tmp_path / "ws").exists()


def test_commentary_basis_needs_notes(clip, tmp_path):
    with pytest.raises(ValueError, match="permission_notes"):
        ingest.ingest(str(clip), tmp_path / "ws", RightsDeclaration(status=RightsStatus.COMMENTARY_REVIEW))


def test_rejects_non_video(tmp_path):
    f = tmp_path / "x.mp4"
    f.write_text("not video")
    with pytest.raises(ValueError):
        ingest.ingest(str(f), tmp_path / "ws", OK)


def test_ingest_and_analyze(clip, tmp_path):
    rec = ingest.ingest(str(clip), tmp_path / "ws", OK, title="Test Ep")
    assert rec.duration_sec == pytest.approx(6, abs=0.2) and rec.has_audio and rec.rights.status == RightsStatus.COMMENTARY_REVIEW
    a = analysis.analyze(rec, tmp_path / "ws", use_asr=False)
    assert [round(s.start) for s in a.shots] == [0, 2, 4]
    assert a.transcript_source == "embedded_subs"
    assert [s.text for s in a.transcript] == ["He draws the sword.", "Run!"]
    assert (tmp_path / "ws" / "analysis.json").exists()


def test_srt_parse_strips_markup():
    segs = analysis.parse_srt("1\n00:00:01,000 --> 00:00:02,500\n<i>Hi</i> {\an8}there\n")
    assert segs[0].text == "Hi there" and segs[0].end == 2.5
