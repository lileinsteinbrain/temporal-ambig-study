# app.py
import random
import time
from datetime import datetime
from urllib.parse import quote
from typing import List

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

from config import (
    FIGMA_URL_DIRECTIVE,   # Figma prototype "Play" URL
    FIGMA_URL_AMBIGUOUS,   # Figma prototype "Play" URL
    SESSION_SECONDS        # e.g. 120
)

# ------------ Always use this Google Sheet ------------
GOOGLE_SHEET_ID = "1GppaOTunJ6yt2zJeIhMWxb1xZ2glqUo6XNKK-l-z8FY"
TARGET_SHEET_TITLE = "data_v2"  # all rows go to data_v2

# ------------ Google Sheets Auth ------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds_info = st.secrets["gcp_service_account"]  # stored in Streamlit Cloud secrets
credentials = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
gc = gspread.authorize(credentials)

# ------------ Column headers (one-to-one with the data structure) ------------
HEADERS = [
    # Meta
    "participant_id", "timestamp_utc", "order", "A_condition", "B_condition",
    # Durations
    "dur_directive", "dur_ambiguous",
    # Ambiguous / Directive self-report
    "Ambiguous_size", "Directive_time", "Repeat_note",
    # A block (Q1..Q15)
    *[f"A_Q{i}" for i in range(1, 16)],
    # B block (Q1..Q15)
    *[f"B_Q{i}" for i in range(1, 16)],
    # Baseline
    "BASE_fast_days", "BASE_fragment", "BASE_control_anx",
    "mood_today", "baseline_note",
    # Demographics
    "DEMO_age", "DEMO_gender",
]

def open_target_ws():
    """
    Write only to data_v2. Create it with headers if missing; add headers if A1 is empty.
    """
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    try:
        ws = sh.worksheet(TARGET_SHEET_TITLE)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=TARGET_SHEET_TITLE, rows=5000, cols=120)

    a1 = None
    try:
        a1 = ws.acell("A1").value
    except Exception:
        pass
    if not a1:
        ws.update("A1", [HEADERS])
    return ws

WS = open_target_ws()

# Retry appends on failure (exponential backoff)
def safe_append_row(ws, row: List, *, retries: int = 5, sleep_base: float = 0.6):
    for i in range(retries):
        try:
            ws.append_row(row, value_input_option="RAW")
            return True
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(sleep_base * (2 ** i))  # 0.6s →1.2s →2.4s →...

# ------------ Page config ------------
st.set_page_config(page_title="Temporal Feel Study", page_icon="🫧", layout="centered")

