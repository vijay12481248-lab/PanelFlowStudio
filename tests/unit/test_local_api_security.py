import pytest
from fastapi.testclient import TestClient

from engine.api.app import create_app
from engine.api.routers import jobs as jobs_router
from engine.api.routers import projects as projects_router
from engine.llm.registry import llm_registry
from engine.system.resources import resource_manager


TOKEN = "t" * 64
APPROVED_ORIGIN = "http://tauri.localhost"
PROJECT_PAYLOAD = {
    "title": "Protected project",
    "source_type": "LOCAL_FOLDER",
    "rights_status": "USER_OWNED",
}
OLLAMA_PAYLOAD = {
    "endpoint_url": "http://127.0.0.1:11434",
    "is_remote": False,
    "vision_model": "test-vision",
    "reasoning_model": "test-reasoning",
    "narration_model": "test-narration",
    "num_ctx": 4096,
    "concurrency_mode": "MANUAL",
    "max_gpu_concurrency": 1,
}


def protected_client() -> TestClient:
    app = create_app(
        engine_token=TOKEN,
        allowed_origins={APPROVED_ORIGIN},
        allow_insecure=False,
    )
    return TestClient(app, base_url="http://127.0.0.1:8765")


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/jobs/job-1/cancel", None),
        ("/api/jobs/job-1/retry", None),
        ("/api/projects", PROJECT_PAYLOAD),
        ("/api/system/ollama/config", OLLAMA_PAYLOAD),
    ],
)
@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        ({"Origin": APPROVED_ORIGIN}, 401),
        ({"Origin": APPROVED_ORIGIN, "X-PanelFlow-Token": "wrong"}, 401),
        ({"Host": "evil.example", "Origin": APPROVED_ORIGIN, "X-PanelFlow-Token": TOKEN}, 400),
        ({"Origin": "https://evil.example", "X-PanelFlow-Token": TOKEN}, 403),
    ],
)
def test_protected_mutations_fail_closed_before_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: dict | None,
    headers: dict[str, str],
    expected_status: int,
):
    calls: list[str] = []
    monkeypatch.setattr(jobs_router.job_manager, "cancel_job", lambda *_: calls.append("cancel") or True)
    monkeypatch.setattr(jobs_router.job_manager, "retry_job", lambda *_: calls.append("retry") or True)

    response = protected_client().post(path, json=payload, headers=headers)

    assert response.status_code == expected_status
    assert calls == []


def test_health_remains_usable_without_token():
    response = protected_client().get("/api/system/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_approved_desktop_requests_can_cancel_and_retry(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    monkeypatch.setattr(jobs_router.job_manager, "cancel_job", lambda job_id: calls.append(f"cancel:{job_id}") or True)
    monkeypatch.setattr(jobs_router.job_manager, "retry_job", lambda job_id: calls.append(f"retry:{job_id}") or True)
    headers = {"Origin": APPROVED_ORIGIN, "X-PanelFlow-Token": TOKEN}
    client = protected_client()

    assert client.post("/api/jobs/job-1/cancel", headers=headers).status_code == 200
    assert client.post("/api/jobs/job-1/retry", headers=headers).status_code == 200
    assert calls == ["cancel:job-1", "retry:job-1"]


def test_approved_desktop_request_can_create_project(monkeypatch: pytest.MonkeyPatch):
    created: list[str] = []
    monkeypatch.setattr(
        projects_router.project_service,
        "create_project",
        lambda **kwargs: created.append(kwargs["title"]) or object(),
    )
    monkeypatch.setattr(
        projects_router,
        "format_project_response",
        lambda _project, _db: {
            **PROJECT_PAYLOAD,
            "id": "project-1",
            "source_url": None,
            "source_metadata": {},
            "license_info": "User owned",
            "workspace_path": "C:/workspace/project-1",
            "current_stage": "CREATED",
            "settings": {},
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        },
    )

    response = protected_client().post(
        "/api/projects",
        json=PROJECT_PAYLOAD,
        headers={"Origin": APPROVED_ORIGIN, "X-PanelFlow-Token": TOKEN},
    )

    assert response.status_code == 201
    assert response.json()["id"] == "project-1"
    assert created == ["Protected project"]


def test_approved_desktop_request_can_configure_provider(monkeypatch: pytest.MonkeyPatch):
    from engine.llm.providers import ollama as ollama_module

    provider = llm_registry.get_ollama_provider()
    calls: list[str] = []
    monkeypatch.setattr(llm_registry, "get_ollama_provider", lambda: provider)
    monkeypatch.setattr(llm_registry, "configure_ollama", lambda **_kwargs: calls.append("configured") or provider)
    monkeypatch.setattr(resource_manager, "set_concurrency", lambda *_args: calls.append("concurrency"))
    monkeypatch.setattr(ollama_module, "persist_ollama_endpoint_authorization", lambda *_args: None)

    response = protected_client().post(
        "/api/system/ollama/config",
        json=OLLAMA_PAYLOAD,
        headers={"Origin": APPROVED_ORIGIN, "X-PanelFlow-Token": TOKEN},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SAVED"
    assert calls == ["configured", "concurrency"]


def test_approved_cors_preflight_allows_token_header():
    response = protected_client().options(
        "/api/projects",
        headers={
            "Origin": APPROVED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-panelflow-token",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == APPROVED_ORIGIN


def test_resource_url_token_is_accepted_only_on_safe_resource_gets():
    app = create_app(
        engine_token=TOKEN,
        allowed_origins={APPROVED_ORIGIN},
        allow_insecure=False,
    )

    @app.get("/api/test/file")
    def resource_probe():
        return {"ok": True}

    client = TestClient(app, base_url="http://127.0.0.1:8765")
    response = client.get(f"/api/test/file;pf-token={TOKEN}", headers={"Origin": APPROVED_ORIGIN})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["referrer-policy"] == "no-referrer"

    assert client.post(f"/api/test/file;pf-token={TOKEN}", headers={"Origin": APPROVED_ORIGIN}).status_code == 401
