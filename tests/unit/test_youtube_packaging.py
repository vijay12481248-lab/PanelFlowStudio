import json
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.database.models import CharacterRecord, ProjectRecord, SceneRecord
from engine.database.session import SessionLocal, init_db
from engine.story.packaging import generate_heuristic_packaging


@pytest.fixture
def test_project(tmp_path):
    init_db()
    project_id = str(uuid.uuid4())
    workspace = tmp_path / project_id
    workspace.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        project = ProjectRecord(
            id=project_id,
            title="The Jade Lantern Oath",
            source_type="local",
            workspace_path=str(workspace),
            source_metadata={"synopsis": "A rogue swordswoman uncovers an ancient jade lantern with celestial power."},
            settings={},
        )
        db.add(project)

        char = CharacterRecord(
            id=str(uuid.uuid4()),
            project_id=project_id,
            display_name="Lin Xia",
            canonical_name="Lin Xia",
            role="PROTAGONIST",
            description="teal-haired warrior in crimson robes carrying a glowing jade blade",
            visual_traits=["teal hair", "crimson robes", "jade sword"],
        )
        db.add(char)

        scene1 = SceneRecord(
            id=str(uuid.uuid4()),
            project_id=project_id,
            sequence=1,
            title="Mountain Bridge Confrontation",
            panel_start="p1",
            panel_end="p3",
            summary="The wind howled across the cliff as the shadows gathered.",
        )
        scene2 = SceneRecord(
            id=str(uuid.uuid4()),
            project_id=project_id,
            sequence=2,
            title="Awakening of the Jade Blade",
            panel_start="p4",
            panel_end="p6",
            summary="A burst of emerald light shattered the ancient stone.",
        )
        db.add_all([scene1, scene2])
        db.commit()

    yield project_id

    # Cleanup
    with SessionLocal() as db:
        p = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if p:
            db.delete(p)
            db.commit()


def test_heuristic_packaging_landscape(test_project):
    with SessionLocal() as db:
        project = db.query(ProjectRecord).filter(ProjectRecord.id == test_project).first()
        packaging = generate_heuristic_packaging(
            project,
            profile_name="standard_1080p",
            focus_character="Lin Xia",
        )

        assert packaging.thumbnail.aspect_ratio == "16:9"
        assert packaging.thumbnail.recommended_width == 1280
        assert packaging.thumbnail.recommended_height == 720
        assert packaging.thumbnail.recommended_width % 8 == 0
        assert packaging.thumbnail.recommended_height % 8 == 0
        assert "Lin Xia" in packaging.thumbnail.prompt
        assert "teal-haired warrior" in packaging.thumbnail.prompt
        assert "8k resolution" in packaging.thumbnail.prompt
        assert "text" in packaging.thumbnail.negative_prompt
        assert len(packaging.titles) >= 3
        assert any("The Jade Lantern Oath" in t or "Lin Xia" in t for t in packaging.titles)
        assert len(packaging.chapters) == 2
        assert packaging.chapters[0].timestamp == "00:00"
        assert packaging.chapters[1].timestamp == "00:04"
        assert "lin xia" in packaging.tags
        assert "motion comic" in packaging.tags
        assert "#MotionComic" in packaging.hashtags


def test_heuristic_packaging_vertical_shorts(test_project):
    with SessionLocal() as db:
        project = db.query(ProjectRecord).filter(ProjectRecord.id == test_project).first()
        packaging = generate_heuristic_packaging(
            project,
            profile_name="vertical_shorts",
            custom_hook="WAIT FOR IT",
        )

        assert packaging.thumbnail.aspect_ratio == "9:16"
        assert packaging.thumbnail.recommended_width == 720
        assert packaging.thumbnail.recommended_height == 1280
        assert packaging.thumbnail.recommended_width % 8 == 0
        assert packaging.thumbnail.recommended_height % 8 == 0
        assert "#Shorts" in packaging.titles[0]
        assert "[WAIT FOR IT]" in packaging.titles[0]
        assert "shorts" in packaging.tags


def test_youtube_packaging_api_flow(test_project):
    client = TestClient(app)

    # 1. GET packaging (generates and caches)
    res = client.get(f"/api/projects/{test_project}/youtube/packaging")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == test_project
    assert len(data["titles"]) >= 3
    assert "description" in data
    assert len(data["tags"]) > 5
    assert data["thumbnail"]["aspect_ratio"] == "16:9"

    # 2. Check cached file in workspace
    with SessionLocal() as db:
        project = db.query(ProjectRecord).filter(ProjectRecord.id == test_project).first()
        workspace = Path(str(project.workspace_path))
        cached = workspace / "generated" / "youtube_packaging.json"
        assert cached.is_file()
        cached_content = json.loads(cached.read_text(encoding="utf-8"))
        assert cached_content["project_id"] == test_project

    # 3. POST regenerate with custom hook & vertical shorts
    res_post = client.post(
        f"/api/projects/{test_project}/youtube/packaging/generate",
        json={
            "profile_name": "vertical_shorts",
            "focus_character": "Lin Xia",
            "style_tone": "action",
            "custom_hook": "SHOCKING",
        },
    )
    assert res_post.status_code == 200
    post_data = res_post.json()
    assert post_data["thumbnail"]["aspect_ratio"] == "9:16"
    assert "[SHOCKING]" in post_data["titles"][0]
    assert post_data["thumbnail"]["recommended_width"] == 720
    assert post_data["thumbnail"]["recommended_height"] == 1280
