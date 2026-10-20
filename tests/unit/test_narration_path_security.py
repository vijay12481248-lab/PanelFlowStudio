from pathlib import Path

import pytest

from engine.security.paths import resolve_contained_path
from engine.story.narration import resolve_contained_panel_file


def test_sequence_panel_symlink_outside_workspace_is_rejected(tmp_path: Path):
    panels = tmp_path / "panels"
    panels.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_panel = outside / "panel_0001.png"
    outside_panel.write_bytes(b"not a real image")
    link = panels / "panel_0001.png"
    try:
        link.symlink_to(outside_panel)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    assert resolve_contained_panel_file(link, panels.resolve()) is None


def test_contained_panel_file_is_resolved(tmp_path: Path):
    panels = tmp_path / "panels"
    panels.mkdir()
    panel = panels / "panel_0001.png"
    panel.write_bytes(b"not a real image")

    assert resolve_contained_panel_file(panel, panels.resolve()) == panel.resolve()

def test_workspace_path_traversal_is_rejected(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError):
        resolve_contained_path(workspace, "../secret.txt", must_be_file=True)


def test_workspace_symlink_and_internal_symlink_are_rejected(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")

    internal_link = workspace / "linked.txt"
    try:
        internal_link.symlink_to(outside_file)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(ValueError):
        resolve_contained_path(workspace, "linked.txt", must_be_file=True)

    workspace_link = tmp_path / "workspace-link"
    try:
        workspace_link.symlink_to(workspace, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink creation unavailable: {exc}")

    with pytest.raises(ValueError):
        resolve_contained_path(workspace_link, "linked.txt")
