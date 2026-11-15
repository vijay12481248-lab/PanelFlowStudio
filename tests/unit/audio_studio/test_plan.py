import pytest

from engine.audio.studio.licence import licence_allowed
from engine.audio.studio.plan import PlanStore, SoundPlan, snap


@pytest.mark.parametrize("lic", ["cc0", "CC0", "cc0-1.0", "pdm", "CC0 1.0"])
def test_licence_allowed_cc0_always(lic):
    assert licence_allowed(lic, False) and licence_allowed(lic, True)


def test_licence_cc_by_only_when_flag():
    for lic in ("by", "cc-by", "CC-BY-4.0"):
        assert licence_allowed(lic, False) is False
        assert licence_allowed(lic, True) is True


@pytest.mark.parametrize("lic", ["by-nc", "cc-by-nc-sa", "CC-BY-NC-4.0", "unknown", "", None, "by-sa"])
def test_licence_refuses_nc_unknown_empty(lic):
    assert licence_allowed(lic, True) is False


def test_snap_29_97():
    assert snap(1.0, 29.97) == pytest.approx(30 / 29.97)
    assert snap(0.0, 24) == 0.0


def test_store_roundtrip_bumps_version(tmp_path):
    store = PlanStore(tmp_path)
    plan = store.create("clip.mp4", fps=24.0, duration=10.0)
    assert plan.version == 0
    saved = store.save(plan)
    saved2 = store.save(saved, note="again")
    assert saved2.version == 2
    assert store.load(plan.id) == saved2
    assert isinstance(saved2, SoundPlan)


@pytest.mark.parametrize("bad", ["../x", "a/b", "", "a\b", "x" * 65])
def test_store_rejects_bad_ids(tmp_path, bad):
    with pytest.raises(ValueError):
        PlanStore(tmp_path).load(bad)
    with pytest.raises(ValueError):
        PlanStore(tmp_path).take_dir(bad)


def test_default_tracks_and_ducking(tmp_path):
    plan = PlanStore(tmp_path).create("clip.mp4", fps=24.0, duration=5.0)
    roles = {t.id: t for t in plan.tracks}
    assert set(roles) == {"dialogue", "music", "sfx", "ambience", "foley"}
    assert roles["music"].duck_under == "dialogue"
    assert roles["sfx"].duck_under is None
