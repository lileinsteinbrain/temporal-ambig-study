import random
import time
from datetime import datetime
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

from config import (
    FIGMA_URL_DIRECTIVE, FIGMA_URL_AMBIGUOUS,
    SESSION_SECONDS, GOOGLE_SHEET_NAME
)

# ----------------- Google Sheets -----------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
creds_info = st.secrets["gcp_service_account"]
credentials = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
gc = gspread.authorize(credentials)

def get_or_create_sheet(sheet_name: str):
    try:
        sh = gc.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        sh = gc.create(sheet_name)
    try:
        ws = sh.worksheet("data")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="data", rows=1000, cols=50)
        ws.append_row([
            "timestamp_utc","order","dur_directive","dur_ambiguous",
            *[f"A_Q{i}" for i in range(1,16)],
            *[f"B_Q{i}" for i in range(1,16)],
            "DEMO_age","DEMO_gender","DEMO_BASE_fast_days","DEMO_BASE_fragment",
            "DEMO_BASE_control_anx","DEMO_mood_today","DEMO_baseline_note"
        ])
    return sh, ws

sh, ws = get_or_create_sheet(GOOGLE_SHEET_NAME)

# ----------------- Page config -----------------
st.set_page_config(page_title="Temporal Feel Study", page_icon="🫧", layout="centered")

# ----------------- State init -----------------
def init_state():
    defaults = {
        "consent": False,
        "stage": "consent",          # consent -> choose_order -> sessionA -> formA -> break -> sessionB -> formB -> demo -> end
        "order": None,               # ["A","B"] 或 ["B","A"]
        "start_ts": None,
        "end_ts": None,
        "durations": {},             # {"Directive": seconds, "Ambiguous": seconds}
        "responses": {"A": {}, "B": {}, "DEMO": {}},
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)
init_state()

# ----------------- Helpers -----------------
def label_for(cond: str) -> str:
    # A/B -> 人可读标签（如需互换只改这里）
    return "Ambiguous" if cond == "A" else "Directive"

def render_figma(label: str):
    # label 需要是 "Directive" 或 "Ambiguous"
    url = FIGMA_URL_DIRECTIVE if label == "Directive" else FIGMA_URL_AMBIGUOUS
    st.components.v1.iframe(src=url, height=620, scrolling=True)

def start_timer():
    st.session_state["start_ts"] = time.time()
    st.session_state["end_ts"] = None

def stop_timer() -> float:
    if st.session_state["start_ts"] is None:
        return 0.0
    st.session_state["end_ts"] = time.time()
    return st.session_state["end_ts"] - st.session_state["start_ts"]

def likert(label): 
    return st.radio(label, options=[1,2,3,4,5,6,7], horizontal=True)

# ----------------- UI blocks -----------------
def page_consent():
    st.title("实验参与同意 / Consent")
    st.markdown("""
**研究名称 / Study Title**  
时间感知与模糊交互（Temporal Feel in Ambiguous Interfaces）

**研究简介 / Introduction**  
你将体验两种短交互（Directive vs Ambiguous），每种约 2 分钟，随后回答简短问题。  
本研究关注你对“时间流动与掌控感”的主观感受，不存在对错。

**隐私与数据 / Privacy & Data**  
不收集身份信息；可能记录你的操作时序，仅用于匿名研究分析；可随时退出。

**自愿参与 / Voluntary**  
完全自愿，随时退出，无任何负面影响。

勾选后表示：我已理解以上内容，并自愿参与本研究。
""")
    agree = st.checkbox("我已阅读并同意 / I consent.", value=False)
    if st.button("继续 / Continue"):
        if not agree:
            st.warning("请先勾选同意")
        else:
            st.session_state["consent"] = True
            st.session_state["stage"]   = "choose_order"
            st.rerun()

