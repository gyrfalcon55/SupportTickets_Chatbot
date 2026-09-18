"""
Ingest support_tickets.csv into a local SQLite database.

Reads CSV_PATH, normalizes columns and types, and recreates the tickets table
at DB_PATH using canonical column names expected by the LLM query planner.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from app.config import CSV_PATH, DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id           TEXT PRIMARY KEY,
    created_at          TEXT NOT NULL,
    category            TEXT,
    priority            TEXT,
    status              TEXT,
    response_time_hrs   REAL,
    resolution_time_hrs REAL,
    agent_id            TEXT,
    customer_rating     INTEGER,
    issue_summary       TEXT
);
"""

COLUMN_ALIASES = {
    "resp_time_hrs": "response_time_hrs",
    "response_time_hrs": "response_time_hrs",
    "resol_time_hrs": "resolution_time_hrs",
    "resolution_time_hrs": "resolution_time_hrs",
    "cust_rating": "customer_rating",
    "customer_rating": "customer_rating",
}

REQUIRED_COLUMNS = [
    "ticket_id",
    "created_at",
    "category",
    "priority",
    "status",
    "response_time_hrs",
    "resolution_time_hrs",
    "agent_id",
    "customer_rating",
    "issue_summary",
]


def _load_csv(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"CSV file not found at {csv_path}. Place support_tickets.csv "
            "there, or set CSV_PATH in your .env file."
        )

    df = pd.read_csv(csv_path)

    df.rename(
        columns=lambda column: COLUMN_ALIASES.get(
            column.strip(), column.strip()
        ),
        inplace=True,
    )

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in df.columns
    ]
    if missing_columns:
        raise ValueError(
            f"CSV is missing required columns: {missing_columns}"
        )

    df = df[REQUIRED_COLUMNS].copy()

    df["response_time_hrs"] = pd.to_numeric(
        df["response_time_hrs"], errors="coerce"
    )
    df["resolution_time_hrs"] = pd.to_numeric(
        df["resolution_time_hrs"], errors="coerce"
    )
    df["customer_rating"] = pd.to_numeric(
        df["customer_rating"], errors="coerce"
    )

    parsed_dates = pd.to_datetime(df["created_at"], errors="coerce")
    df["created_at"] = parsed_dates.dt.strftime("%Y-%m-%d %H:%M:%S")

    return df


def build_database(
    csv_path: Path = CSV_PATH,
    db_path: Path = DB_PATH,
) -> int:
    df = _load_csv(Path(csv_path))
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS tickets")
        conn.executescript(SCHEMA)

        df.to_sql("tickets", conn, if_exists="append", index=False)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_status "
            "ON tickets(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_priority "
            "ON tickets(priority)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_agent "
            "ON tickets(agent_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_created_at "
            "ON tickets(created_at)"
        )

        conn.commit()

    row_count = len(df)

    return f"Loaded {row_count} rows from {csv_path} into {db_path}"

