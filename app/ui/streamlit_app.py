"""Streamlit chat UI for the Support Ticket Analytics API."""
import os
import uuid
import requests
import streamlit as st

st.set_page_config(page_title="Support Ticket Analytics", page_icon="🎫", layout="wide")

DEFAULT_API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
if "api_base" not in st.session_state:
    st.session_state.api_base = DEFAULT_API
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "awaiting_clarification" not in st.session_state:
    st.session_state.awaiting_clarification = False
if "clarification_prompt" not in st.session_state:
    st.session_state.clarification_prompt = ""

with st.sidebar:
    st.header("Settings")
    st.session_state.api_base = st.text_input(
        "FastAPI base URL", value=st.session_state.api_base
    ).strip().rstrip("/")
    st.caption("Default: http://127.0.0.1:8000")
    if st.button("New conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.awaiting_clarification = False
        st.session_state.clarification_prompt = ""
        st.rerun()
    st.divider()
    st.caption("Conversation ID")
    st.code(st.session_state.thread_id)

st.title("🎫 Support Ticket Analytics")
st.caption("Ask questions about tickets, investigate anomalies, and continue clarification in the same conversation.")

tab_chat, tab_anomaly, tab_health = st.tabs(["Chat", "Anomaly detection", "API health"])

def api_error(response):
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    st.error(f"API error ({response.status_code}): {detail}")

def show_response(data):
    """Store/render only human-readable text, not the raw response JSON."""
    status = data.get("status")
    if status == "needs_clarification":
        clarifications = data.get("clarification") or []
        prompt = "\n\n".join(
            str(item.get("question", "Please clarify.")) if isinstance(item, dict)
            else str(item) for item in clarifications
        ) or "Please clarify your question."
        st.session_state.awaiting_clarification = True
        st.session_state.clarification_prompt = prompt
        st.session_state.messages.append({"role": "assistant", "content": prompt})
    elif status == "completed":
        answer = data.get("answer", "The API completed without returning an answer.")
        if not isinstance(answer, str):
            answer = str(answer)
        st.session_state.awaiting_clarification = False
        st.session_state.clarification_prompt = ""
        st.session_state.messages.append({"role": "assistant", "content": answer})
    else:
        st.session_state.messages.append({
            "role": "assistant",
            "content": data.get("answer") or data.get("message") or "Unexpected API response."
        })

with tab_chat:
    # Render persisted conversation on every Streamlit rerun.
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if st.session_state.awaiting_clarification:
        st.info("Clarification needed — your next message will resume this workflow.")
    placeholder = "Type your answer to the clarification..." if st.session_state.awaiting_clarification else "Ask about ticket counts, agents, response times, or anomalies..."
    user_text = st.chat_input(placeholder)
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)
        try:
            with st.chat_message("assistant"):
                with st.spinner("Working..."):
                    if st.session_state.awaiting_clarification:
                        response = requests.post(
                            f"{st.session_state.api_base}/query/resume",
                            json={"answer": user_text, "thread_id": st.session_state.thread_id},
                            timeout=180,
                        )
                    else:
                        response = requests.post(
                            f"{st.session_state.api_base}/query",
                            json={"question": user_text, "thread_id": st.session_state.thread_id},
                            timeout=180,
                        )
                if response.ok:
                    data = response.json()
                    returned_thread = data.get("thread_id")
                    if returned_thread:
                        st.session_state.thread_id = returned_thread
                    # Show a readable response and retain it across reruns.
                    status = data.get("status")
                    if status == "needs_clarification":
                        prompt_items = data.get("clarification") or []
                        text = "\n\n".join(
                            str(item.get("question", "Please clarify.")) if isinstance(item, dict) else str(item)
                            for item in prompt_items
                        ) or "Please clarify your question."
                        st.markdown(text)
                        st.session_state.awaiting_clarification = True
                        st.session_state.clarification_prompt = text
                        st.session_state.messages.append({"role": "assistant", "content": text})
                    elif status == "completed":
                        answer = data.get("answer", "Completed, but no answer was returned.")
                        if not isinstance(answer, str):
                            answer = str(answer)
                        st.markdown(answer)
                        st.session_state.awaiting_clarification = False
                        st.session_state.clarification_prompt = ""
                        st.session_state.messages.append({"role": "assistant", "content": answer})
                    else:
                        st.error(f"Unexpected response status: {status}")
                        st.code(str(data))
            if not response.ok:
                api_error(response)
        except requests.RequestException as exc:
            st.error(f"Could not reach FastAPI: {exc}")

with tab_anomaly:
    st.subheader("Deterministic anomaly detection")
    st.caption("Uses the API's Python/statistical endpoint; no LLM call is required.")
    st.caption("Choose a date range for ticket creation. Leave the start date empty to analyze cumulatively from the dataset start.")
    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("Start date (inclusive)", value=None, key="anomaly_start_date")
    with col2:
        end_date = st.date_input("End date (inclusive)", value=None, key="anomaly_end_date")
    with col3:
        threshold = st.number_input("Overdue threshold (hours)", min_value=0.1, value=24.0, step=1.0)
    if start_date and end_date and start_date > end_date:
        st.error("Start date must be on or before end date.")
    if st.button("Detect anomalies", type="primary", disabled=bool(start_date and end_date and start_date > end_date)):
        params = {"overdue_hours": threshold}
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
            params["as_of"] = end_date.isoformat()
        try:
            with st.spinner("Analyzing..."):
                response = requests.get(f"{st.session_state.api_base}/anomalies", params=params, timeout=90)
            if response.ok:
                data = response.json()
                counts = data.get("counts", {})
                c1, c2 = st.columns(2)
                c1.metric("Resolution-time outliers", counts.get("resolution_time_outliers", 0))
                c2.metric("Overdue high-priority unresolved", counts.get("overdue_unresolved_high_priority", 0))
                st.markdown("#### Resolution-time IQR")
                st.json(data.get("resolution_time_iqr", {}))
                st.markdown("#### Resolution-time outlier records")
                outliers = data.get("resolution_time_outliers", [])
                if outliers:
                    st.dataframe(outliers, use_container_width=True)
                else:
                    st.success("No resolution-time outliers returned.")
                st.markdown("#### Overdue unresolved high-priority tickets")
                overdue = data.get("overdue_unresolved_high_priority", [])
                if overdue:
                    st.dataframe(overdue, use_container_width=True)
                else:
                    st.success("No overdue unresolved high-priority tickets returned.")
            else:
                api_error(response)
        except requests.RequestException as exc:
            st.error(f"Could not reach FastAPI: {exc}")

with tab_health:
    if st.button("Check API and database"):
        try:
            response = requests.get(f"{st.session_state.api_base}/health", timeout=15)
            if response.ok:
                data = response.json()
                if data.get("status") == "ok":
                    st.success(f"API: {data.get('status')} · Database: {data.get('database')}")
                else:
                    st.warning(str(data))
                with st.expander("Health response"):
                    st.json(data)
            else:
                api_error(response)
        except requests.RequestException as exc:
            st.error(f"Could not reach FastAPI: {exc}")
