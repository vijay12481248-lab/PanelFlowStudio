import pytest

from engine.narration.artifacts import BibleCharacter, BibleLocation, BibleProposal, SeriesBible
from engine.narration.bible.store import BibleStore, apply_proposals, series_key_for


@pytest.mark.parametrize("title,meta,key", [
    ("Magic Emperor - Chapter 927 - Twisted Reality", {}, "magic-emperor"),
    ("Anything", {"series_title": "Tales Of Demons And Gods"}, "tales-of-demons-and-gods"),
    ("Log Into The Future - CHAPTER 5", None, "log-into-the-future"),
])
def test_series_key_for(title, meta, key):
    assert series_key_for(title, meta) == key


def test_load_missing_returns_empty_v0(tmp_path):
    assert BibleStore(tmp_path).load("x") == SeriesBible(series_key="x")


def test_default_root_resolved_at_construction(tmp_path, monkeypatch):
    from engine.config.settings import settings
    monkeypatch.setattr(settings, "app_data_dir", tmp_path)
    assert BibleStore().root == tmp_path / "series"


def test_save_bumps_version_and_keeps_history(tmp_path):
    store = BibleStore(tmp_path)
    b = store.save(store.load("s"), "proj-1", ["a"])
    assert b.version == 1
    store.save(b, "proj-2", ["b"])
    loaded = store.load("s")
    assert loaded.version == 2
    assert (tmp_path / "s" / "bible.v1.json").exists()
    assert (tmp_path / "s" / "bible.v2.json").exists()
    assert loaded.history[-1].project_id == "proj-2"
    assert len(loaded.history) == 2


def _prop(kind, **payload):
    return BibleProposal(kind=kind, payload=payload)


def test_apply_add_character_skips_duplicate_names():
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Yulin")])
    out, applied = apply_proposals(bible, [
        _prop("add_character", id="c2", name="yulin"),
        _prop("add_character", id="c3", name="Feiyun"),
        _prop("add_character", name="NoId"),
    ])
    assert [c.name for c in out.characters] == ["Yulin", "Feiyun"]
    assert len(applied) == 1 and "Feiyun" in applied[0]
    assert len(bible.characters) == 1  # input not mutated


def test_apply_add_location_skips_duplicates():
    bible = SeriesBible(series_key="s", locations=[BibleLocation(id="l1", name="Keep")])
    out, applied = apply_proposals(bible, [
        _prop("add_location", id="l2", name="KEEP"),
        _prop("add_location", id="l3", name="Cave"),
    ])
    assert [l.name for l in out.locations] == ["Keep", "Cave"]
    assert len(applied) == 1


def test_apply_update_plot_over_150_words_is_skipped():
    bible = SeriesBible(series_key="s", plot_so_far="old")
    out, applied = apply_proposals(bible, [_prop("update_plot", plot_so_far=" ".join(["w"] * 151))])
    assert out.plot_so_far == "old" and applied == []
    out, applied = apply_proposals(bible, [_prop("update_plot", plot_so_far="new")])
    assert out.plot_so_far == "new" and len(applied) == 1


def test_apply_threads_add_and_close():
    bible = SeriesBible(series_key="s")
    out, applied = apply_proposals(bible, [
        _prop("add_thread", text="Who stole the sword?"),
        _prop("close_thread", text="Who stole the sword?"),
    ])
    assert out.open_threads == [] and len(applied) == 2

@pytest.mark.parametrize("bad", [None, 5, "", "  "])
def test_apply_threads_skip_non_string_or_blank_text(bad):
    bible = SeriesBible(series_key="s", open_threads=["keep"])
    out, applied = apply_proposals(bible, [
        _prop("add_thread", text=bad),
        _prop("close_thread", text=bad),
    ])
    assert out.open_threads == ["keep"] and applied == []


def test_store_rejects_path_escaping_keys(tmp_path):
    store = BibleStore(tmp_path)
    with pytest.raises(ValueError):
        store.load("../x")
    with pytest.raises(ValueError):
        store.save(SeriesBible(series_key="../x"), "p", [])

def test_apply_add_character_accepts_cluster_unknown_ids():
    out, applied = apply_proposals(SeriesBible(series_key="s"), [
        BibleProposal(kind="add_character", payload={"id": "c_1", "name": "Mask", "unknown_ids": ["unknown_1"]})])
    assert [c.id for c in out.characters] == ["c_1"] and applied == ["add_character: Mask"]


def test_store_key_must_fully_match(tmp_path):
    with pytest.raises(ValueError):
        BibleStore(tmp_path).load("abc\n")


@pytest.mark.parametrize("title,key", [
    ("Magic Emperor Chapter 927", "magic-emperor"),
    ("Magic Emperor - Ch. 12", "magic-emperor"),
    ("Log Into The Future Episode 5", "log-into-the-future"),
    ("Solo Leveling", "solo-leveling"),
    ("Return of the Mount Hua Sect - chapter 3", "return-of-the-mount-hua-sect"),
])
def test_series_key_for_chapter_variants(title, key):
    assert series_key_for(title, None) == key
