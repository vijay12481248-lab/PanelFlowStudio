import pytest

from engine.training.registry import ModelStore, mirror_tree


def _model(tmp_path, text="weights-1"):
    d = tmp_path / f"src-{text}"
    d.mkdir()
    (d / "model.safetensors").write_text(text)
    (d / "config.json").write_text("{}")
    return d


def _store(tmp_path):
    return ModelStore(tmp_path / "root", tmp_path / "backup")


def test_publish_versions_never_overwrite_and_mirror(tmp_path):
    s = _store(tmp_path)
    v1 = s.publish("det", _model(tmp_path, "a"), metrics={"f1": .9}, base_model="b", data={"tiles": 1})
    v2 = s.publish("det", _model(tmp_path, "b"), metrics={"f1": .95}, base_model="b", data={"tiles": 2})
    assert (v1, v2) == (1, 2) and s.current("det") == 2
    assert (s.current_path("det") / "model.safetensors").read_text() == "b"
    assert (tmp_path / "root/det/versions/v1/model.safetensors").read_text() == "a"  # v1 untouched
    assert (tmp_path / "backup/det/versions/v2/manifest.json").is_file()
    assert s.verify("det", 1) == [] and s.verify("det", 2, backup=True) == []


def test_corruption_is_detected_and_restored_from_backup(tmp_path):
    s = _store(tmp_path)
    s.publish("det", _model(tmp_path), metrics={}, base_model="b", data={})
    (s.current_path("det") / "model.safetensors").write_text("garbage")
    assert s.verify("det", 1) == ["model.safetensors: hash changed"]
    s.restore_from_backup("det", 1)
    assert s.verify("det", 1) == []
    assert any(p.name.startswith("v1.damaged-") for p in (tmp_path / "root/det/versions").iterdir())  # kept, not deleted


def test_cannot_switch_to_a_damaged_version_and_rollback_works(tmp_path):
    s = _store(tmp_path)
    s.publish("det", _model(tmp_path, "a"), metrics={}, base_model="b", data={})
    s.publish("det", _model(tmp_path, "b"), metrics={}, base_model="b", data={})
    s.set_current("det", 1)
    assert s.current("det") == 1
    (s.root / "det/versions/v2/config.json").write_text("{x}")
    with pytest.raises(ValueError, match="failed verification"):
        s.set_current("det", 2)
    assert s.current("det") == 1


def test_empty_publish_is_refused(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="nothing to publish"):
        _store(tmp_path).publish("det", tmp_path / "empty", metrics={}, base_model="b", data={})


def test_mirror_tree_copies_only_new_or_changed_and_never_deletes(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "a").mkdir(parents=True)
    (src / "a/x.txt").write_text("1")
    assert mirror_tree(src, dst) == 1 and mirror_tree(src, dst) == 0
    (src / "a/x.txt").unlink()
    assert mirror_tree(src, dst) == 0 and (dst / "a/x.txt").read_text() == "1"
