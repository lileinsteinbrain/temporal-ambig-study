# app.py
import random
import time
from datetime import datetime

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

from config import (
    FIGMA_URL_DIRECTIVE,   # Figma embed URL
    FIGMA_URL_AMBIGUOUS,   # Figma embed URL
    SESSION_SECONDS        # e.g. 120
)

# ------------ 固定使用这张 Google Sheet ------------
GOOGLE_SHEET_ID = "1GppaOTunJ6yt2zJeIhMWxb1xZ2glqUo6XNKK-l-z8FY"

# ------------ Google Sheets Auth ------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds_info = st.secrets["gcp_service_account"]  # 放在 Streamlit Cloud 的 Secrets
credentials = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
gc = gspread.authorize(credentials)

# ------------ 统一表头（若表为空会自动补上） ------------
HEADERS = [
    # Meta
    "timestamp_utc", "order", "A_condition", "B_condition",
    # Durations
    "dur_directive", "dur_ambiguous",
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
    """优先 data；没有就用第一个工作表；如为空自动写入表头。"""
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    try:
        ws = sh.worksheet("data")
        return ws
    except gspread.WorksheetNotFound:
        pass

    try:
        ws = sh.sheet1
    except Exception:
        ws = sh.add_worksheet(title="Sheet1", rows=2000, cols=80)

    try:
        a1 = ws.acell("A1").value
    except Exception:
        a1 = None

    if not a1 or "Type '@Date' to open date picker" in str(a1):
        ws.update("A1", [HEADERS])  # 写入表头

    return ws

# 👇 启动就初始化工作表 & 表头（不用等到最后一步）
WS = open_target_ws()

# ------------ Page config ------------
st.set_page_config(page_title="Temporal Feel Study", page_icon="🫧", layout="centered")

# ------------ State init ------------
def init_state():
    defaults = {
        "consent": False,
        # flow: consent -> baseline -> choose_order -> sessionA -> formA -> break -> sessionB -> formB -> demo -> end
        "stage": "consent",
        "order": None,                 # ["A","B"] 或 ["B","A"]
        "start_ts": None,
        "end_ts": None,
        "current_condition": None,     # "Directive"/"Ambiguous"（计时保护）
        "durations": {},               # {"Directive": seconds, "Ambiguous": seconds}
        "responses": {"A": {}, "B": {}, "BASE": {}, "DEMO": {}},
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

init_state()

# ------------ Helpers ------------
def label_for(cond_tag: str) -> str:
    """输入 'A'/'B'；输出人可读标签（A=Ambiguous, B=Directive）。"""
    return "Ambiguous" if cond_tag == "A" else "Directive"

def render_figma(label: str):
    url = FIGMA_URL_DIRECTIVE if label == "Directive" else FIGMA_URL_AMBIGUOUS
    st.components.v1.iframe(src=url, height=640, scrolling=True)
    # 兜底外链（Figma 偶尔会拒绝内嵌）
    st.link_button("⇱ 在新标签打开原型 / Open prototype", url, use_container_width=True)

def start_timer(label: str):
    st.session_state["current_condition"] = label
    st.session_state["start_ts"] = time.time()
    st.session_state["end_ts"] = None

def stop_timer() -> float:
    if st.session_state["start_ts"] is None:
        return 0.0
    st.session_state["end_ts"] = time.time()
    return float(st.session_state["end_ts"] - st.session_state["start_ts"])

def likert(prompt: str):
    return st.radio(prompt, options=[1,2,3,4,5,6,7], horizontal=True)

# ------------ UI blocks ------------
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
    if st.button("继续 / Continue", use_container_width=True):
        if not agree:
            st.warning("请先勾选同意")
        else:
            st.session_state["consent"] = True
            st.session_state["stage"]   = "baseline"
            st.rerun()

def page_baseline():
    st.subheader("最近一周 & 今日状态（基线测量）")
    b = {}
    st.markdown("**最近一周（1=非常不同意，7=非常同意）**")
    b["BASE_fast_days"]   = likert("我常觉得一天过得很快（时间加速感）")
    b["BASE_fragment"]    = likert("我常忘记具体哪天发生了什么（时间断裂感）")
    b["BASE_control_anx"] = likert("我容易被“时间控制/拖延感”困扰（时间焦虑）")

    st.markdown("**今日状态**")
    b["mood_today"] = st.slider("你今天整体情绪如何？", 0, 10, 6)
    b["baseline_note"] = st.text_area("此刻关于你自己的“时间感”的一句话（可选）", height=60)

    if st.button("继续 / Continue", type="primary", use_container_width=True):
        st.session_state["responses"]["BASE"] = b
        st.session_state["stage"] = "choose_order"
        st.rerun()

def page_choose_order():
    st.subheader("选择体验顺序（或随机）")
    choice = st.radio("先体验哪一个？", ["Directive → Ambiguous", "Ambiguous → Directive", "随机 / Random"], index=2)
    if st.button("开始 / Start", use_container_width=True):
        if choice == "随机 / Random":
            order = ["A","B"] if int(time.time()) % 2 == 0 else ["B","A"]
        else:
            order_labels = ["Directive","Ambiguous"] if choice.startswith("Directive") else ["Ambiguous","Directive"]
            order = ["A","B"] if order_labels[0] == "Ambiguous" else ["B","A"]
        st.session_state["order"] = order
        st.session_state["stage"] = "sessionA"
        st.rerun()

def questionnaire_ui(tag: str):
    q = {}
    st.markdown("### Section 2 — Structured / Directive Layer（1–7）")
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
    st.subheader(f"Session {tag} — {label}")
    st.caption("建议体验约 2 分钟。点击开始后计时自动记录。")

    # 条件切换保护：若切换了条件，清空之前计时
    if st.session_state["current_condition"] not in (None, label):
        st.session_state["start_ts"] = None
        st.session_state["end_ts"] = None

    if st.session_state["start_ts"] is None:
        if st.button("▶️ Start", type="primary"):
            start_timer(label)
            st.rerun()
        return

    elapsed = int(time.time() - st.session_state["start_ts"])
    remaining = max(0, SESSION_SECONDS - elapsed)
    st.info(f"已用时 {elapsed}s · 建议至少 {SESSION_SECONDS}s · 剩余 {remaining}s")

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
            st.caption("⏳ 建议至少体验到推荐时长后再停止。")

def page_form(tag: str, cond_tag: str):
    label = label_for(cond_tag)  # "Ambiguous"/"Directive"
    st.subheader(f"Questionnaire {tag} — {label}")
    st.caption("请基于刚才这一段体验作答。")
    questionnaire_ui(tag)
    if st.button("Submit questionnaire", type="primary"):
        st.success("✅ Responses saved.")
        st.session_state["stage"] = "break" if tag == "A" else "demo"
        st.rerun()

def page_break():
    st.info("休息 1 分钟后进行下一段体验（喝口水、伸展一下）。准备好后点击继续。")
    if st.button("Continue to Session B", use_container_width=True):
        st.session_state["stage"] = "sessionB"
        st.rerun()

def page_demo():
    st.subheader("Demographics（简）")
    d = {}
    d["age"]    = st.selectbox("年龄段", ["18–24","25–34","35–44","45–54","55+"], index=1)
    d["gender"] = st.selectbox("性别（可选）", ["不透露","女性","男性","非二元/其他"], index=0)
    st.session_state["responses"]["DEMO"] = d

    # 🔧 调试：一键试写一行，方便排查权限/连接问题
    if st.button("🔧 Test write to Sheet (debug)"):
        try:
            now_iso = datetime.utcnow().isoformat()
            WS.append_row([now_iso, "TEST", "", "", "", ""], value_input_option="RAW")
            st.success("✅ TEST 行已写入（去表里刷新看看）")
        except Exception as e:
            st.error(f"❌ TEST 写入失败：{e}")

    if st.button("Submit all & Save", type="primary"):
        now_iso = datetime.utcnow().isoformat()
        order = st.session_state["order"] or ["A","B"]
        a_label = label_for(order[0])   # 记录每一段的条件标签
        b_label = label_for(order[1])
        durs = st.session_state["durations"]

        row = [
            now_iso,
            "→".join(order),
            a_label, b_label,
            durs.get("Directive", None),
            durs.get("Ambiguous", None),
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
            WS.append_row(row, value_input_option="RAW")
            st.success("✅ All data saved to Google Sheet.")
            st.session_state["stage"] = "end"
            st.rerun()
        except Exception as e:
            st.error(f"❌ 写入 Google Sheet 失败：{e}")

def page_end():
    st.success("全部完成，感谢参与！你可以关闭页面。")
    st.caption("研究者提示：打开 Google Drive 搜索表名即可查看数据。")

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
