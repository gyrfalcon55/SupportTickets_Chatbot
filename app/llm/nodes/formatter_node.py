import json
import logging

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from app.llm.state import MessageState, latest_user_message
from app.llm.llm_service import large_model_with_fallback
from app.config import FORMAT_SQL_PROMPT_TEXT

logger = logging.getLogger(__name__)


async def format_output(state: MessageState) -> MessageState:
    """Format SQL results into a concise, evidence-grounded user response.
    Surface upstream errors directly and never invent results when formatting fails.
    """
    question = latest_user_message(state.get("messages", []))
    if state.get("error"):
        answer = f"Request could not be completed: {state['error']}"
        return {"messages": [AIMessage(content=answer)], "result": answer}

    raw = state.get("sql_result", "")
    if not raw:
        answer = "There is no query result to format."
        return {"messages": [AIMessage(content=answer)], "result": answer}

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        payload = None

    if isinstance(payload, list):
        errors = [
            item.get("error") for item in payload
            if isinstance(item, dict) and item.get("error")
        ]
        datasets = [
            item.get("data") for item in payload
            if isinstance(item, dict) and "data" in item
        ]
        if errors and not datasets:
            answer = "Query execution failed: " + "; ".join(map(str, errors))
            return {"messages": [AIMessage(content=answer)], "result": answer}
        if datasets and all(data == [] for data in datasets):
            answer = (
                "The query ran successfully but found no matching records. "
                "This does not mean the dataset is empty."
            )
            return {"messages": [AIMessage(content=answer)], "result": answer}

    prompt = ChatPromptTemplate.from_template(
        FORMAT_SQL_PROMPT_TEXT
    )
    try:
        response = await (prompt | large_model_with_fallback).ainvoke({
            "question": question,
            "data": raw,
        })
        answer = str(response.content).strip()
        if not answer:
            raise ValueError("The model returned an empty formatted response.")
    except Exception:
        logger.exception("Could not format SQL result with the LLM")
        answer = "The query completed, but I couldn't format its result. Please inspect the raw result or try again."
    return {"messages": [AIMessage(content=answer)], "result": answer}
