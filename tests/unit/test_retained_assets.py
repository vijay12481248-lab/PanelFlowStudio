from pathlib import Path

import pytest


def test_retained_asset_store_restores_before_and_after_including_deleted_files(tmp_path: Path):
    from engine.history.assets import RetainedAssetStore

    workspace = tmp_path / "project"
    (workspace / "panels").mkdir(parents=True)
    target = workspace / "panels" / "panel.jpg"
    target.write_bytes(b"before")
    store = RetainedAssetStore(workspace)

    store.capture_before("op-1", ["panels/panel.jpg", "panels/new.jpg"])
    target.write_bytes(b"after")
    (workspace / "panels" / "new.jpg").write_bytes(b"created")
    store.capture_after("op-1")

    target.write_bytes(b"broken")
    (workspace / "panels" / "new.jpg").unlink()
    store.restore("op-1", "before")
    assert target.read_bytes() == b"before"
    assert not (workspace / "panels" / "new.jpg").exists()

    store.restore("op-1", "after")
    assert target.read_bytes() == b"after"
    assert (workspace / "panels" / "new.jpg").read_bytes() == b"created"


def test_retained_asset_store_recovers_interrupted_prepared_operation(tmp_path: Path):
    from engine.history.assets import RetainedAssetStore, recover_workspaces

    workspace = tmp_path / "project"
    (workspace / "panels").mkdir(parents=True)
    target = workspace / "panels" / "panel.jpg"
    target.write_bytes(b"original")
    store = RetainedAssetStore(workspace)
    store.capture_before("op-2", ["panels/panel.jpg"])
    target.write_bytes(b"partial")

    assert recover_workspaces([workspace]) == {str(workspace.resolve()): ["op-2"]}
    assert target.read_bytes() == b"original"


@pytest.mark.parametrize("path", ["../outside.txt", "/absolute.txt", "panels/../../outside.txt"])
def test_retained_asset_store_rejects_paths_outside_project(tmp_path: Path, path: str):
    from engine.history.assets import RetainedAssetStore

    workspace = tmp_path / "project"
    workspace.mkdir()
    store = RetainedAssetStore(workspace)
    with pytest.raises(ValueError, match="contained"):
        store.capture_before("op-3", [path])
