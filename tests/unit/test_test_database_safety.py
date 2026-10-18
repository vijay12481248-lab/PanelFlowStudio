from pathlib import Path
import tempfile

from engine.config.settings import settings


def test_pytest_uses_isolated_database_and_workspace():
    root = Path(settings.app_data_dir).resolve()
    assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
    assert root.name.startswith("panelflow-tests-")
    assert settings.workspace_root.resolve().is_relative_to(root)
    assert settings.get_database_url() == f"sqlite:///{(root / 'test.db').as_posix()}"
