from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from engine.config.settings import settings
from engine.database.models import Base

# Create SQLite engine with WAL mode and foreign key constraints enabled
engine = create_engine(
    settings.get_database_url(),
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
    except Exception:
        pass

def init_db():
    """Initializes tables in database and runs non-destructive migrations."""
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)

def get_db():
    """FastAPI dependency for database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
