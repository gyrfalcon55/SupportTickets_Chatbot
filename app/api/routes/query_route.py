from fastapi import APIRouter, HTTPException
from app.api.models.request_models import QueryRequest, ResumeRequest
import uuid
from app.api.services.extract_interrupts_service import extract_interrupts
from app.api.services.json_sanitize_service import sanitize_for_json
from app.llm.graph import resume_query, run_query



router = APIRouter()

@router.post("/query")
async def natural_language_query(payload: QueryRequest):
    """
    Submit a natural-language question to the LangGraph.

    If clarification is required, the response includes thread_id and
    clarification; continue using POST /query/resume with that thread_id.
    """
    thread_id = payload.thread_id or str(uuid.uuid4())
    try:
        result = await run_query(payload.question, thread_id=thread_id)
        interruptions = extract_interrupts(result)

        if interruptions:
            return sanitize_for_json({
                "status": "needs_clarification",
                "question": payload.question,
                "thread_id": thread_id,
                "clarification": interruptions,
            })

        return sanitize_for_json({
            "status": "completed",
            "question": payload.question,
            "thread_id": thread_id,
            "answer": result.get("result", result.get("error", result)),
        })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"NL query failed: {exc}")


@router.post("/query/resume")
async def resume_natural_language_query(payload: ResumeRequest):
    """Answer a LangGraph clarification and continue the same conversation."""
    try:
        result = await resume_query(payload.answer, thread_id=payload.thread_id)
        interruptions = extract_interrupts(result)

        if interruptions:
            return sanitize_for_json({
                "status": "needs_clarification",
                "thread_id": payload.thread_id,
                "clarification": interruptions,
            })

        return sanitize_for_json({
            "status": "completed",
            "thread_id": payload.thread_id,
            "answer": result.get("result", result.get("error", result)),
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not resume query: {exc}")
