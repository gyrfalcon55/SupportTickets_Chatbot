from datetime import date
import pandas as pd
from app.api.services.json_sanitize_service import sanitize_for_json
from fastapi import HTTPException


def detect_anomalies(
    df: pd.DataFrame,
    as_of: date,
    overdue_hours: float,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Detect IQR resolution-time outliers and overdue high-priority unresolved tickets.
    Apply inclusive creation-date boundaries when supplied; overdue age is measured as of as_of.
    """
    required = {"ticket_id", "created_at", "priority", "status", "resolution_time_hrs"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing required columns: {sorted(missing)}")

    created_dates = pd.to_datetime(df["created_at"], errors="coerce").dt.date
    if start_date is not None:
        df = df.loc[created_dates >= start_date].copy()
        created_dates = created_dates.loc[df.index]
    if end_date is not None:
        df = df.loc[created_dates <= end_date].copy()
    else:
        df = df.loc[created_dates <= as_of].copy()

    resolved = df[
        df["status"].astype(str).str.strip().str.lower().eq("resolved")
    ].copy()
    resolved["resolution_time_hrs"] = pd.to_numeric(
        resolved["resolution_time_hrs"], errors="coerce"
    )
    valid = resolved[
        resolved["resolution_time_hrs"].notna()
        & (resolved["resolution_time_hrs"] >= 0)
    ].copy()

    iqr_summary = {
        "valid_resolved_count": int(len(valid)),
        "q1": None,
        "q3": None,
        "iqr": None,
        "lower_bound": None,
        "upper_bound": None,
    }
    resolution_outliers = []

    if not valid.empty:
        q1 = float(valid["resolution_time_hrs"].quantile(0.25))
        q3 = float(valid["resolution_time_hrs"].quantile(0.75))
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        iqr_summary.update(
            q1=q1,
            q3=q3,
            iqr=iqr,
            lower_bound=lower,
            upper_bound=upper,
        )
        outliers = valid[
            (valid["resolution_time_hrs"] < lower)
            | (valid["resolution_time_hrs"] > upper)
        ]
        resolution_outliers = [
            sanitize_for_json(row)
            for row in outliers.to_dict(orient="records")
        ]

    unresolved_statuses = {
        "open", "escalated", "pending", "in progress", "unresolved"
    }
    high_priority = df[
        df["status"].astype(str).str.strip().str.lower().isin(unresolved_statuses)
        & df["priority"].astype(str).str.strip().str.lower().isin({"critical", "high"})
    ].copy()

    created = pd.to_datetime(high_priority["created_at"], errors="coerce")
    reference_end = pd.Timestamp(as_of) + pd.Timedelta(days=1)
    high_priority["age_hours"] = (
        reference_end - created
    ).dt.total_seconds() / 3600

    overdue = high_priority[
        created.notna() & (high_priority["age_hours"] > overdue_hours)
    ].copy()
    overdue_records = [
        sanitize_for_json(row) for row in overdue.to_dict(orient="records")
    ]

    return sanitize_for_json({
        "as_of": as_of.isoformat(),
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else as_of.isoformat(),
        "overdue_threshold_hours": overdue_hours,
        "resolution_time_iqr": iqr_summary,
        "resolution_time_outliers": resolution_outliers,
        "overdue_unresolved_high_priority": overdue_records,
        "counts": {
            "resolution_time_outliers": len(resolution_outliers),
            "overdue_unresolved_high_priority": len(overdue_records),
        },
    })
