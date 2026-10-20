"""Isolate test state before test modules import the engine's global session.

Integration fixtures recreate database tables. Never let them touch the desktop
database, even when the developer has configured an explicit DATABASE_URL.
"""
import os
from pathlib import Path
import tempfile


_test_root = Path(tempfile.mkdtemp(prefix="panelflow-tests-")).resolve()
os.environ["PANELFLOW_APP_DATA"] = str(_test_root)
os.environ["PANELFLOW_WORKSPACE_ROOT"] = str(_test_root / "projects")
os.environ["PANELFLOW_DATABASE_URL"] = f"sqlite:///{(_test_root / 'test.db').as_posix()}"
# Existing tests exercise domain/API behavior rather than the desktop launch
# handshake. Security tests instantiate a protected app explicitly.
os.environ["PANELFLOW_ALLOW_INSECURE_LOCAL_API"] = "1"
