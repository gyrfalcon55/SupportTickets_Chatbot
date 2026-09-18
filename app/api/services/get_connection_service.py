from pathlib import Path
from fastapi import HTTPException
import sqlite3
from app.config import DB_PATH

def get_connection():
    if not DB_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
