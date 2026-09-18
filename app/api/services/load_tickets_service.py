import pandas as pd
from app.api.services.get_connection_service import get_connection
from fastapi import HTTPException

TABLE_NAME = "tickets"

def load_tickets() -> pd.DataFrame:
    try:
        with get_connection() as conn:
            return pd.read_sql_query(f'SELECT * FROM "{TABLE_NAME}"', conn)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read tickets table: {exc}")
