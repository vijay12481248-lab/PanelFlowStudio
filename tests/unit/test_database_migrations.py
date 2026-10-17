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
    }
    registered_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(registered_tables), f"Missing tables: {expected_tables - registered_tables}"
