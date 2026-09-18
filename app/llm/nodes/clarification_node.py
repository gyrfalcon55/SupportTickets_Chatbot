import asyncio
import logging
import re
from datetime import date, timedelta
from langchain_core.messages import AIMessage
from langgraph.types import interrupt
from app.llm.state import MessageState, latest_user_message
from app.llm.nodes.executor_node import get_dataset_date_range
import calendar

logger = logging.getLogger(__name__)


def _period_phrase(question: str) -> str | None:
    """Detect whether a question refers to the current calendar month or week.
    Return the matching period label, or None when no clarification check applies.
    """
    q = question.lower()
    if "this month" in q or "current month" in q:
        return "month"
    if "this week" in q or "current week" in q:
        return "week"
    return None


async def check_clarification(state: MessageState) -> MessageState:
    """Check whether a requested current period overlaps the dataset dates.
    Return clarification metadata or allow the SQL workflow to continue.
    """
    question = latest_user_message(state.get("messages", []))
    period = _period_phrase(question)
    if not period:
        return {"needs_clarification": False}

    try:
        date_range = await asyncio.to_thread(get_dataset_date_range)
    except Exception:
        logger.exception("Could not retrieve dataset date range")
        return {"needs_clarification": False, "error": "Could not inspect dataset date coverage."}
    start, end = date_range.get("min_date"), date_range.get("max_date")
    today = date.today().isoformat()
    if not start or not end:
        return {
            "needs_clarification": True,
            "clarification_kind": "dataset_empty",
            "clarification_question": "The ticket table has no valid created_at dates. What date range should I use, or would you like to inspect the dataset first?",
        }

    # Ask if the requested calendar period is outside the dataset's coverage.
    if period == "month":
        current_start = today[:7] + "-01"
        current_end = (date.today().replace(day=28) + timedelta(days=4)).replace(day=1).isoformat()
        outside = end < current_start or start >= current_end
        label = "current month"
    else:
        monday = date.today() - timedelta(days=date.today().weekday())
        next_monday = monday + timedelta(days=7)
        outside = end < monday.isoformat() or start >= next_monday.isoformat()
        label = "current week"

    if outside:
        prompt = (
            f"Your dataset covers {start} through {end}, which does not overlap the {label}. "
            "Would you like me to analyze the latest available matching period, specify a date range, or use the actual current period?"
        )
        return {
            "needs_clarification": True,
            "clarification_kind": period,
            "clarification_question": prompt,
            "date_range": {"start": start, "end": end},
        }
    return {"needs_clarification": False, "date_range": {"start": start, "end": end}}



def _resolve_clarified_period(answer: str, kind: str, dataset_range: dict):
    """Parse natural-language or numeric date ranges into inclusive ISO dates.
    Infer omitted years from dataset coverage and reject invalid/reversed ranges.
    """
    text = answer.strip().casefold().replace("–", "-").replace("—", "-")
    start_ds, end_ds = dataset_range.get("min_date"), dataset_range.get("max_date")
    if not start_ds or not end_ds:
        return None

    if any(x in text for x in ("latest", "latest available", "available period")):
        end_date = date.fromisoformat(end_ds)
        if kind == "month":
            first = end_date.replace(day=1)
            next_first = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
            return {"start": first.isoformat(), "end": (next_first - timedelta(days=1)).isoformat()}
        monday = end_date - timedelta(days=end_date.weekday())
        return {"start": monday.isoformat(), "end": (monday + timedelta(days=6)).isoformat()}

    if any(x in text for x in ("actual current", "current period", "use now")):
        today = date.today()
        if kind == "month":
            first = today.replace(day=1)
            next_first = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
            return {"start": first.isoformat(), "end": (next_first - timedelta(days=1)).isoformat()}
        monday = today - timedelta(days=today.weekday())
        return {"start": monday.isoformat(), "end": (monday + timedelta(days=6)).isoformat()}

    # Numeric formats: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, and slash variants.
    iso_dates = re.findall(r'\b\d{4}-\d{1,2}-\d{1,2}\b', text)
    if len(iso_dates) >= 2:
        a, b = (date.fromisoformat(x) for x in iso_dates[:2])
    else:
        numeric = re.findall(r'\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b', text)
        if len(numeric) >= 2:
            a, b = (date(int(y), int(m), int(d)) for d, m, y in numeric[:2])
        else:
            months = {name.casefold(): i for i, name in enumerate(calendar.month_name) if name}
            months.update({name.casefold(): i for i, name in enumerate(calendar.month_abbr) if name})
            month_match = next(((re.search(r'\b' + re.escape(name) + r'\b', text), num)
                                for name, num in sorted(months.items(), key=lambda x: -len(x[0]))
                                if re.search(r'\b' + re.escape(name) + r'\b', text)), None)
            if month_match:
                match, month_num = month_match
                tail = text[match.end():]
                nums = re.findall(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', tail)
                if not nums:
                    if kind == "month":
                        year_match = re.search(r'\b(20\d{2})\b', text)
                        year = int(year_match.group(1)) if year_match else date.fromisoformat(end_ds).year
                        first = date(year, month_num, 1)
                        return {"start": first.isoformat(), "end": date(year, month_num, calendar.monthrange(year, month_num)[1]).isoformat()}
                    return None
                year_match = re.search(r'\b(20\d{2})\b', text)
                year = int(year_match.group(1)) if year_match else date.fromisoformat(end_ds).year
                first_day = int(nums[0])
                second_day = int(nums[1]) if len(nums) > 1 else first_day
                # If two different month names are present, parse each endpoint separately.
                month_matches = [(m.start(), num, m) for name, num in months.items()
                                 for m in [re.search(r'\b' + re.escape(name) + r'\b', text)] if m]
                month_matches.sort(key=lambda x: x[0])
                if len(month_matches) >= 2:
                    m1, m2 = month_matches[0][1], month_matches[1][1]
                    day_nums = re.findall(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', text)
                    if len(day_nums) >= 2:
                        first_day, second_day = int(day_nums[0]), int(day_nums[1])
                    a, b = date(year, m1, first_day), date(year, m2, second_day)
                else:
                    a, b = date(year, month_num, first_day), date(year, month_num, second_day)
            else:
                return None

    if b < a:
        return None
    if a < date.fromisoformat(start_ds) or b > date.fromisoformat(end_ds):
        # Explicit dates outside coverage are preserved for transparent empty results.
        pass
    return {"start": a.isoformat(), "end": b.isoformat()}


async def ask_clarification(state: MessageState) -> MessageState:
    """Pause the graph for a date clarification and resolve the user's answer.
    Return the resolved range or an error that routes directly to output formatting.
    """
    question = state.get("clarification_question", "Please clarify the date range.")
    answer = interrupt({"type": "clarification", "question": question})
    answer = str(answer).strip()
    if not answer:
        return {"needs_clarification": False, "error": "Clarification answer was empty."}

    kind = state.get("clarification_kind", "")
    dataset_range = await __import__("asyncio").to_thread(get_dataset_date_range)
    resolved = _resolve_clarified_period(answer, kind, dataset_range)

    if resolved:
        return {
            "clarification_answer": answer,
            "date_range": resolved,
            "needs_clarification": False,
            "clarification_question": "",
        }

    return {
        "clarification_answer": answer,
        "needs_clarification": False,
        "clarification_question": "",
        "error": (
            f"Could not interpret '{answer}' as a {kind} or date range. "
            "Please specify a month (e.g. March), a full date range, "
            "'latest available period', or 'actual current period'."
        ),
    }
