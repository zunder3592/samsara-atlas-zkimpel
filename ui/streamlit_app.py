import json
import requests
import streamlit as st

API_BASE = "http://localhost:8000"


def run_workflow(employee_id: str, case_transcript: str, tone: str, idempotency_key: str | None = None):
    resp = requests.post(
        f"{API_BASE}/cases",
        json={
            "inputs": {
                "employee_id": employee_id,
                "case_transcript": case_transcript,
                "tone": tone,
            },
            "idempotency_key": idempotency_key,
        },
        timeout=120,
    )
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        err = requests.exceptions.HTTPError(f"{resp.status_code}: {detail}", response=resp)
        raise err
    return resp.json()


def get_case(case_id: int):
    resp = requests.get(f"{API_BASE}/cases/{case_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def replay_case(case_id: int):
    resp = requests.post(f"{API_BASE}/cases/{case_id}/replay", timeout=120)
    resp.raise_for_status()
    return resp.json()


def list_cases():
    resp = requests.get(f"{API_BASE}/cases", timeout=10)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json()


st.set_page_config(page_title="Samsara Atlas", page_icon="🧭", layout="wide")
st.title("🧭 Samsara Atlas")
st.caption("HR Case Response Assistant")

with st.sidebar:
    try:
        info = requests.get(f"{API_BASE}/info", timeout=2).json()
        provider = info.get("provider", "?")
        st.success(f"**Provider:** {provider}")
    except Exception:
        st.warning("API not reachable")
    st.info(
        "**Real LLM:** Create `.env` with `PROVIDER_TYPE=ollama` and restart the API.\n\n"
        "Or run `make api-ollama`. Requires [Ollama](https://ollama.ai) + `ollama pull llama3.2`"
    )
    st.caption("All employee data shown here is synthetic fixture data.")

with st.form("workflow_form"):
    col1, col2 = st.columns(2)
    with col1:
        try:
            employees_resp = requests.get(f"{API_BASE}/employees", timeout=2)
            employees = employees_resp.json().get("employees", []) if employees_resp.ok else []
        except Exception:
            employees = []
        if not employees:
            employees = ["E10234", "E10897", "E11342"]
        employee_id = st.selectbox("Employee ID", options=employees, index=0)
        tone = st.selectbox("Tone", ["empathetic", "direct", "formal"])
    with col2:
        case_transcript = st.text_area(
            "Case Description",
            value="Asked how PTO carryover works going into next year. Has about 30 unused hours.",
            height=100,
        )
    idempotency_key = st.text_input("Idempotency Key (optional)", value="")
    submitted = st.form_submit_button("Run Workflow")

if submitted:
    with st.spinner("Running workflow..."):
        try:
            result = run_workflow(
                employee_id=employee_id,
                case_transcript=case_transcript,
                tone=tone,
                idempotency_key=idempotency_key or None,
            )
            st.session_state["last_case_id"] = result["case_id"]
            #if else to display true status instead of just completed 
            status = result.get("status")
            if status == "completed":
                st.success(f"Case completed: {result['case_id']}")
                st.session_state["case_result"] = result
            elif status == "running":
                st.session_state.pop("case_result", None)
                st.warning(
                    f"Case {result['case_id']} is still running (or was started by an earlier "
                    "request with this key). No new draft was produced. Check it in Case Explorer."
                )
            else:
                st.session_state.pop("case_result", None)
                st.error(f"Case {result['case_id']} ended with status '{status}': {result.get('error')}")
        except requests.exceptions.RequestException as e:
            st.error(f"Error: {e}")

if "case_result" in st.session_state:
    st.subheader("Drafted Response")
    outputs = st.session_state["case_result"].get("outputs", {})
    st.write(f"**Subject:** {outputs.get('subject', '')}")
    st.write(outputs.get("body", ""))
    if outputs.get("cited_snippets"):
        with st.expander("Cited policy snippets"):
            for s in outputs["cited_snippets"]:
                st.write(f"- {s}")

st.divider()
st.subheader("Case Explorer")

case_id_input = st.number_input("Case ID", min_value=1, step=1, value=st.session_state.get("last_case_id", 1))
col_a, col_b = st.columns(2)
with col_a:
    if st.button("Load Case"):
        try:
            st.session_state["loaded_case"] = get_case(int(case_id_input))
        except requests.exceptions.RequestException as e:
            st.error(f"Error: {e}")
with col_b:
    if st.button("Replay Case"):
        try:
            replay_result = replay_case(int(case_id_input))
            st.info(f"Replay created case {replay_result['case_id']}")
        except requests.exceptions.RequestException as e:
            st.error(f"Error: {e}")

if "loaded_case" in st.session_state:
    data = st.session_state["loaded_case"]
    st.json(data["case"])
    st.write("**Steps**")
    st.table(data["steps"])
    st.write("**Case Notes**")
    st.table(data["case_notes"])

st.divider()
st.caption(f"All cases: {list_cases().get('case_ids', [])}")
