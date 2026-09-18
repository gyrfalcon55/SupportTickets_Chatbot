from typing import Annotated, NotRequired, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class MessageState(TypedDict):
    """Declare the shared state fields used by the LangGraph workflow.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    intent: NotRequired[str]
    schema: NotRequired[str]
    generated_sql: NotRequired[str | None]
    sql_result: NotRequired[str]
    result: NotRequired[str]
    error: NotRequired[str | None]
    needs_clarification: NotRequired[bool]
    clarification_question: NotRequired[str]
    clarification_answer: NotRequired[str]
    clarification_kind: NotRequired[str]
    date_range: NotRequired[dict[str, str]]
    anomaly_data: NotRequired[str]


def latest_user_message(messages: list[BaseMessage]) -> str:
    """Find the latest human message in the conversation history.
    Return an empty string when no human-authored message is present.
    """
    for message in reversed(messages):
        if getattr(message, "type", None) == "human":
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""
