


def extract_interrupts(result: dict) -> list:
    """Return clarification payloads from LangGraph's __interrupt__ field."""
    prompts = []
    for item in result.get("__interrupt__", []) or []:
        value = getattr(item, "value", None)
        if isinstance(value, dict):
            prompts.append(value)
        elif value is not None:
            prompts.append({"question": str(value)})
        else:
            prompts.append({"question": "Please clarify your question."})
    return prompts