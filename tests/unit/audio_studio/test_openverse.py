import json

import pytest

from engine.audio.studio.plan import Cue, PlanStore
from engine.audio.studio.sources.openverse import MAX_BYTES, OpenverseProvider


def _result(i, lic="cc0", ver="1.0", dur=2000, creator="alice"):
    return {"id": f"id{i}-xxxxxxxx", "title": f"Door {i}", "creator": creator, "license": lic, "license_version": ver,
            "url": f"https://cdn.example/{i}.mp3", "foreign_landing_url": f"https://freesound.org/s/{i}",
            "duration": dur, "provider": "freesound", "source": "freesound"}


def _fake(results, body=b"RIFFxxxx", ctype="audio/mpeg", seen=None):
    def get(url):
        if seen is not None:
            seen.append(url)
        if "api.openverse.org" in url:
            return json.dumps({"results": results}).encode(), "application/json"
        return body, ctype
    return get


@pytest.fixture
def ctx(tmp_path):
    plan = PlanStore(tmp_path).create("v.mp4", 24.0, 10.0)
    return plan, Cue(id="c1", track="sfx", kind="impact", intent="door slam"), tmp_path / "out"


def test_keeps_only_cc0_and_writes_files(ctx):
    plan, cue, out = ctx
    seen = []
    cands = OpenverseProvider(_fake([_result(1), _result(2, lic="by", ver="4.0"), _result(3, lic="by-nc", ver="4.0")], seen=seen)).find(cue, out, plan)
    assert [c.provenance.url for c in cands] == ["https://freesound.org/s/1"]
    assert all((out / c.path.split("\\")[-1].split("/")[-1]).is_file() for c in cands)
    assert any("license=cc0" in u for u in seen if "api.openverse.org" in u)


def test_cc_by_result_dropped_when_flag_off_kept_when_on(ctx):
    plan, cue, out = ctx
    data = [_result(1, lic="by", ver="4.0")]
    assert OpenverseProvider(_fake(data)).find(cue, out, plan) == []
    plan.allow_cc_by = True
    got = OpenverseProvider(_fake(data)).find(cue, out, plan)
    assert len(got) == 1 and got[0].provenance.licence.lower().startswith("by")


def test_oversize_download_rejected(ctx):
    plan, cue, out = ctx
    assert OpenverseProvider(_fake([_result(1)], body=b"x" * (MAX_BYTES + 1))).find(cue, out, plan) == []
    assert not out.exists() or not any(out.iterdir())


def test_non_audio_content_type_rejected(ctx):
    plan, cue, out = ctx
    assert OpenverseProvider(_fake([_result(1)], ctype="text/html")).find(cue, out, plan) == []
    assert not out.exists() or not any(out.iterdir())


def test_network_error_reports_unavailable(ctx):
    plan, cue, out = ctx

    def boom(url):
        raise OSError("name resolution failed")
    p = OpenverseProvider(boom)
    assert p.availability().ok is True
    assert p.find(cue, out, plan) == []
    a = p.availability()
    assert a.ok is False and "name resolution failed" in a.reason


def test_provenance_has_licence_and_url(ctx):
    plan, cue, out = ctx
    c = OpenverseProvider(_fake([_result(1)])).find(cue, out, plan)[0]
    assert c.provenance.licence.lower().startswith("cc0") and c.provenance.author == "alice"
    assert c.provenance.source == "openverse/freesound"


def test_long_clip_skipped_for_sfx_but_kept_for_ambience(ctx):
    plan, cue, out = ctx
    long = [_result(1, dur=120_000)]
    assert OpenverseProvider(_fake(long)).find(cue, out, plan) == []
    amb = Cue(id="c2", track="ambience", kind="rain", intent="rain on a window")
    assert len(OpenverseProvider(_fake(long)).find(amb, out, plan)) == 1


def test_limit_caps_candidates(ctx):
    plan, cue, out = ctx
    assert len(OpenverseProvider(_fake([_result(i) for i in range(9)])).find(cue, out, plan, limit=2)) == 2
