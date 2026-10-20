"""Exercise restart request boundaries without stopping any real engine."""
from unittest.mock import Mock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from engine.api.routers.system import router, engine_instance_id
from engine.database.models import JobRecord, RenderJobRecord
from engine.database.session import get_db


@pytest.fixture
def restart_app():
    app = FastAPI()
    app.include_router(router)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: db
    app.state.request_restart = Mock()
    return app, db


async def post_restart(app, host="127.0.0.1", headers=None):
    transport = httpx.ASGITransport(app=app, client=(host, 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        return await client.post("/api/system/restart", headers=headers if headers is not None else {"X-PanelFlow-Control": "restart"})


@pytest.mark.asyncio
async def test_restart_accepted_once_after_response(restart_app):
    app, _ = restart_app
    response = await post_restart(app)
    assert response.status_code == 202
    assert response.json() == {"status": "restarting", "instance_id": engine_instance_id}
    app.state.request_restart.assert_called_once_with()
    assert (await post_restart(app)).status_code == 409
    app.state.request_restart.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("host,headers", [("192.168.1.5", None), ("127.0.0.1", {})])
async def test_restart_requires_local_control_request(restart_app, host, headers):
    app, _ = restart_app
    assert (await post_restart(app, host, headers)).status_code == 403
    app.state.request_restart.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("busy_model", [JobRecord, RenderJobRecord])
async def test_restart_rejects_active_work(restart_app, busy_model):
    app, db = restart_app
    def query(model):
        result = MagicMock()
        result.filter.return_value.first.return_value = object() if model is busy_model else None
        return result
    db.query.side_effect = query
    assert (await post_restart(app)).status_code == 409
    app.state.request_restart.assert_not_called()


@pytest.mark.asyncio
async def test_restart_requires_managed_entrypoint(restart_app):
    app, _ = restart_app
    del app.state.request_restart
    assert (await post_restart(app)).status_code == 409


@pytest.mark.parametrize("restart", [True, False])
def test_entrypoint_reexecutes_only_after_server_returns(monkeypatch, restart):
    import os
    import runpy
    import sys
    from pathlib import Path
    import uvicorn
    from engine.api.app import app

    server = Mock()
    events = []
    def serve():
        if restart:
            app.state.request_restart()
            assert server.should_exit is True
        events.append("shutdown_complete")
    server.run.side_effect = serve
    monkeypatch.setattr(uvicorn, "Server", Mock(return_value=server))
    monkeypatch.setattr(uvicorn, "Config", Mock())
    monkeypatch.setattr(os, "execv", lambda executable, args: events.append((executable, args)))
    entrypoint = Path(__file__).resolve().parents[2] / "run_engine.py"
    try:
        runpy.run_path(str(entrypoint), run_name="__main__")
        assert events[0] == "shutdown_complete"
        if restart:
            assert events[1] == (sys.executable, [sys.executable, str(entrypoint)])
        else:
            assert len(events) == 1
    finally:
        del app.state.request_restart
