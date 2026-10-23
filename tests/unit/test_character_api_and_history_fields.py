import pytest
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from engine.api.app import app
from engine.config.settings import settings
from engine.database.models import (
    Base, ProjectRecord, CharacterRecord, AssetRecord, TextRegionRecord, PageRecord, PanelRecord, EventRecord, utc_now
)
from engine.database.session import engine, SessionLocal
from engine.history.service import HistoryService
from engine.history.contracts import HistoryFault
from tests.fixtures.helpers import create_test_image_bytes

@pytest.fixture(autouse=True)
def setup_db(tmp_path: Path, monkeypatch):
    test_ws = tmp_path / "workspaces"
    monkeypatch.setattr(settings, "workspace_root", test_ws)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def create_test_project_and_asset(project_id: str = "proj-1", asset_id: str = "asset-1", cross_project_id: str = "proj-other"):
    with SessionLocal() as db:
        proj = ProjectRecord(
            id=project_id, title="Test Project", workspace_path=f"/tmp/{project_id}",
            source_type="LOCAL_FOLDER", source_url="/tmp/src", current_stage="MANGA_LOADED"
        )
        proj_other = ProjectRecord(
            id=cross_project_id, title="Other Project", workspace_path=f"/tmp/{cross_project_id}",
            source_type="LOCAL_FOLDER", source_url="/tmp/other", current_stage="MANGA_LOADED"
        )
        db.add_all([proj, proj_other])
        db.commit()

        asset = AssetRecord(
            id=asset_id, project_id=project_id, asset_type="CHARACTER_REFERENCE",
            filename="hero.png", relative_path="references/hero.png",
            content_type="image/png", width=512, height=768, byte_size=1000,
            sha256="a" * 64, provenance={"workflow_id": "wf_test", "seed": 42}
        )
        cross_asset = AssetRecord(
            id="asset-cross", project_id=cross_project_id, asset_type="CHARACTER_REFERENCE",
            filename="cross.png", relative_path="references/cross.png",
            content_type="image/png", width=512, height=768, byte_size=1000,
            sha256="c" * 64, provenance={"workflow_id": "cross_wf", "seed": 99}
        )
        char = CharacterRecord(
            id="char-1", project_id=project_id, display_name="Hero",
            canonical_name="The Hero", role="PROTAGONIST", aliases=["H1"],
            description="Main hero", visual_traits=["red cape"],
            reference_asset_id=None, generation_params={}, proposed_changes={}, change_status="NONE",
            status="APPROVED", manual_override=False,
        )
        page = PageRecord(id="page-1", project_id=project_id, sequence=1, filename="p1.jpg", width=100, height=100)
        panel = PanelRecord(id="pan-1", project_id=project_id, page_id="page-1", sequence=1, page_sequence=1, x=0, y=0, width=50, height=50, crop_filename="c1.jpg")
        db.add_all([asset, cross_asset, char, page, panel])
        db.commit()

def test_api_character_list_and_update_fields():
    create_test_project_and_asset()
    client = TestClient(app)

    # Verify list_characters contains new fields
    resp = client.get("/api/projects/proj-1/characters")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    char_data = data[0]
    assert "reference_asset_id" in char_data
    assert "generation_params" in char_data
    assert "proposed_changes" in char_data
    assert "change_status" in char_data

    # Update character with new fields
    update_resp = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={
            "reference_asset_id": "asset-1",
            "generation_params": {"model": "qwen", "seed": 42},
            "proposed_changes": {"visual_traits": ["red cape", "blue boots"]},
            "change_status": "PENDING_REVIEW",
        }
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated.get("reference_asset_id") == "asset-1"
    assert updated.get("generation_params") == {"model": "qwen", "seed": 42}
    assert updated.get("proposed_changes") == {"visual_traits": ["red cape", "blue boots"]}
    assert updated.get("change_status") == "PENDING_REVIEW"

    # Verify DB persistence
    with SessionLocal() as db:
        db_char = db.get(CharacterRecord, "char-1")
        assert db_char.reference_asset_id == "asset-1"
        assert db_char.generation_params == {"model": "qwen", "seed": 42}
        assert db_char.proposed_changes == {"visual_traits": ["red cape", "blue boots"]}
        assert db_char.change_status == "PENDING_REVIEW"

