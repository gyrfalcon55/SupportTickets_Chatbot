import logging

from langchain_core.messages import AIMessage
from app.llm.state import MessageState, latest_user_message
from app.llm.llm_service import large_model_with_fallback

logger = logging.getLogger(__name__)


async def chat_node(state: MessageState) -> MessageState:
    """Generate a conversational response for non-analytics requests.
    Store the answer as an AI message and as the workflow result.
    """
    question = latest_user_message(state.get("messages", []))
    if not question:
        answer = "Hello! How can I help you?"
    else:
        try:
            response = await large_model_with_fallback.ainvoke(question)
            answer = str(response.content).strip()
            if not answer:
                answer = "I couldn't generate a response. Please try again."
        except Exception:
            logger.exception("Chat response generation failed")
            answer = "I couldn't generate a response right now. Please try again."
    return {"messages": [AIMessage(content=answer)], "result": answer}