def page_choose_order():
    st.subheader("选择体验顺序（或随机）")
    order_sel = st.radio("先体验哪一个？", ["A → B", "B → A", "随机 / Random"], index=2)
    if st.button("开始 / Start"):
        if order_sel == "随机 / Random":
            order = ["A","B"] if int(time.time()) % 2 == 0 else ["B","A"]
        else:
            order = ["A","B"] if order_sel.startswith("A") else ["B","A"]
        st.session_state["order"] = order
        st.session_state["stage"] = "sessionA"
        st.rerun()

def questionnaire_ui(tag: str):
    st.markdown("### Section 2 — Structured / Directive Layer (1–7)")
    q = {}
    q["Q1"] = likert("我能清晰地感到时间在流动（Temporal awareness）")
    q["Q2"] = likert("我觉得自己能掌控互动的节奏（Sense of control）")
    q["Q3"] = likert("系统的反应大多在我的预期之内（Predictability）")
    q["Q4"] = likert("我感觉这段时间的快慢与现实不同（Subjective time speed）")
    q["Q5"] = likert("我与系统的节奏是同步的（Synchrony）")
    q["Q6"] = likert("我愿意继续与它多待一会儿（Desire to continue）")
    q["Q7"] = likert("这段体验让我情绪更平稳（Calmness）")

    st.markdown("### Section 3 — Phenomenological Imagery Probe")
    q["Q8"]  = st.selectbox("如果这段体验有一种质地，它更像：", ["流动的水","厚重的雾","脉动的光","静止的空气","其他"], index=0)
    q["Q9"]  = st.selectbox("这段体验中的时间更像：", ["一条直线","一个圆","循环","空白/真空","其他"], index=0)
    q["Q10"] = st.selectbox("当界面回应你时，你更像是在：", ["引导它","被它带着走","和它一起移动","谁也没在控制"], index=1)
    q["Q11"] = st.text_input("用一个词形容这段体验的氛围：", value="")

    st.markdown("### Section 4 — Reflective / Meta Layer")
    q["Q12"] = st.text_area("在刚才的体验中，你对时间的感觉有变化吗？（如变慢、变快、变模糊、变得不重要等）", height=80)
    q["Q13"] = st.selectbox("当界面的反应不是你的预期时，你的第一反应是：",
                            ["放松（不用急）","好奇（想看看会怎样）","不安（不确定该做什么）","没什么特别感觉"], index=1)
    q["Q14"] = st.text_area("这次体验让你对“掌控/节奏”有新的想法吗？", height=80)
    q["Q15"] = st.text_area("如果要和朋友形容这次体验，你会怎么说？", height=80)

    st.session_state["responses"][tag] = q

def page_session(tag: str, label: str):
    """
    tag: "A" or "B"
    label: "Ambiguous" or "Directive"（用于渲染 figma 与时长记账的 key）
    """
    st.subheader(f"Session {tag} — {label}")
    st.caption("建议体验约 2 分钟。点击开始后计时自动记录。")

    # 开始计时
    if st.session_state["start_ts"] is None:
        if st.button("▶️ Start"):
            start_timer()
            st.rerun()
        return

    # 已经在计时
    elapsed = int(time.time() - st.session_state["start_ts"])
    remaining = max(0, SESSION_SECONDS - elapsed)
    st.info(f"已用时 {elapsed}s · 建议至少 {SESSION_SECONDS}s · 剩余 {remaining}s")

    render_figma(label)
    st.write("")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⏹ Stop & go to questionnaire"):
            dur = stop_timer()
            st.session_state["durations"][label] = round(dur, 2)
            st.session_state["stage"] = "formA" if tag == "A" else "formB"
            st.rerun()
    with col2:
        if elapsed < SESSION_SECONDS:
            st.caption("⏳ 建议至少体验到推荐时长后再停止。")

def page_form(tag: str, cond_tag: str):
    """cond_tag 是 'A' 或 'B'，用来取回本轮是哪种并回写问卷到 responses[tag]"""
    label = label_for(cond_tag)  # 转成人可读标签，仅需展示时使用
    st.subheader(f"Questionnaire {tag} — {label}")
    questionnaire_ui(tag)
    if st.button("Submit questionnaire"):
        st.success("✅ Responses saved in session.")
        st.session_state["stage"] = "break" if tag == "A" else "demo"
        st.rerun()