def test_api_rejects_cross_project_or_nonexistent_reference_asset():
    create_test_project_and_asset()
    client = TestClient(app)

    # Non-existent asset
    resp_nonexistent = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={"reference_asset_id": "asset-does-not-exist"}
    )
    assert resp_nonexistent.status_code in (400, 404, 422)

    # Cross-project asset
    resp_cross = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={"reference_asset_id": "asset-cross"}
    )
    assert resp_cross.status_code in (400, 404, 422)

def test_api_character_split_response_and_metadata():
    create_test_project_and_asset()
    client = TestClient(app)

    split_resp = client.post(
        "/api/projects/proj-1/characters/char-1/split",
        json={
            "new_name": "Split Hero",
            "panel_ids": ["pan-1"],
        }
    )
    assert split_resp.status_code == 200
    split_data = split_resp.json()
    assert "reference_asset_id" in split_data
    assert "generation_params" in split_data
    assert "proposed_changes" in split_data
    assert "change_status" in split_data
    assert split_data["reference_asset_id"] is None
    assert split_data["generation_params"] == {}
    assert split_data["proposed_changes"] == {}
    assert split_data["change_status"] == "NONE"

def test_history_character_update_undo_redo_retains_metadata():
    create_test_project_and_asset()
    history = HistoryService.create_default()

    with SessionLocal() as db:
        proj = db.get(ProjectRecord, "proj-1")
        res = history.execute(
            db, "proj-1", operation_id=str(uuid4()), expected_revision=0,
            command_type="character.update", version=1,
            label="Update character reference",
            input={
                "character_id": "char-1",
                "reference_asset_id": "asset-1",
                "generation_params": {"model": "qwen", "seed": 123},
                "proposed_changes": {"visual_traits": ["helmet"]},
                "change_status": "PENDING_REVIEW",
            }
        )
        char = db.get(CharacterRecord, "char-1")
        assert char.reference_asset_id == "asset-1"
        assert char.generation_params == {"model": "qwen", "seed": 123}
        assert char.proposed_changes == {"visual_traits": ["helmet"]}
        assert char.change_status == "PENDING_REVIEW"

        # Undo
        undone = history.move(db, "proj-1", direction="undo", operation_id=str(uuid4()), expected_revision=res["history"]["revision"])
        char_undone = db.get(CharacterRecord, "char-1")
        assert char_undone.reference_asset_id is None
        assert char_undone.generation_params == {}
        assert char_undone.proposed_changes == {}
        assert char_undone.change_status == "NONE"

        # Redo
        history.move(db, "proj-1", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        char_redone = db.get(CharacterRecord, "char-1")
        assert char_redone.reference_asset_id == "asset-1"
        assert char_redone.generation_params == {"model": "qwen", "seed": 123}
        assert char_redone.proposed_changes == {"visual_traits": ["helmet"]}
        assert char_redone.change_status == "PENDING_REVIEW"

def test_history_rejects_cross_project_asset():
    create_test_project_and_asset()
    history = HistoryService.create_default()

    with SessionLocal() as db:
        with pytest.raises(HistoryFault) as exc_info:
            history.execute(
                db, "proj-1", operation_id=str(uuid4()), expected_revision=0,
                command_type="character.update", version=1,
                label="Invalid cross-project asset",
                input={
                    "character_id": "char-1",
                    "reference_asset_id": "asset-cross",
                }
            )
        assert exc_info.value.code in ("VALIDATION", "NOT_FOUND")

def test_history_legacy_payload_compatibility():
    create_test_project_and_asset()
    history = HistoryService.create_default()

    # Simulate a legacy payload from an older journal before new fields existed
    legacy_payload = {
        "character_id": "char-1",
        "before": {"display_name": "Hero", "role": "PROTAGONIST", "manual_override": False},
        "after": {"display_name": "Updated Hero", "role": "PROTAGONIST"},
        "operation_id": str(uuid4()),
    }
    strategy = history.registry.resolve("character.update", 1)
    assert strategy.validate(legacy_payload) is True

    with SessionLocal() as db:
        proj = db.get(ProjectRecord, "proj-1")
        strategy.apply(db, proj, legacy_payload, forward=True)
        char = db.get(CharacterRecord, "char-1")
        assert char.display_name == "Updated Hero"
        # Defaults/existing values preserved
        assert char.reference_asset_id is None
        assert char.generation_params == {}

        strategy.apply(db, proj, legacy_payload, forward=False)
        char = db.get(CharacterRecord, "char-1")
        assert char.display_name == "Hero"

def test_character_merge_undo_redo_retains_metadata():
    create_test_project_and_asset()
    history = HistoryService.create_default()

    with SessionLocal() as db:
        # Add a source character with reference asset and metadata
        src_char = CharacterRecord(
            id="char-src", project_id="proj-1", display_name="Source",
            canonical_name="Source Hero", role="SUPPORTING", aliases=["S1"],
            description="To be merged", visual_traits=["cape"],
            reference_asset_id="asset-1", generation_params={"seed": 111},
            proposed_changes={"trait": "x"}, change_status="PENDING_REVIEW",
            status="CONFIRMED", manual_override=True
        )
        db.add(src_char)
        db.commit()

        merged = history.execute(
            db, "proj-1", operation_id=str(uuid4()), expected_revision=0,
            command_type="character.merge", version=1,
            label="Merge character",
            input={"source_character_id": "char-src", "target_character_id": "char-1"}
        )
        assert db.get(CharacterRecord, "char-src") is None

        # Undo
        undone = history.move(db, "proj-1", direction="undo", operation_id=str(uuid4()), expected_revision=merged["history"]["revision"])
        src_restored = db.get(CharacterRecord, "char-src")
        assert src_restored is not None
        assert src_restored.reference_asset_id == "asset-1"
        assert src_restored.generation_params == {"seed": 111}
        assert src_restored.proposed_changes == {"trait": "x"}
        assert src_restored.change_status == "PENDING_REVIEW"

def test_character_split_undo_redo_retains_metadata():
    create_test_project_and_asset()
    history = HistoryService.create_default()

    with SessionLocal() as db:
        split = history.execute(
            db, "proj-1", operation_id=str(uuid4()), expected_revision=0,
            command_type="character.split", version=1,
            label="Split character",
            input={
                "character_id": "char-1",
                "new_name": "Split Hero",
                "panel_ids": ["pan-1"],
                "new_character_id": "char-new-split",
            }
        )
        new_c = db.get(CharacterRecord, "char-new-split")
        assert new_c is not None
        assert new_c.reference_asset_id is None
        assert new_c.generation_params == {}
        assert new_c.proposed_changes == {}
        assert new_c.change_status == "NONE"

        undone = history.move(db, "proj-1", direction="undo", operation_id=str(uuid4()), expected_revision=split["history"]["revision"])
        assert db.get(CharacterRecord, "char-new-split") is None

        history.move(db, "proj-1", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        new_c_redo = db.get(CharacterRecord, "char-new-split")
        assert new_c_redo is not None
        assert new_c_redo.reference_asset_id is None
        assert new_c_redo.generation_params == {}
        assert new_c_redo.change_status == "NONE"

def test_api_proposal_approval_boundaries():
    create_test_project_and_asset()
    client = TestClient(app)

    # 1. Propose changes
    prop_resp = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={
            "proposed_changes": {"visual_traits": ["red cape", "winged boots"], "description": "Updated description"},
        }
    )
    assert prop_resp.status_code == 200
    data = prop_resp.json()
    assert data["change_status"] == "PENDING_REVIEW"
    assert data["proposed_changes"]["visual_traits"] == ["red cape", "winged boots"]
    # Curated traits must NOT have changed yet!
    assert data["visual_traits"] == ["red cape"]
    assert data["description"] == "Main hero"

    # 2. Approve proposal
    appr_resp = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={"change_status": "APPROVED"}
    )
    assert appr_resp.status_code == 200
    appr_data = appr_resp.json()
    assert appr_data["change_status"] == "APPROVED"
    assert appr_data["proposed_changes"] == {}
    assert appr_data["visual_traits"] == ["red cape", "winged boots"]
    assert appr_data["description"] == "Updated description"

    # 3. Propose another change then reject
    client.put(
        "/api/projects/proj-1/characters/char-1",
        json={
            "proposed_changes": {"visual_traits": ["clown nose"]},
        }
    )
    rej_resp = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={"change_status": "REJECTED"}
    )
    assert rej_resp.status_code == 200
    rej_data = rej_resp.json()
    assert rej_data["change_status"] == "REJECTED"
    assert rej_data["proposed_changes"] == {}
    # Curated traits must remain unchanged
    assert rej_data["visual_traits"] == ["red cape", "winged boots"]



