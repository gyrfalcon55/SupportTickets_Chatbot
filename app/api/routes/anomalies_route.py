from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.api.services.detect_anomalies_service import detect_anomalies
from app.api.services.load_tickets_service import load_tickets

router = APIRouter()


@router.get("/anomalies")
def anomalies(
    as_of: Optional[date] = Query(
        default=None,
        description="Reference date; defaults to latest created_at date in the dataset",
    ),
    overdue_hours: float = Query(default=24, gt=0),
    start_date: Optional[date] = Query(
        default=None,
        description="Inclusive ticket-creation start date; omit for cumulative analysis",
    ),
    end_date: Optional[date] = Query(
        default=None,
        description="Inclusive ticket-creation end date; defaults to as_of",
    ),
):
    """Load tickets and validate the requested analysis period.
    Return deterministic anomaly statistics for the requested inclusive date range.
    """
    df = load_tickets()
    if df.empty:
        return {
            "as_of": as_of.isoformat() if as_of else None,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "counts": {
                "resolution_time_outliers": 0,
                "overdue_unresolved_high_priority": 0,
            },
            "resolution_time_iqr": {},
            "resolution_time_outliers": [],
            "overdue_unresolved_high_priority": [],
        }

    if "created_at" not in df.columns:
        raise HTTPException(status_code=500, detail="Missing required column: created_at")

    dates = __import__("pandas").to_datetime(df["created_at"], errors="coerce").dropna()
    if dates.empty:
        raise HTTPException(
            status_code=422,
            detail="No valid created_at dates available; supply as_of explicitly.",
        )

    dataset_max = dates.max().date()
    if as_of is None:
        as_of = end_date or dataset_max
    if end_date is None:
        end_date = as_of

    if start_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if end_date > as_of:
        as_of = end_date

    return detect_anomalies(
        df,
        as_of=as_of,
        overdue_hours=overdue_hours,
        start_date=start_date,
        end_date=end_date,
    )
