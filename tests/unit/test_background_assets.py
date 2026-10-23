from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient


def png():
    data = BytesIO()
    Image.new("RGBA", (30, 60), (200, 40, 80, 128)).save(data, "PNG")
    return data.getvalue()


def test_custom_background_upload_roundtrip_and_project_scope(tmp_path):
    from engine.api.routers.backgrounds import router
    from engine.database.session import get_db
    project = SimpleNamespace(workspace_path=str(tmp_path))
    query = SimpleNamespace(first=lambda: project)
    query.filter = lambda *_: query
    db = SimpleNamespace(query=lambda *_: query)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        uploaded = client.post("/api/projects/fixture/backgrounds", content=png(), headers={"Content-Type": "image/png"})
        assert uploaded.status_code == 200
        result = uploaded.json()
        assert result["width"] == 30 and result["height"] == 60
        response = client.get(result["image_url"])
        assert response.status_code == 200
        assert Image.open(BytesIO(response.content)).getpixel((0, 0)) == (200, 40, 80, 128)
        assert client.post("/api/projects/fixture/backgrounds", content=b"not an image").status_code == 422
        assert client.get("/api/projects/fixture/backgrounds/not-a-file.png/file").status_code == 404
        project = None
        assert client.post("/api/projects/missing/backgrounds", content=png()).status_code == 404


def test_background_store_rejects_escaping_directory_and_normalizes_orientation(tmp_path):
    from engine.api.routers.backgrounds import store_background_image
    data = BytesIO()
    image = Image.new("RGB", (20, 40), "red")
    exif = Image.Exif(); exif[274] = 6
    image.save(data, "JPEG", exif=exif)
    saved = store_background_image(tmp_path, data.getvalue())
    assert saved[1:] == (40, 20)
    assert Image.open(saved[0]).size == (40, 20)
    with pytest.raises(ValueError):
        store_background_image(tmp_path, b"garbage")