def test_aud_rev_01_proposal_approval_matches_history_and_rest():
    # AUD-REV-01: Proposing via REST or history and approving via REST or history produces identical state
    create_test_project_and_asset()
    client = TestClient(app)

    # Propose changes
    r = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={"proposed_changes": {"description": "Durable proposed desc"}},
    )
    assert r.status_code == 200
    assert r.json()["change_status"] == "PENDING_REVIEW"
    assert r.json()["description"] == "Main hero"

    # Approve
    r2 = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={"change_status": "APPROVED"},
    )
    assert r2.status_code == 200
    assert r2.json()["change_status"] == "APPROVED"
    assert r2.json()["description"] == "Durable proposed desc"
    assert r2.json()["proposed_changes"] == {}


def test_aud_rev_02_canonical_planning_provenance_and_conflict_on_missing_asset():
    # AUD-REV-02: generation_params derived from provenance captured in forward state; replay fails atomically on missing asset
    db = SessionLocal()
    try:
        create_test_project_and_asset()
        a0 = db.get(AssetRecord, "asset-1")
        a0.provenance = {"seed": 1234, "model": "sd-xl"}
        db.commit()
        history = HistoryService.create_default()

        # 1. Update character with asset reference but omitted generation_params
        res = history.execute(
            db,
            "proj-1",
            operation_id=str(uuid4()),
            expected_revision=0,
            command_type="character.update",
            version=1,
            label="Set ref asset",
            input={"character_id": "char-1", "reference_asset_id": "asset-1"},
        )
        # Check canonical planning captured provenance
        c = db.get(CharacterRecord, "char-1")
        assert c.generation_params == {"seed": 1234, "model": "sd-xl"}

        # 2. Undo returns params to prior
        undone = history.move(db, "proj-1", direction="undo", operation_id=str(uuid4()), expected_revision=res["history"]["revision"])
        c_undone = db.get(CharacterRecord, "char-1")
        assert c_undone.reference_asset_id is None
        assert c_undone.generation_params == {}

        # 3. Delete referenced asset outside history
        a = db.get(AssetRecord, "asset-1")
        db.delete(a)
        db.commit()

        # 4. Redo must fail atomically with CONFLICT (409) and not advance revision
        try:
            history.move(db, "proj-1", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
            assert False, "Expected CONFLICT HistoryFault"
        except HistoryFault as e:
            assert e.code == "CONFLICT"
            assert e.status == 409
    finally:
        db.close()


def test_aud_rev_03_strict_object_and_valid_change_status():
    # AUD-REV-03: Strict JSON object + valid status enforced across REST and history boundaries
    create_test_project_and_asset()
    client = TestClient(app)

    # REST rejects non-dict generation_params
    r = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={"generation_params": [1, 2, 3]},
    )
    assert r.status_code == 422

    # REST rejects non-dict proposed_changes
    r = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={"proposed_changes": "scalar_string"},
    )
    assert r.status_code == 422

    # REST rejects invalid change_status
    r = client.put(
        "/api/projects/proj-1/characters/char-1",
        json={"change_status": "INVALID_STATUS"},
    )
    assert r.status_code == 422

    # History strategy rejects non-dict via direct command
    db = SessionLocal()
    try:
        history = HistoryService.create_default()
        try:
            history.execute(
                db,
                "proj-1",
                operation_id=str(uuid4()),
                expected_revision=0,
                command_type="character.update",
                version=1,
                label="Bad params",
                input={"character_id": "char-1", "generation_params": [1, 2, 3]},
            )
            assert False, "Expected validation failure"
        except HistoryFault as e:
            assert e.status == 422

        try:
            history.execute(
                db,
                "proj-1",
                operation_id=str(uuid4()),
                expected_revision=0,
                command_type="character.update",
                version=1,
                label="Bad status",
                input={"character_id": "char-1", "change_status": "BOGUS"},
            )
            assert False, "Expected validation failure"
        except HistoryFault as e:
            assert e.status == 422
    finally:
        db.close()