def page_break():
    st.info("休息 1 分钟后进行下一段体验（喝口水、伸展一下）。准备好后点击继续。")
    if st.button("Continue to Session B"):
        st.session_state["stage"] = "sessionB"
        st.rerun()

def page_demo():
    st.subheader("Demographics & Recent Temporal Baseline")
    d = {}
    d["age"]   = st.selectbox("年龄段", ["18–24","25–34","35–44","45–54","55+"], index=1)
    d["gender"] = st.selectbox("性别（可选）", ["不透露","女性","男性","非二元/其他"], index=0)

    st.markdown("**最近一周的主观时间状态（1=非常不同意，7=非常同意）**")
    d["BASE_fast_days"]   = likert("我常觉得一天过得很快（时间加速感）")
    d["BASE_fragment"]    = likert("我常忘记具体哪天发生了什么（时间断裂感）")
    d["BASE_control_anx"] = likert("我容易被“时间控制/拖延感”困扰（时间焦虑）")

    st.markdown("**今日状态**")
    d["mood_today"]   = st.slider("你今天整体情绪如何？", 0, 10, 6)
    d["baseline_note"] = st.text_area("此刻关于你自己的“时间感”的一句话（可选）", height=60)

    st.session_state["responses"]["DEMO"] = d

    if st.button("Submit all & Save"):
        # 汇总一行数据
        now_iso = datetime.utcnow().isoformat()
        order = st.session_state["order"] or ["A","B"]
        durs  = st.session_state["durations"]
        row = [
            now_iso,
            "→".join(order),
            durs.get("Directive", None),
            durs.get("Ambiguous", None),
        ]
        for i in range(1,16):
            row.append(st.session_state["responses"]["A"].get(f"Q{i}", ""))
        for i in range(1,16):
            row.append(st.session_state["responses"]["B"].get(f"Q{i}", ""))

        demo = st.session_state["responses"]["DEMO"]
        row.extend([
            demo.get("age",""), demo.get("gender",""),
            demo.get("BASE_fast_days",""), demo.get("BASE_fragment",""),
            demo.get("BASE_control_anx",""), demo.get("mood_today",""),
            demo.get("baseline_note","")
        ])

        sh, ws = get_or_create_sheet(GOOGLE_SHEET_NAME)
        ws.append_row(row)
        st.success("✅ All data saved to Google Sheet.")
        st.session_state["stage"] = "end"
        st.rerun()

def page_end():
    st.success("全部完成，感谢参与！你可以关闭页面。")
    st.caption("研究者提示：打开 Google Drive 搜索表名即可查看数据。")

# ----------------- Dispatcher -----------------
def dispatch():
    if not st.session_state.get("consent", False):
        page_consent(); return

    stage = st.session_state.get("stage", "choose_order")

    if stage == "choose_order":
        page_choose_order(); return

    # 防御：order 一定要就位
    if "order" not in st.session_state or not st.session_state["order"]:
        st.session_state["order"] = random.sample(["A","B"], 2)

    if stage == "sessionA":
        cond  = st.session_state["order"][0]        # "A" or "B"
        label = label_for(cond)                     # "Ambiguous"/"Directive"
        page_session("A", label); return

    if stage == "formA":
        cond = st.session_state["order"][0]         # "A" or "B"
        page_form("A", cond); return

    if stage == "break":
        page_break(); return

    if stage == "sessionB":
        cond  = st.session_state["order"][1]
        label = label_for(cond)
        page_session("B", label); return

    if stage == "formB":
        cond = st.session_state["order"][1]
        page_form("B", cond); return

    if stage == "demo":
        page_demo(); return

    page_end()

# ----------------- Run -----------------
dispatch()
