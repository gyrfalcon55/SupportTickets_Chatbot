from fastapi import APIRouter, HTTPException
from app.api.services.get_connection_service import get_connection

router = APIRouter()

@router.get("/health")
def health():
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database health check failed: {exc}")