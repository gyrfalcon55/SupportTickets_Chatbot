import logging
import os

from dotenv import load_dotenv
from langchain_core.runnables import RunnableLambda
from langchain_groq import ChatGroq

load_dotenv()
logger = logging.getLogger(__name__)


async def _invoke_with_fallback(input_value, config=None, **kwargs):
    """Invoke the configured primary Groq model and then its fallback.
    Defer credential validation until invocation so imports do not crash startup.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set; configure it in the environment.")

    primary_name = os.getenv("GROQ_PRIMARY_MODEL", "qwen/qwen3.8-27b")
    fallback_name = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")
    try:
        primary = ChatGroq(model=primary_name, api_key=api_key, temperature=0)
        return await primary.ainvoke(input_value, config=config, **kwargs)
    except Exception as primary_exc:
        logger.warning("Primary LLM invocation failed; trying fallback: %s", primary_exc)
        try:
            fallback = ChatGroq(model=fallback_name, api_key=api_key, temperature=0)
            return await fallback.ainvoke(input_value, config=config, **kwargs)
        except Exception:
            logger.exception("Fallback LLM invocation failed")
            raise


# Runnable wrapper preserves prompt | large_model_with_fallback usage.
large_model_with_fallback = RunnableLambda(_invoke_with_fallback)
