import asyncio
import json
import logging
from datetime import date

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from app.llm.state import MessageState, latest_user_message
from app.llm.llm_service import large_model_with_fallback
from app.api.services.load_tickets_service import load_tickets
from app.api.services.detect_anomalies_service import detect_anomalies
from app.llm.nodes.executor_node import get_dataset_date_range

logger = logging.getLogger(__name__)

async def anomaly_node(state: MessageState) -> MessageState:
    """Run deterministic anomaly calculations on the requested ticket period.
    Ask the LLM to explain only the computed results and their date scope.
    """
    try:
        rng = state.get("date_range") or {}
        dataset = await asyncio.to_thread(get_dataset_date_range)
        end = date.fromisoformat(rng.get("end") or dataset["max_date"])
        start = date.fromisoformat(rng["start"]) if rng.get("start") else None
        if start and start > end:
            raise ValueError("Start date must be on or before end date.")
        df = await asyncio.to_thread(load_tickets)
        stats = await asyncio.to_thread(detect_anomalies, df, end, 24.0, start)
        raw = json.dumps(stats, ensure_ascii=False, default=str)
        prompt = ChatPromptTemplate.from_template(
            "Answer the user's anomaly question using ONLY this computed API result. "
            "Explain the date scope, counts, and IQR bounds when present. Do not infer "
            "that no anomalies exist unless the result count is zero. Result: {data}\nQuestion: {question}"
        )
        response = await (prompt | large_model_with_fallback).ainvoke({
            "data": raw, "question": latest_user_message(state.get("messages", []))
        })
        answer = str(response.content).strip() or "Anomaly calculations completed; see returned metrics."
        return {"anomaly_data": raw, "messages": [AIMessage(content=answer)], "result": answer, "error": None}
    except Exception as exc:
        logger.exception("Anomaly analysis failed")
        message = f"Anomaly analysis failed: {exc}"
        return {"error": message, "result": message, "messages": [AIMessage(content=message)]}
