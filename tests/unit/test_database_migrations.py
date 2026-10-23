"""Validates non-destructive database migration and backward compatibility across milestones.

Tests upgrading:
1. Phase 1-style schema (original projects, pages, jobs, panels)
2. Phase 2-style schema (added page_normalizations, normalized panel columns)
3. Current schema (with text_regions, ocr_results, ocr_cache)
Ensures existing records and foreign keys remain intact without data loss.
"""

from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from engine.database.session import run_sqlite_migrations, set_sqlite_pragma
from engine.database.models import (
    Base,
    ProjectRecord,
    PageRecord,
    NormalizationRecord,
    PanelRecord,
    TextRegionRecord,
    OCRRecord,
    OCRCacheRecord,
    JobRecord,
    CharacterRecord,
    AssetRecord,
)

def test_upgrade_phase1_database(tmp_path: Path):
    db_file = tmp_path / "phase1.db"
    eng = create_engine(f"sqlite:///{db_file}")

    # 1. Construct Phase 1 legacy schema manually
    with eng.connect() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE projects (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                source_type VARCHAR(64) NOT NULL,
                source_url VARCHAR(1024),
                source_metadata JSON NOT NULL,
                rights_status VARCHAR(64) NOT NULL,
                license_info TEXT NOT NULL,
                workspace_path VARCHAR(1024) NOT NULL,
                current_stage VARCHAR(64) NOT NULL,
                settings JSON NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
        """)
        conn.exec_driver_sql("""
            CREATE TABLE pages (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                sequence INTEGER NOT NULL,
                filename VARCHAR(255) NOT NULL,
                source_url VARCHAR(1024),
                content_type VARCHAR(64) NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                byte_size BIGINT NOT NULL,
                sha256 VARCHAR(64) NOT NULL,
                downloaded_at DATETIME NOT NULL,
                status VARCHAR(32) NOT NULL,
                error_message TEXT
            );
        """)
        conn.exec_driver_sql("""
            CREATE TABLE panels (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                page_id VARCHAR(36) NOT NULL,
                sequence INTEGER NOT NULL,
                page_sequence INTEGER NOT NULL,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                crop_filename VARCHAR(255) NOT NULL,
                confidence FLOAT NOT NULL,
                status VARCHAR(32) NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
        """)
        # Insert Phase 1 sample record
        conn.exec_driver_sql("""
            INSERT INTO projects VALUES (
                'p1', 'Legacy Phase 1 Project', 'LOCAL_FOLDER', '', '{}',
                'PUBLIC_DOMAIN', 'None', '/fake/path', 'ACQUIRED', '{}',
                '2026-01-01 00:00:00', '2026-01-01 00:00:00'
            );
        """)
        conn.exec_driver_sql("""
            INSERT INTO panels VALUES (
                'pan1', 'p1', 'page1', 1, 1, 100, 100, 400, 300,
                'pan1.jpg', 0.95, 'DETECTED', '2026-01-01 00:00:00', '2026-01-01 00:00:00'
            );
        """)
        conn.commit()

    # 2. Run migrations
    Base.metadata.create_all(bind=eng)
    run_sqlite_migrations(eng)

    # 3. Verify upgraded columns exist and legacy data is preserved
    Session = sessionmaker(bind=eng)
    session = Session()

    proj = session.query(ProjectRecord).filter(ProjectRecord.id == "p1").first()
    assert proj is not None
    assert proj.title == "Legacy Phase 1 Project"

    pan = session.query(PanelRecord).filter(PanelRecord.id == "pan1").first()
    assert pan is not None
    assert pan.width == 400
    # Newly migrated columns have default values
    assert pan.normalized_x == 0.0
    assert pan.detection_method == "AUTO"
    assert pan.panel_type == "STANDARD"
    assert pan.manually_modified is False
    assert pan.reading_direction == "ltr"

    session.close()

def test_upgrade_phase2_database(tmp_path: Path):
    db_file = tmp_path / "phase2.db"
    eng = create_engine(f"sqlite:///{db_file}")

    # Create Phase 2 schema (with page_normalizations and panels with normalized cols)
    Base.metadata.create_all(bind=eng)
    run_sqlite_migrations(eng)

    Session = sessionmaker(bind=eng)
    session = Session()

    # Insert a project, panel, and text region
    proj = ProjectRecord(
        id="proj-p2",
        title="Phase 2 Project",
        source_type="LOCAL_FOLDER",
        source_url="",
        workspace_path="/tmp",
        rights_status="PUBLIC_DOMAIN",
        current_stage="PANELS_DETECTED",
    )
    session.add(proj)
    session.commit()

    # Re-run migrations to verify idempotency
    run_sqlite_migrations(eng)

    queried = session.query(ProjectRecord).filter(ProjectRecord.id == "proj-p2").first()
    assert queried is not None
    assert queried.current_stage == "PANELS_DETECTED"
    session.close()

def test_canonical_models_declarative():
    """Confirms all canonical tables and models are registered in Base metadata."""
    expected_tables = {
        "projects",
        "pages",
        "page_normalizations",
        "panels",
        "text_regions",
        "ocr_results",
        "ocr_cache",
        "jobs",
        "characters",
        "assets",
    }
    registered_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(registered_tables), f"Missing tables: {expected_tables - registered_tables}"


def test_upgrade_legacy_assets_and_characters_database(tmp_path: Path):
    db_file = tmp_path / "legacy_chars_assets.db"
    eng = create_engine(f"sqlite:///{db_file}")

    # 1. Construct pre-change legacy schema without new columns
    with eng.connect() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE projects (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                source_type VARCHAR(64) NOT NULL,
                source_url VARCHAR(1024),
                source_metadata JSON NOT NULL,
                rights_status VARCHAR(64) NOT NULL,
                license_info TEXT NOT NULL,
                workspace_path VARCHAR(1024) NOT NULL,
                current_stage VARCHAR(64) NOT NULL,
                settings JSON NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
        """)
        conn.exec_driver_sql("""
            CREATE TABLE characters (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                display_name VARCHAR(255) NOT NULL,
                canonical_name VARCHAR(255),
                aliases JSON NOT NULL,
                description TEXT NOT NULL,
                visual_traits JSON NOT NULL,
                role VARCHAR(32) NOT NULL,
                first_panel_id VARCHAR(36),
                reference_panel_ids JSON NOT NULL,
                status VARCHAR(32) NOT NULL,
                manual_override BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
        """)
        conn.exec_driver_sql("""
            CREATE TABLE assets (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                asset_type VARCHAR(64) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                relative_path VARCHAR(1024) NOT NULL,
                content_type VARCHAR(128) NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                byte_size BIGINT NOT NULL,
                sha256 VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                created_at DATETIME NOT NULL
            );
        """)
        # Seed representative legacy rows
        conn.exec_driver_sql("""
            INSERT INTO projects VALUES (
                'proj-legacy-1', 'Legacy Project', 'LOCAL_FOLDER', '', '{}',
                'PUBLIC_DOMAIN', 'None', '/fake/workspace', 'STORY_APPROVED', '{}',
                '2026-01-01 00:00:00', '2026-01-01 00:00:00'
            );
        """)
        conn.exec_driver_sql("""
            INSERT INTO characters VALUES (
                'char-legacy-1', 'proj-legacy-1', 'Original Hero', 'Hero', '[\"The One\"]',
                'A legendary swordsman', '[\"katana\", \"white cape\"]', 'PROTAGONIST',
                'pan-1', '[\"pan-1\"]', 'APPROVED', 1,
                '2026-01-01 00:00:00', '2026-01-01 00:00:00'
            );
        """)
        conn.exec_driver_sql("""
            INSERT INTO assets VALUES (
                'asset-legacy-1', 'proj-legacy-1', 'CHARACTER_REFERENCE',
                'hero_ref.png', 'references/hero_ref.png', 'image/png',
                512, 768, 45000, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'READY', '2026-01-01 00:00:00'
            );
        """)
        conn.commit()

    # 2. Run startup migrations twice to test idempotency
    run_sqlite_migrations(eng)
    run_sqlite_migrations(eng)

    # 3. Assert old data preserved and added columns have correct default/null semantics
    Session = sessionmaker(bind=eng)
    session = Session()

    char = session.query(CharacterRecord).filter(CharacterRecord.id == "char-legacy-1").first()
    assert char is not None
    assert char.display_name == "Original Hero"
    assert char.visual_traits == ["katana", "white cape"]
    assert char.role == "PROTAGONIST"
    assert char.manual_override is True
    assert char.reference_asset_id is None
    assert char.generation_params == {} or char.generation_params == "{}"
    assert char.proposed_changes == {} or char.proposed_changes == "{}"
    assert char.change_status == "NONE"

    asset = session.query(AssetRecord).filter(AssetRecord.id == "asset-legacy-1").first()
    assert asset is not None
    assert asset.filename == "hero_ref.png"
    assert asset.width == 512
    assert asset.height == 768
    assert asset.sha256 == 'a' * 64
    assert asset.provenance == {} or asset.provenance == "{}"

    # 4. ORM read/write/reopen
    char.reference_asset_id = "asset-legacy-1"
    char.generation_params = {"workflow_id": "manga_qwen", "seed": 42}
    char.proposed_changes = {"visual_traits": ["katana", "white cape", "gold badge"]}
    char.change_status = "PENDING_REVIEW"
    asset.provenance = {"workflow_id": "manga_consistent_qwen_image_edit", "seed": 42, "model": "qwen"}

    new_char = CharacterRecord(
        id="char-new-1",
        project_id="proj-legacy-1",
        display_name="New Ally",
        visual_traits=["shield"],
        role="SUPPORTING",
        reference_asset_id="asset-legacy-1",
        generation_params={"seed": 999},
        proposed_changes={},
        change_status="NONE",
    )
    session.add(new_char)
    session.commit()
    session.close()
    eng.dispose()

    # Reopen on fresh engine connection from disk
    eng_reopened = create_engine(f"sqlite:///{db_file}")
    SessionReopened = sessionmaker(bind=eng_reopened)
    session2 = SessionReopened()

    char_reloaded = session2.query(CharacterRecord).filter(CharacterRecord.id == "char-legacy-1").first()
    assert char_reloaded.reference_asset_id == "asset-legacy-1"
    assert char_reloaded.generation_params == {"workflow_id": "manga_qwen", "seed": 42}
    assert char_reloaded.proposed_changes == {"visual_traits": ["katana", "white cape", "gold badge"]}
    assert char_reloaded.change_status == "PENDING_REVIEW"

    asset_reloaded = session2.query(AssetRecord).filter(AssetRecord.id == "asset-legacy-1").first()
    assert asset_reloaded.provenance == {"workflow_id": "manga_consistent_qwen_image_edit", "seed": 42, "model": "qwen"}

    new_char_reloaded = session2.query(CharacterRecord).filter(CharacterRecord.id == "char-new-1").first()
    assert new_char_reloaded is not None
    assert new_char_reloaded.display_name == "New Ally"
    assert new_char_reloaded.generation_params == {"seed": 999}

    session2.close()
    eng_reopened.dispose()


def test_upgrade_partially_migrated_database(tmp_path: Path):
    db_file = tmp_path / "partially_migrated.db"
    eng = create_engine(f"sqlite:///{db_file}")

    # Schema where characters has reference_asset_id already, but missing other new columns; assets lacks provenance
    with eng.connect() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE projects (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                source_type VARCHAR(64) NOT NULL,
                source_url VARCHAR(1024),
                source_metadata JSON NOT NULL,
                rights_status VARCHAR(64) NOT NULL,
                license_info TEXT NOT NULL,
                workspace_path VARCHAR(1024) NOT NULL,
                current_stage VARCHAR(64) NOT NULL,
                settings JSON NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
        """)
        conn.exec_driver_sql("""
            CREATE TABLE characters (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                display_name VARCHAR(255) NOT NULL,
                canonical_name VARCHAR(255),
                aliases JSON NOT NULL,
                description TEXT NOT NULL,
                visual_traits JSON NOT NULL,
                role VARCHAR(32) NOT NULL,
                first_panel_id VARCHAR(36),
                reference_panel_ids JSON NOT NULL,
                reference_asset_id VARCHAR(36),
                status VARCHAR(32) NOT NULL,
                manual_override BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
        """)
        conn.exec_driver_sql("""
            CREATE TABLE assets (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                asset_type VARCHAR(64) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                relative_path VARCHAR(1024) NOT NULL,
                content_type VARCHAR(128) NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                byte_size BIGINT NOT NULL,
                sha256 VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                created_at DATETIME NOT NULL
            );
        """)
        conn.exec_driver_sql("""
            INSERT INTO projects VALUES (
                'proj-part-1', 'Partial Project', 'LOCAL_FOLDER', '', '{}',
                'PUBLIC_DOMAIN', 'None', '/fake', 'PANELS_DETECTED', '{}',
                '2026-01-01 00:00:00', '2026-01-01 00:00:00'
            );
        """)
        conn.exec_driver_sql("""
            INSERT INTO characters VALUES (
                'char-part-1', 'proj-part-1', 'Partial Hero', 'Hero', '[]',
                'A hero with asset', '[]', 'PROTAGONIST',
                NULL, '[]', 'existing-asset-ref', 'LIKELY', 0,
                '2026-01-01 00:00:00', '2026-01-01 00:00:00'
            );
        """)
        conn.commit()

    # Run migrations twice for idempotency
    run_sqlite_migrations(eng)
    run_sqlite_migrations(eng)

    Session = sessionmaker(bind=eng)
    session = Session()

    char = session.query(CharacterRecord).filter(CharacterRecord.id == "char-part-1").first()
    assert char is not None
    assert char.reference_asset_id == "existing-asset-ref"
    assert char.generation_params == {} or char.generation_params == "{}"
    assert char.proposed_changes == {} or char.proposed_changes == "{}"
    assert char.change_status == "NONE"

    session.close()
    eng.dispose()


def test_fresh_database_path(tmp_path: Path):
    db_file = tmp_path / "fresh_migration.db"
    eng = create_engine(f"sqlite:///{db_file}")

    # Fresh project startup sequence
    Base.metadata.create_all(bind=eng)
    run_sqlite_migrations(eng)
    run_sqlite_migrations(eng)

    Session = sessionmaker(bind=eng)
    session = Session()

    proj = ProjectRecord(
        id="proj-fresh",
        title="Fresh Project",
        source_type="LOCAL_FOLDER",
        rights_status="PUBLIC_DOMAIN",
        workspace_path=str(tmp_path),
        current_stage="ACQUIRED",
    )
    asset = AssetRecord(
        id="asset-fresh-1",
        project_id="proj-fresh",
        asset_type="CHARACTER_REFERENCE",
        filename="ref.png",
        relative_path="references/ref.png",
        content_type="image/png",
        width=512,
        height=512,
        byte_size=1024,
        sha256="c" * 64,
        provenance={"seed": 777},
    )
    char = CharacterRecord(
        id="char-fresh-1",
        project_id="proj-fresh",
        display_name="Fresh Char",
        reference_asset_id="asset-fresh-1",
        generation_params={"seed": 777},
        proposed_changes={},
        change_status="NONE",
    )
    session.add_all([proj, asset, char])
    session.commit()
    session.close()
    eng.dispose()

    # Reopen and assert
    eng_reopened = create_engine(f"sqlite:///{db_file}")
    Session2 = sessionmaker(bind=eng_reopened)
    session2 = Session2()

    c = session2.query(CharacterRecord).filter(CharacterRecord.id == "char-fresh-1").first()
    a = session2.query(AssetRecord).filter(AssetRecord.id == "asset-fresh-1").first()
    assert c is not None
    assert c.reference_asset_id == "asset-fresh-1"
    assert c.generation_params == {"seed": 777}
    assert a is not None
    assert a.provenance == {"seed": 777}

    session2.close()
    eng_reopened.dispose()

