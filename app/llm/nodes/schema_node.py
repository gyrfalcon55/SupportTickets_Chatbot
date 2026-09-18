import json
import logging
from app.llm.state import MessageState

logger = logging.getLogger(__name__)

# This project currently uses a single SQLite table named support_tickets.
RAW_SCHEMA = [{
    "schema": None,
    "table": "tickets",
    "description": "Customer support tickets",
    "columns": {
        "ticket_id": {"type": "TEXT", "description": "Unique ticket ID"},
        "created_at": {"type": "TEXT", "description": "Ticket creation timestamp"},
        "category": {"type": "TEXT", "description": "Billing, Technical, General"},
        "priority": {"type": "TEXT", "description": "Low, Medium, High, Critical"},
        "status": {"type": "TEXT", "description": "Open, Resolved, Escalated"},
        "response_time_hrs": {"type": "TEXT", "description": "Hours to first response"},
        "resolution_time_hrs": {"type": "TEXT", "description": "Hours to resolution; null if unresolved"},
        "agent_id": {"type": "TEXT", "description": "Assigned agent ID"},
        "customer_rating": {"type": "TEXT", "description": "Rating 1–5; may be null"},
        "issue_summary": {"type": "TEXT", "description": "Issue summary"},
    },
}]


async def relevant_schema(state: MessageState) -> MessageState:
    """Serialize the supported ticket schema for the SQL-generation node.
    Return a clear state error if schema serialization unexpectedly fails.
    """
    try:
        return {"schema": json.dumps(RAW_SCHEMA, indent=2)}
    except (TypeError, ValueError):
        logger.exception("Could not serialize ticket schema")
        return {"error": "Could not prepare the database schema."}
