import logging

from app.llm.state import MessageState, latest_user_message
from app.llm.llm_service import large_model_with_fallback

logger = logging.getLogger(__name__)


async def classify_intent(state: MessageState) -> MessageState:
    """Classify the latest message as SQL analytics, formatting, or chat.
    
    """
    question = latest_user_message(state.get("messages", []))
    if not question:
        return {"intent": "formal_chat"}

    q = question.casefold()
    try:
        response = await large_model_with_fallback.ainvoke(
            f"""Classify as exactly anomaly, sql, format, or formal_chat.
                anomaly means a request to detect/explain resolution-time outliers or overdue tickets. sql means other support-ticket data questions.
                format means reformat an existing result; formal_chat means greeting or unrelated.
                Message: {question}"""
        )
        intent = str(response.content).strip().lower()
        if intent not in {"anomaly", "sql", "format", "formal_chat"}:
            raise ValueError("The model returned an unsupported intent.")
        return {"intent": intent}
    except Exception:
        logger.exception("Intent classification failed; using deterministic fallback")
        terms = ("ticket", "agent", "resolution", "response time", "rating",
                 "open", "escalat", "category", "priority", "status")
        return {"intent": "anomaly" if any(term in q for term in ("anomal", "outlier", "overdue")) else ("sql" if any(term in q for term in terms) else "formal_chat")}
