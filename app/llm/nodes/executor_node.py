
import asyncio
import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.llm.state import MessageState

from app.config import DB_PATH

logger = logging.getLogger(__name__)



def extract_json_array(raw: Any) -> list[dict]:
    """Extract query objects from JSON, Markdown-wrapped JSON, or parsed data.
    Reject unsupported or malformed model output with a descriptive exception.
    """

    if isinstance(raw, list):
        parsed = raw

    elif isinstance(raw, dict):
        parsed = [raw]

    elif isinstance(raw, str):
        cleaned = raw.strip()

        # Remove Markdown fences.
        cleaned = re.sub(
            r"^\s*```(?:json)?\s*|\s*```\s*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()

        try:
            parsed = json.loads(cleaned)

        except json.JSONDecodeError:
            # Handle extra text surrounding a JSON array.
            decoder = json.JSONDecoder()
            parsed = None

            for index, char in enumerate(cleaned):
                if char == "[":
                    try:
                        candidate, _ = decoder.raw_decode(
                            cleaned[index:]
                        )

                        if isinstance(candidate, list):
                            parsed = candidate
                            break

                    except json.JSONDecodeError:
                        continue

            if parsed is None:
                raise ValueError(
                    "No valid JSON array found in model response."
                )

    else:
        raise ValueError(
            f"Unsupported generated_sql type: {type(raw).__name__}"
        )

    if not isinstance(parsed, list):
        raise ValueError(
            "Model output must be a JSON array of query objects."
        )

    return parsed


def _connect_readonly():
    """Open the configured SQLite database in read-only URI mode.
    Raise a clear error if the database file does not exist.
    """

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"SQLite database not found: {DB_PATH}"
        )

    uri = DB_PATH.resolve().as_uri() + "?mode=ro"

    return sqlite3.connect(uri, uri=True)



def get_dataset_date_range():
    """Return the earliest and latest valid ticket creation dates.
    Use a read-only connection and return None values when no dates exist.
    """

    with _connect_readonly() as conn:
        row = conn.execute(
            """
            SELECT
                MIN(date("created_at")),
                MAX(date("created_at"))
            FROM "tickets"
            WHERE date("created_at") IS NOT NULL
            """
        ).fetchone()

    return {
        "min_date": row[0],
        "max_date": row[1],
    }



def validate_readonly_sql(sql: str) -> str:
    """Validate that input contains one read-only SELECT or WITH statement.
    SQLite read-only mode and the authorizer provide additional enforcement.
    """

    if not isinstance(sql, str):
        raise ValueError("SQL query must be a string.")

    sql = sql.strip()

    # Remove a trailing semicolon.
    sql = sql.rstrip(";").strip()

    if not sql:
        raise ValueError("SQL query is empty.")


    if ";" in sql:
        raise ValueError(
            "Provide exactly one SQL statement."
        )


    statement = re.sub(
        r"(?s)^\s*(?:(?:--[^\n]*(?:\n|$))|(?:/\*.*?\*/)\s*)*",
        "",
        sql,
    ).lstrip()

    if not re.match(
        r"(?i)^(SELECT|WITH)\b",
        statement,
    ):
        raise ValueError(
            "Only read-only SELECT queries are allowed."
        )

    return sql



def execute_sqlite_query(sql: str) -> list[dict]:
    """Execute a validated query against SQLite in read-only mode.
    Return rows as dictionaries and deny non-read operations through an authorizer.
    """

    sql = validate_readonly_sql(sql)

    with _connect_readonly() as conn:
        conn.row_factory = sqlite3.Row

        def authorizer(
            action,
            arg1,
            arg2,
            db_name,
            trigger,
        ):
            allowed_actions = {
                sqlite3.SQLITE_SELECT,
                sqlite3.SQLITE_READ,
                sqlite3.SQLITE_FUNCTION,
                sqlite3.SQLITE_RECURSIVE,
            }

            if action in allowed_actions:
                return sqlite3.SQLITE_OK

            return sqlite3.SQLITE_DENY

        conn.set_authorizer(authorizer)

        rows = conn.execute(sql).fetchall()

        return [
            dict(row)
            for row in rows
        ]




async def execute_sql(state: MessageState) -> MessageState:
    """Execute the SQL JSON produced by the SQL builder and collect row results.
    Convert parsing and execution failures into structured workflow state errors.
    """

    try:
        raw_output = state.get("generated_sql", "")

        logger.debug("Generated SQL output received")

        queries = extract_json_array(raw_output)

        if not queries:
            raise ValueError(
                "Model returned an empty query list."
            )

        results = []

        for item in queries:

            if not isinstance(item, dict):
                results.append({
                    "error": "Invalid query object."
                })
                continue

            if "error" in item:
                results.append({
                    "error": str(item["error"])
                })
                continue

            sql = item.get("query")

            if not isinstance(sql, str):
                results.append({
                    "table": item.get("table", "tickets"),
                    "error": "Missing SQL query."
                })
                continue

            try:
                logger.debug("Executing generated read-only SQL")

                data = await asyncio.to_thread(
                    execute_sqlite_query,
                    sql,
                )

                results.append({
                    "table": item.get("table", "tickets"),
                    "data": data,
                })

            except Exception as exc:
                results.append({
                    "table": item.get("table", "tickets"),
                    "error": str(exc),
                })

        return {
            "sql_result": json.dumps(
                results,
                default=str,
            ),
            "error": "",
        }

    except Exception as exc:
        error_message = str(exc)

        logger.exception("SQL execution failed")

        return {
            "sql_result": json.dumps([
                {"error": error_message}
            ]),
            "error": error_message,
        }