# ------------ State init ------------
def init_state():
    defaults = {
        "participant_id": None,
        "consent": False,
        # flow: consent -> baseline -> choose_order -> sessionA -> formA -> break -> sessionB -> formB -> demo -> end
        "stage": "consent",
        "order": None,                 # ["A","B"] or ["B","A"]
        "start_ts": None,
        "end_ts": None,
        "current_condition": None,     # "Directive"/"Ambiguous" (timer guard)
        "durations": {},               # {"Directive": seconds, "Ambiguous": seconds}
        "responses": {"A": {}, "B": {}, "BASE": {}, "DEMO": {}},
        "elapsed_probe": None,         # small probe to avoid the timer sticking at 0 s
        # These three come from participant self-report (left empty if missing)
        "Ambiguous_size": None,        # e.g. small/mid/large, or percentage/radius
        "Directive_time": None,        # e.g. 3s/6s/10s, or seconds as a number
        "Repeat_note": None,           # e.g. repetition count / notes (optional)
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

init_state()

def gen_participant_id() -> str:
    # Human-readable: PYYMMDD-HHMMSS-rand3
    return datetime.utcnow().strftime("P%y%m%d-%H%M%S-") + f"{random.randint(100,999)}"

# ------------ Helpers ------------
def label_for(cond_tag: str) -> str:
    """Input 'A'/'B'; return a readable label (A=Ambiguous, B=Directive)."""
    return "Ambiguous" if cond_tag == "A" else "Directive"

def _figma_embed_url(proto_url: str) -> str:
    """
    Convert a Figma prototype share link into an embeddable link with the UI hidden.
    """
    encoded = quote(proto_url, safe="")
    return (
        f"https://www.figma.com/embed?embed_host=share"
        f"&url={encoded}"
        f"&hide-ui=1&hide-sidebar=1&scaling=scale-down-width"
    )

def render_figma(label: str):
    # label must be "Directive" or "Ambiguous"
    proto = FIGMA_URL_DIRECTIVE if label == "Directive" else FIGMA_URL_AMBIGUOUS
    embed = _figma_embed_url(proto)
    st.components.v1.iframe(src=embed, height=820, scrolling=False)
    st.link_button("⇱ Open prototype in a new tab", proto, use_container_width=True)

def start_timer(label: str):
    st.session_state["current_condition"] = label
    st.session_state["start_ts"] = time.time()
    st.session_state["end_ts"] = None
    st.session_state["elapsed_probe"] = time.time()

def stop_timer() -> float:
    if st.session_state["start_ts"] is None:
        return 0.0
    st.session_state["end_ts"] = time.time()
    return float(st.session_state["end_ts"] - st.session_state["start_ts"])

def likert(prompt: str):
    return st.radio(prompt, options=[1,2,3,4,5,6,7], horizontal=True)

# ------------ UI blocks ------------
def page_consent():
    st.title("Consent")
    st.markdown("""
**Study Title**
Temporal Feel in Ambiguous Interfaces

**Introduction**
You will try two short interactions (Directive and Ambiguous), about 2 minutes each, and then answer a few short questions.
This study is about how you subjectively experience the flow of time and your sense of control. There are no right or wrong answers.

**Privacy & Data**
No identifying information is collected. The timing of your actions may be recorded and used only for anonymous research analysis. You may withdraw at any time.

**Voluntary Participation**
Participation is entirely voluntary. You can stop at any time without any negative consequences.

By ticking the box below, I confirm that I understand the above and agree to take part in this study.
""")
    agree = st.checkbox("I have read and agree. I consent.", value=False)
    if st.button("Continue", use_container_width=True):
        if not agree:
            st.warning("Please tick the consent box first.")
        else:
            # Generate participant ID
            if not st.session_state["participant_id"]:
                st.session_state["participant_id"] = gen_participant_id()
            st.session_state["consent"] = True
            st.session_state["stage"]   = "baseline"
            st.rerun()

def page_baseline():
    st.subheader("Past week & today (baseline)")
    b = {}
    st.markdown("**Past week (1 = strongly disagree, 7 = strongly agree)**")
    b["BASE_fast_days"]   = likert("I often feel that days pass very quickly")
    b["BASE_fragment"]    = likert("I often forget what happened on which day")
    b["BASE_control_anx"] = likert("I am easily troubled by feeling controlled by time or by procrastination")

    st.markdown("**Today**")
    b["mood_today"] = st.slider("How is your overall mood today?", 0, 10, 6)
    b["baseline_note"] = st.text_area("One sentence about your sense of time right now (optional)", height=60)

    if st.button("Continue", type="primary", use_container_width=True):
        st.session_state["responses"]["BASE"] = b
        st.session_state["stage"] = "choose_order"
        st.rerun()

def page_choose_order():
    st.subheader("Choose the order (or random)")
    choice = st.radio("Which one first?", ["Directive → Ambiguous", "Ambiguous → Directive", "Random"], index=2)
    if st.button("Start", use_container_width=True):
        if choice == "Random":
            order = ["A","B"] if int(time.time()) % 2 == 0 else ["B","A"]
        else:
            order_labels = ["Directive","Ambiguous"] if choice.startswith("Directive") else ["Ambiguous","Directive"]
            order = ["A","B"] if order_labels[0] == "Ambiguous" else ["B","A"]
        st.session_state["order"] = order
        st.session_state["stage"] = "sessionA"
        st.rerun()

def questionnaire_ui(tag: str):
    q = {}
    st.markdown("### Section 2 — Structured / Directive Layer (1–7)")
    q["Q1"] = likert("I could clearly feel time passing")
    q["Q2"] = likert("I felt in control of the pace of the interaction")
    q["Q3"] = likert("The system mostly responded as I expected")
    q["Q4"] = likert("Time during this session felt faster or slower than real time")
    q["Q5"] = likert("I was in sync with the system's rhythm")
    q["Q6"] = likert("I would like to stay with it a little longer")
    q["Q7"] = likert("This experience made me feel calmer")

    st.markdown("### Section 3 — Phenomenological Imagery Probe")
    q["Q8"]  = st.selectbox("If this experience had a texture, it would be closest to:", ["Flowing water","Thick fog","Pulsing light","Still air","Other"], index=0)
    q["Q9"]  = st.selectbox("Time in this experience felt more like:", ["A straight line","A circle","A loop","A blank / vacuum","Other"], index=0)
    q["Q10"] = st.selectbox("When the interface responded to you, you felt more like you were:", ["Guiding it","Being carried along by it","Moving together with it","Nobody was in control"], index=1)
    q["Q11"] = st.text_input("Describe the atmosphere of this experience in one word:", value="")

    st.markdown("### Section 4 — Reflective / Meta Layer")
    q["Q12"] = st.text_area("Did your sense of time change during the experience you just had?", height=80)
    q["Q13"] = st.selectbox("When the interface did not respond as you expected, your first reaction was:",
                            ["Relaxed","Curious","Uneasy","Nothing in particular"], index=1)
    q["Q14"] = st.text_area("Did this experience give you any new thoughts about control or pace?", height=80)
    q["Q15"] = st.text_area("How would you describe this experience to a friend?", height=80)

    st.session_state["responses"][tag] = q

def page_session(tag: str, label: str):
    st.subheader(f"Session {tag} — {label}")
    st.caption("Suggested duration is about 2 minutes. Timing starts automatically when you press Start.")

    # Condition-switch guard: reset the timer if the condition changed
    if st.session_state["current_condition"] not in (None, label):
        st.session_state["start_ts"] = None
        st.session_state["end_ts"] = None

    if st.session_state["start_ts"] is None:
        if st.button("▶️ Start", type="primary"):
            start_timer(label)
            st.rerun()
        return

    elapsed = int(time.time() - st.session_state["start_ts"])

    # Some browsers' focus handling can freeze the timer at 0 s: soft-refresh once if still 0 after 2 s
    if elapsed <= 0 and st.session_state.get("elapsed_probe"):
        if time.time() - st.session_state["elapsed_probe"] > 2:
            st.rerun()

    remaining = max(0, SESSION_SECONDS - elapsed)
    st.info(f"Elapsed {elapsed}s · suggested at least {SESSION_SECONDS}s · {remaining}s remaining")

    render_figma(label)
    st.write("")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⏹ Stop & go to questionnaire", use_container_width=True):
            dur = stop_timer()
            st.session_state["durations"][label] = round(dur, 2)
            st.session_state["stage"] = "formA" if tag == "A" else "formB"
            st.rerun()
    with col2:
        if elapsed < SESSION_SECONDS:
            st.caption("⏳ Please try to continue until the suggested duration before stopping.")

def page_form(tag: str, cond_tag: str):
    label = label_for(cond_tag)  # "Ambiguous"/"Directive"
    st.subheader(f"Questionnaire {tag} — {label}")
    st.caption("Please answer based on the session you just completed.")
    questionnaire_ui(tag)
    if st.button("Submit questionnaire", type="primary"):
        st.success("✅ Responses saved.")
        st.session_state["stage"] = "break" if tag == "A" else "demo"
        st.rerun()

def page_break():
    st.info("Take a 1-minute break before the next session (have some water, stretch). Click Continue when ready.")
    if st.button("Continue to Session B", use_container_width=True):
        st.session_state["stage"] = "sessionB"
        st.rerun()

def page_demo():
    st.subheader("Demographics (brief)")
    d = {}
    d["age"]    = st.selectbox("Age group", ["18–24","25–34","35–44","45–54","55+"], index=1)
    d["gender"] = st.selectbox("Gender (optional)", ["Prefer not to say","Female","Male","Non-binary / other"], index=0)
    st.session_state["responses"]["DEMO"] = d

    # 🔧 Debug: write one test row to check permissions / connection
    if st.button("🔧 Test write to Sheet (debug)"):
        try:
            now_iso = datetime.utcnow().isoformat()
            # Pad to the length of HEADERS
            test_row = ["DBG", now_iso] + [""] * (len(HEADERS) - 2)
            safe_append_row(WS, test_row)
            st.success("✅ Test row written (refresh the sheet to check)")
        except Exception as e:
            st.error(f"❌ Test write failed: {e}")

    if st.button("Submit all & Save", type="primary"):
        # Fallback: if the timer is still running but the participant submits, record the elapsed time so far
        for _lbl in ("Directive", "Ambiguous"):
            if _lbl not in st.session_state["durations"] and st.session_state.get("start_ts"):
                st.session_state["durations"][_lbl] = round(time.time() - st.session_state["start_ts"], 2)

        now_iso = datetime.utcnow().isoformat()
        order = st.session_state["order"] or ["A","B"]
        a_label = label_for(order[0])   # condition label for each session
        b_label = label_for(order[1])
        durs = st.session_state["durations"]

        # Self-report fields: left empty if not filled in the UI
        amb_size = st.session_state.get("Ambiguous_size", "") or ""
        dir_time = st.session_state.get("Directive_time", "") or ""
        repeat_note = st.session_state.get("Repeat_note", "") or ""

        # Build one row (strictly in HEADERS order)
        row = [
            st.session_state.get("participant_id", ""),   # participant_id
            now_iso,
            "→".join(order),
            a_label, b_label,
            durs.get("Directive", None),
            durs.get("Ambiguous", None),
            amb_size, dir_time, repeat_note,
        ]
        # A responses
        for i in range(1, 16):
            row.append(st.session_state["responses"]["A"].get(f"Q{i}", ""))
        # B responses
        for i in range(1, 16):
            row.append(st.session_state["responses"]["B"].get(f"Q{i}", ""))

        # Baseline
        base = st.session_state["responses"]["BASE"]
        row.extend([
            base.get("BASE_fast_days", ""),
            base.get("BASE_fragment", ""),
            base.get("BASE_control_anx", ""),
            base.get("mood_today", ""),
            base.get("baseline_note", "")
        ])

        # Demographics
        demo = st.session_state["responses"]["DEMO"]
        row.extend([demo.get("age", ""), demo.get("gender", "")])

        try:
            safe_append_row(WS, row)
            st.success("✅ All data saved to Google Sheet.")
            st.session_state["stage"] = "end"
            st.rerun()
        except Exception as e:
            st.error(f"❌ Failed to write to Google Sheet: {e}")

def page_end():
    st.success("All done, thank you for taking part! You can close this page.")
    st.caption("Researcher note: data is in the data_v2 tab at the bottom of the Google Sheet.")

# ------------ Dispatcher ------------
def dispatch():
    if not st.session_state.get("consent", False):
        page_consent(); return

    stage = st.session_state.get("stage", "baseline")

    if stage == "baseline":
        page_baseline(); return

    if stage == "choose_order":
        page_choose_order(); return

    if "order" not in st.session_state or not st.session_state["order"]:
        st.session_state["order"] = random.sample(["A", "B"], 2)

    if stage == "sessionA":
        cond = st.session_state["order"][0]
        label = label_for(cond)
        page_session("A", label); return

    if stage == "formA":
        cond = st.session_state["order"][0]
        page_form("A", cond); return

    if stage == "break":
        page_break(); return

    if stage == "sessionB":
        cond = st.session_state["order"][1]
        label = label_for(cond)
        page_session("B", label); return

    if stage == "formB":
        cond = st.session_state["order"][1]
        page_form("B", cond); return

    if stage == "demo":
        page_demo(); return

    page_end()

# ------------ Run ------------
dispatch()
