
import json
import logging

from langchain_core.prompts import ChatPromptTemplate

from app.llm.state import MessageState, latest_user_message
from app.llm.llm_service import large_model_with_fallback
from app.config import GENERATE_SQL_PROMPT_TEXT

logger = logging.getLogger(__name__)


def _recent_context(messages, limit=8):
    """Build context from recent conversation messages."""
    return "\n".join(
        f"{message.type}: {message.content}"
        for message in messages[-limit:]
    )


def _parse_schema(schema_text: str) -> list:
    """Parse schema JSON and fail clearly if it is invalid."""
    try:
        schema = json.loads(schema_text or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Schema is not valid JSON.") from exc

    if not isinstance(schema, list):
        raise ValueError("Schema must be a JSON array.")

    return schema


def _extract_json_response(content) -> str:
    """
    Extract the model's JSON response.
    The executor should still independently validate the SQL.
    """
    if isinstance(content, list):
        # Some model integrations return content blocks.
        content = "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict)
        )

    if not isinstance(content, str) or not content.strip():
        raise ValueError("The model returned an empty SQL response.")

    content = content.strip()

    # Remove optional Markdown code fences.
    if content.startswith("```"):
        lines = content.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        content = "\n".join(lines).strip()

    # Validate that the response is JSON.
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "The model did not return valid JSON."
        ) from exc

    if not isinstance(parsed, list) or len(parsed) != 1:
        raise ValueError(
            "Expected a JSON array containing exactly one object."
        )

    item = parsed[0]

    if not isinstance(item, dict):
        raise ValueError("The response object must be a JSON object.")

    if "error" in item:
        return json.dumps([{"error": str(item["error"])}])

    if item.get("table") != "tickets":
        raise ValueError("The response must use the tickets table.")

    query = item.get("query")

    if not isinstance(query, str) or not query.strip():
        raise ValueError("The response does not contain a SQL query.")

    return json.dumps(
        [{"table": "tickets", "query": query.strip()}],
        ensure_ascii=False,
    )


async def generate_sql(state: MessageState) -> MessageState:
    """Generate a structured, read-only SQLite query from the current question.
    Return a structured SQL response or a clear error.
    """

    messages = state.get("messages", [])
    question = latest_user_message(messages)

    if not question:
        return {"error": "No user question found."}

    try:
        schema_data = _parse_schema(state.get("schema", "[]"))
    except ValueError as exc:
        logger.exception("Invalid schema")
        return {"error": str(exc)}

    schema_block = json.dumps(
        schema_data,
        indent=2,
        ensure_ascii=False,
    )

    context = _recent_context(messages[:-1])

    clarification = state.get("clarification_answer", "") or ""
    date_range = state.get("date_range") or {}
    clarification_kind = state.get("clarification_kind", "")
    clarification_answer = clarification.strip()

    q_lower = question.casefold()
    full_dataset_intent = any(phrase in q_lower for phrase in (
        "entire dataset", "whole dataset", "all tickets", "across the dataset",
        "full dataset", "overall"
    ))



    date_followup_intent = any(phrase in q_lower for phrase in (
        "same period", "that period", "those dates", "same date range",
        "that week", "that month", "for that range", "for those dates"
    ))




    looks_like_date_answer = bool(__import__("re").search(
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
        r"dec(?:ember)?|\d{4}-\d{2}-\d{2})\b", q_lower
    ))

    
    use_clarified_range = bool(
        date_range.get("start") and date_range.get("end")
        and not full_dataset_intent
        and (date_followup_intent or (clarification and looks_like_date_answer))
    )




    if clarification_answer and date_range.get("start") and date_range.get("end"):
        date_context = (
            f"User answered the pending {clarification_kind} clarification with "
            f"'{clarification_answer}'. Apply this exact date range to the original "
            f"question: {date_range['start']} through {date_range['end']} inclusive. "
            "Use date(created_at) boundaries; do not use date('now')."
        )
    elif use_clarified_range:
        date_context = (
            f"ACTIVE clarified date range: {date_range['start']} through "
            f"{date_range['end']}. Use it only if the latest question refers "
            "to that range or is the answer to the date clarification."
        )
    else:
        date_context = "No active date range supplied for this question."

    prompt = ChatPromptTemplate.from_template(
        GENERATE_SQL_PROMPT_TEXT
    )

    try:
        response = await (
            prompt | large_model_with_fallback
        ).ainvoke(
            {
                "schema_block": schema_block,
                "context": context,
                "clarification": clarification,
                "date_context": date_context,
                "question": question,
            }
        )

        generated_sql = _extract_json_response(response.content)

        logger.info("Generated SQL response: %s", generated_sql)

        return {
            "generated_sql": generated_sql,
            "error": None,
        }

    except Exception as exc:
        logger.exception("SQL generation failed")

        return {
            "generated_sql": None,
            "error": f"SQL generation failed: {exc}",
        }