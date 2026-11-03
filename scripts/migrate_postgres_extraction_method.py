from app.database.db_manager import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS extraction_method VARCHAR;"))
    conn.commit()
    print("Postgres RDS Migration: extraction_method added to processing_jobs successfully!")
