"""Database migration runner for AI Gateway migrations."""

import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from engine.config.settings import settings

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "database" / "migrations"


def get_db_engine():
    db_path = settings.app_data_dir / "panelflow.db"
    return create_engine(f"sqlite:///{db_path}")


def create_migrations_table(engine):
    """Create migrations tracking table if it doesn't exist."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_gateway_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()


def get_applied_migrations(engine):
    """Get list of already applied migrations."""
    applied = []
    with engine.connect() as conn:
        result = conn.execute(text("SELECT migration_id FROM ai_gateway_migrations"))
        applied = [row[0] for row in result]
    return applied


def run_migration(engine, migration_file):
    """Run a single migration file."""
    migration_id = migration_file.stem
    
    # Check if already applied
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT 1 FROM ai_gateway_migrations WHERE migration_id = :id"
        ), {"id": migration_id})
        if result.fetchone():
            return False  # Already applied
    
    # Read and execute migration
    sql_content = migration_file.read_text()
    
    with engine.connect() as conn:
        # SQLite requires explicit transaction handling
        with conn.begin():
            # Split by semicolon and execute each statement
            statements = [s.strip() for s in sql_content.split(';') if s.strip()]
            for statement in statements:
                if statement:
                    conn.execute(text(statement))
            
            # Record migration as applied
            conn.execute(text(
                "INSERT INTO ai_gateway_migrations (migration_id) VALUES (:id)"
            ), {"id": migration_id})
    
    return True


def migrate_ai_gateway():
    """Run all pending AI Gateway migrations."""
    engine = get_db_engine()
    create_migrations_table(engine)
    
    applied = get_applied_migrations(engine)
    
    # Find all migration files
    migration_files = sorted(
        MIGRATIONS_DIR.glob("*.sql"),
        key=lambda p: p.name
    )
    
    if not migration_files:
        print("No migration files found")
        return
    
    applied_count = 0
    for migration_file in migration_files:
        migration_id = migration_file.stem
        if migration_id in applied:
            print(f"✓ {migration_id} already applied")
            continue
        
        print(f"Applying {migration_file.name}...")
        try:
            success = run_migration(engine, migration_file)
            if success:
                print(f"✓ Applied {migration_id}")
                applied_count += 1
            else:
                print(f"⚠ Skipped {migration_id}")
        except Exception as e:
            print(f"✗ Failed to apply {migration_id}: {e}")
            raise
    
    print(f"\nMigration complete. Applied {applied_count} migrations.")


if __name__ == "__main__":
    migrate_ai_gateway()
