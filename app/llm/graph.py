"""
LangGraph workflow for support-ticket analytics.

The graph is compiled with MemorySaver so clarification can be resumed
using the same thread_id.
"""
import asyncio

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
import logging
from app.llm.state import MessageState
from app.llm.nodes import (
    chat_node,
    executor_node,
    formatter_node,
    intent_node,
    schema_node,
    sql_builder_node,
    clarification_node,
    anomaly_node,
)

logger = logging.getLogger(__name__)

def route_after_intent(state: MessageState) -> str:
    """Select the workflow branch based on the classified intent.
    Route SQL questions, formatting requests, and general chat separately.
    """
    intent = state.get("intent", "formal_chat")
    if intent == "anomaly":
        return "check_clarification"
    if intent == "sql":
        return "check_clarification"
    if intent == "format":
        return "format_output"
    return "chat_node"


def route_after_clarification_check(state: MessageState) -> str:
    """Choose clarification or schema retrieval based on current state.
    Any existing error is sent to formatting so it is not lost.
    """
    if state.get("error"):
        return "format_output"
    if state.get("needs_clarification"):
        return "ask_clarification"
    return "anomaly_node" if state.get("intent") == "anomaly" else "relevant_schema"


def route_after_ask_clarification(state: MessageState) -> str:
    """Route failed clarification parsing to output instead of SQL generation.
    Continue to schema retrieval only when the answer was resolved successfully.
    """
    if state.get("error"):
        return "format_output"
    return "anomaly_node" if state.get("intent") == "anomaly" else "relevant_schema"


builder = StateGraph(MessageState)

# Nodes
builder.add_node("classify_intent", intent_node.classify_intent)
builder.add_node("anomaly_node", anomaly_node.anomaly_node)

builder.add_node("check_clarification", clarification_node.check_clarification)

builder.add_node("ask_clarification", clarification_node.ask_clarification)

builder.add_node("relevant_schema", schema_node.relevant_schema)

builder.add_node("generate_sql", sql_builder_node.generate_sql)

builder.add_node("execute_sql", executor_node.execute_sql)

builder.add_node("format_output", formatter_node.format_output)

builder.add_node("chat_node", chat_node.chat_node)


# Edges
builder.add_edge(START, "classify_intent")

builder.add_conditional_edges(
    "classify_intent",
    route_after_intent,
    {
        "check_clarification": "check_clarification",
        "format_output": "format_output",
        "chat_node": "chat_node",
    },
)

builder.add_conditional_edges(
    "check_clarification",
    route_after_clarification_check,
    {
        "ask_clarification": "ask_clarification",
        "relevant_schema": "relevant_schema",
        "format_output": "format_output",
        "anomaly_node": "anomaly_node",
    },
)

builder.add_conditional_edges(
    "ask_clarification",
    route_after_ask_clarification,
    {
        "relevant_schema": "relevant_schema",
        "anomaly_node": "anomaly_node",
        "format_output": "format_output",
    },
)

builder.add_edge("anomaly_node", END)

builder.add_edge("relevant_schema", "generate_sql")

builder.add_edge("generate_sql", "execute_sql")

builder.add_edge("execute_sql", "format_output")

builder.add_edge("format_output", END)

builder.add_edge("chat_node", END)


checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)



async def run_query(question: str, thread_id: str = "session_001"):
    """Run a new question through the compiled, checkpointed graph.
    Validate inputs and log execution failures before propagating them.
    """
    if not question or not question.strip():
        raise ValueError("question must not be empty")
    config = {"configurable": {"thread_id": thread_id}}
    try:
        return await graph.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            config=config,
        )
    except Exception:
        logger.exception("Graph execution failed")
        raise


async def resume_query(answer: str, thread_id: str = "session_001"):
    """Resume a paused graph with the user's clarification answer.
    Use the same thread ID so LangGraph can load the checkpointed state.
    """
    if not answer or not answer.strip():
        raise ValueError("answer must not be empty")
    config = {"configurable": {"thread_id": thread_id}}
    try:
        return await graph.ainvoke(Command(resume=answer), config=config)
    except Exception:
        logger.exception("Graph resume failed")
        raise


async def main():
    """Run a terminal-based manual test loop for the graph.
    Handle clarification interrupts and keep the session alive after errors.
    """
    thread_id = "session_001"
    while True:
        question = input("\nAsk a support-ticket question (or 'quit'): ").strip()
        if question.lower() in {"quit", "exit"}:
            break
        if not question:
            continue

        result = await run_query(question, thread_id)
        while result.get("__interrupt__"):
            for item in result["__interrupt__"]:
                value = getattr(item, "value", {}) or {}
                print("\nClarification:", value.get("question", "Please clarify."))
            result = await resume_query(input("Your answer: ").strip(), thread_id)

        print("\n", result.get("result", result.get("error", result)))


if __name__ == "__main__":
    asyncio.run(main())
