from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from engine.config.settings import settings
from engine.database.models import Base
import logging

logger = logging.getLogger("panelflow.database")

DATABASE_URL = settings.get_database_url()
if not DATABASE_URL.lower().startswith("sqlite"):
    raise RuntimeError("PanelFlow currently supports SQLite only; configure a sqlite database URL")

# Create SQLite engine with WAL mode and foreign key constraints enabled
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def run_sqlite_migrations(db_engine):
    """Safely adds missing columns to existing SQLite tables without data loss."""
    if db_engine.dialect.name != "sqlite":
        raise RuntimeError("PanelFlow SQLite migrations require a SQLite engine")
    try:
        with db_engine.connect() as conn:
            # 1. Panel columns
            res_panels = conn.exec_driver_sql("PRAGMA table_info(panels)").fetchall()
            existing_panel_cols = {row[1] for row in res_panels}
            if existing_panel_cols:
                panel_cols_to_add = [
                    ("normalized_x", "FLOAT DEFAULT 0.0"),
                    ("normalized_y", "FLOAT DEFAULT 0.0"),
                    ("normalized_width", "FLOAT DEFAULT 0.0"),
                    ("normalized_height", "FLOAT DEFAULT 0.0"),
                    ("polygon_json", "TEXT NULL"),
                    ("detection_method", "VARCHAR(32) DEFAULT 'AUTO'"),
                    ("panel_type", "VARCHAR(32) DEFAULT 'STANDARD'"),
                    ("manually_modified", "BOOLEAN DEFAULT 0"),
                    ("reading_direction", "VARCHAR(16) DEFAULT 'ltr'"),
                ]
                for col_name, col_type in panel_cols_to_add:
                    if col_name not in existing_panel_cols:
                        conn.exec_driver_sql(f"ALTER TABLE panels ADD COLUMN {col_name} {col_type}")
                        conn.commit()

            # 2. TextRegion columns
            res_tr = conn.exec_driver_sql("PRAGMA table_info(text_regions)").fetchall()
            existing_tr_cols = {row[1] for row in res_tr}
            if existing_tr_cols:
                tr_cols_to_add = [
                    ("sequence_in_panel", "INTEGER DEFAULT 1"),
                    ("sequence_global", "INTEGER DEFAULT 1"),
                    ("page_x", "INTEGER DEFAULT 0"),
                    ("page_y", "INTEGER DEFAULT 0"),
                    ("page_width", "INTEGER DEFAULT 0"),
                    ("page_height", "INTEGER DEFAULT 0"),
                    ("region_type", "VARCHAR(32) DEFAULT 'SPEECH'"),
                    ("confidence", "FLOAT DEFAULT 1.0"),
                    ("status", "VARCHAR(32) DEFAULT 'DETECTED'"),
                    ("detection_method", "VARCHAR(32) DEFAULT 'AUTO'"),
                    ("crop_filename", "VARCHAR(255) DEFAULT ''"),
                    ("crop_sha256", "VARCHAR(64) DEFAULT ''"),
                    ("raw_text", "TEXT DEFAULT ''"),
                    ("raw_confidence", "FLOAT DEFAULT 0.0"),
                    ("raw_polygon", "JSON DEFAULT '[]'"),
                    ("ocr_engine", "VARCHAR(64) DEFAULT ''"),
                    ("ocr_engine_version", "VARCHAR(32) DEFAULT ''"),
                    ("ocr_extracted_at", "DATETIME NULL"),
                    ("corrected_text", "TEXT DEFAULT ''"),
                    ("corrected_by", "VARCHAR(64) DEFAULT ''"),
                    ("corrected_at", "DATETIME NULL"),
                    ("correction_status", "VARCHAR(32) DEFAULT 'UNEDITED'"),
                    ("speaker_character_id", "VARCHAR(36) NULL"),
                    ("speaker_confidence", "FLOAT NULL"),
                    ("speaker_assignment_method", "VARCHAR(32) NULL"),
                ]
                for col_name, col_type in tr_cols_to_add:
                    if col_name not in existing_tr_cols:
                        conn.exec_driver_sql(f"ALTER TABLE text_regions ADD COLUMN {col_name} {col_type}")
                        conn.commit()

            # 3. Jobs table columns
            res_jobs = conn.exec_driver_sql("PRAGMA table_info(jobs)").fetchall()
            existing_jobs_cols = {row[1] for row in res_jobs}
            if existing_jobs_cols:
                jobs_cols_to_add = [
                    ("priority", "INTEGER DEFAULT 10"),
                    ("depends_on_job_id", "VARCHAR(36) NULL"),
                    ("requires_gpu", "BOOLEAN DEFAULT 0"),
                    ("gpu_vram_mb", "INTEGER DEFAULT 0"),
                    ("cpu_units", "INTEGER DEFAULT 1"),
                    ("worker_lease_id", "VARCHAR(64) NULL"),
                    ("lease_expires_at", "DATETIME NULL"),
                    ("retry_count", "INTEGER DEFAULT 0"),
                    ("max_retries", "INTEGER DEFAULT 3"),
                ]
                for col_name, col_type in jobs_cols_to_add:
                    if col_name not in existing_jobs_cols:
                        conn.exec_driver_sql(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
                        conn.commit()

            # 4. Assets columns
            res_assets = conn.exec_driver_sql("PRAGMA table_info(assets)").fetchall()
            existing_asset_cols = {row[1] for row in res_assets}
            if existing_asset_cols:
                asset_cols_to_add = [
                    ("provenance", "JSON DEFAULT '{}'"),
                ]
                for col_name, col_type in asset_cols_to_add:
                    if col_name not in existing_asset_cols:
                        conn.exec_driver_sql(f"ALTER TABLE assets ADD COLUMN {col_name} {col_type}")
                        conn.commit()

            # 5. Characters columns
            res_chars = conn.exec_driver_sql("PRAGMA table_info(characters)").fetchall()
            existing_char_cols = {row[1] for row in res_chars}
            if existing_char_cols:
                char_cols_to_add = [
                    ("reference_asset_id", "VARCHAR(36) NULL"),
                    ("generation_params", "JSON DEFAULT '{}'"),
                    ("proposed_changes", "JSON DEFAULT '{}'"),
                    ("change_status", "VARCHAR(32) DEFAULT 'NONE'"),
                ]
                for col_name, col_type in char_cols_to_add:
                    if col_name not in existing_char_cols:
                        conn.exec_driver_sql(f"ALTER TABLE characters ADD COLUMN {col_name} {col_type}")
                        conn.commit()
    except Exception as exc:
        logger.exception("SQLite schema migration failed")
        raise RuntimeError("PanelFlow SQLite schema migration failed") from exc


def init_db():
    """Initializes tables in database and runs non-destructive migrations."""
    # Register additive history tables even when init_db is called without app imports.
    from engine.history import models as _history_models
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)

def get_db():
    """FastAPI dependency for database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
