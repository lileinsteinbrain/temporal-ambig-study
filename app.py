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

# ------------ 固定使用这张 Google Sheet ------------
GOOGLE_SHEET_ID = "1GppaOTunJ6yt2zJeIhMWxb1xZ2glqUo6XNKK-l-z8FY"
TARGET_SHEET_TITLE = "data_v2"  # 统一写到 data_v2

# ------------ Google Sheets Auth ------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds_info = st.secrets["gcp_service_account"]  # 放在 Streamlit Cloud 的 Secrets
credentials = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
gc = gspread.authorize(credentials)

# ------------ 统一表头（与数据结构一一对应） ------------
HEADERS = [
    # Meta
    "participant_id", "timestamp_utc", "order", "A_condition", "B_condition",
    # Durations
    "dur_directive", "dur_ambiguous",
    # Ambiguous / Directive 自报
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
    只写入 data_v2。不存在就创建并写表头；存在但 A1 为空也补表头。
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

# 追加写入的容错重试（指数退避）
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
        "order": None,                 # ["A","B"] 或 ["B","A"]
        "start_ts": None,
        "end_ts": None,
        "current_condition": None,     # "Directive"/"Ambiguous"（计时保护）
        "durations": {},               # {"Directive": seconds, "Ambiguous": seconds}
        "responses": {"A": {}, "B": {}, "BASE": {}, "DEMO": {}},
        "elapsed_probe": None,         # 防 0s 卡住的小探针
        # 这三项来自用户自报（若没接到，就留空）
        "Ambiguous_size": None,        # 例：small/mid/large 或百分比/半径
        "Directive_time": None,        # 例：3s/6s/10s 或数字秒
        "Repeat_note": None,           # 例：重复次数/体验备注（可留空）
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

init_state()

def gen_participant_id() -> str:
    # 简单可读：PYYMMDD-HHMMSS-rand3
    return datetime.utcnow().strftime("P%y%m%d-%H%M%S-") + f"{random.randint(100,999)}"

# ------------ Helpers ------------
def label_for(cond_tag: str) -> str:
    """输入 'A'/'B'；输出人可读标签（A=Ambiguous, B=Directive）。"""
    return "Ambiguous" if cond_tag == "A" else "Directive"

def _figma_embed_url(proto_url: str) -> str:
    """
    把 Figma 的 proto 分享链接转换成可内嵌的 embed 链接，并隐藏 UI。
    """
    encoded = quote(proto_url, safe="")
    return (
        f"https://www.figma.com/embed?embed_host=share"
        f"&url={encoded}"
        f"&hide-ui=1&hide-sidebar=1&scaling=scale-down-width"
    )

def render_figma(label: str):
    # label 必须是 "Directive" 或 "Ambiguous"
    proto = FIGMA_URL_DIRECTIVE if label == "Directive" else FIGMA_URL_AMBIGUOUS
    embed = _figma_embed_url(proto)
    st.components.v1.iframe(src=embed, height=820, scrolling=False)
    st.link_button("⇱ 在新标签打开原型 / Open prototype", proto, use_container_width=True)

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
            # 生成参与编号
            if not st.session_state["participant_id"]:
                st.session_state["participant_id"] = gen_participant_id()
            st.session_state["consent"] = True
            st.session_state["stage"]   = "baseline"
            st.rerun()

def page_baseline():
    st.subheader("最近一周 & 今日状态（基线测量）")
    b = {}
    st.markdown("**最近一周（1=非常不同意，7=非常同意）**")
    b["BASE_fast_days"]   = likert("我常觉得一天过得很快")
    b["BASE_fragment"]    = likert("我常忘记具体哪天发生了什么")
    b["BASE_control_anx"] = likert("我容易被“时间控制/拖延感”困扰")

    st.markdown("**今日状态**")
    b["mood_today"] = st.slider("你今天整体情绪如何？", 0, 10, 6)
    b["baseline_note"] = st.text_area("此刻关于你“时间感”的一句话（可选）", height=60)

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
    q["Q1"] = likert("我能清晰地感到时间在流动")
    q["Q2"] = likert("我觉得自己能掌控互动的节奏")
    q["Q3"] = likert("系统的反应大多在我的预期之内")
    q["Q4"] = likert("我感觉这段时间的快慢与现实不同")
    q["Q5"] = likert("我与系统的节奏是同步的")
    q["Q6"] = likert("我愿意继续与它多待一会儿")
    q["Q7"] = likert("这段体验让我情绪更平稳")

    st.markdown("### Section 3 — Phenomenological Imagery Probe")
    q["Q8"]  = st.selectbox("如果这段体验有一种质地，它更像：", ["流动的水","厚重的雾","脉动的光","静止的空气","其他"], index=0)
    q["Q9"]  = st.selectbox("这段体验中的时间更像：", ["一条直线","一个圆","循环","空白/真空","其他"], index=0)
    q["Q10"] = st.selectbox("当界面回应你时，你更像是在：", ["引导它","被它带着走","和它一起移动","谁也没在控制"], index=1)
    q["Q11"] = st.text_input("用一个词形容这段体验的氛围：", value="")

    st.markdown("### Section 4 — Reflective / Meta Layer")
    q["Q12"] = st.text_area("在刚才的体验中，你对时间的感觉有变化吗？", height=80)
    q["Q13"] = st.selectbox("当界面的反应不是你的预期时，你的第一反应是：",
                            ["放松","好奇","不安","没什么特别感觉"], index=1)
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

    # 防止个别浏览器焦点导致 0s 卡住：若 2 秒后仍为 0，则软刷新一次
    if elapsed <= 0 and st.session_state.get("elapsed_probe"):
        if time.time() - st.session_state["elapsed_probe"] > 2:
            st.rerun()

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
            # 用 HEADERS 长度补齐
            test_row = ["DBG", now_iso] + [""] * (len(HEADERS) - 2)
            safe_append_row(WS, test_row)
            st.success("✅ TEST 行已写入（去表里刷新看看）")
        except Exception as e:
            st.error(f"❌ TEST 写入失败：{e}")

    if st.button("Submit all & Save", type="primary"):
        # 兜底：若仍在计时但用户直奔提交，把至今时长写进去
        for _lbl in ("Directive", "Ambiguous"):
            if _lbl not in st.session_state["durations"] and st.session_state.get("start_ts"):
                st.session_state["durations"][_lbl] = round(time.time() - st.session_state["start_ts"], 2)

        now_iso = datetime.utcnow().isoformat()
        order = st.session_state["order"] or ["A","B"]
        a_label = label_for(order[0])   # 每段的条件标签
        b_label = label_for(order[1])
        durs = st.session_state["durations"]

        # 自报三项：若 UI 未写入就留空
        amb_size = st.session_state.get("Ambiguous_size", "") or ""
        dir_time = st.session_state.get("Directive_time", "") or ""
        repeat_note = st.session_state.get("Repeat_note", "") or ""

        # 汇总一行（严格按 HEADERS 顺序）
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
            st.error(f"❌ 写入 Google Sheet 失败：{e}")

def page_end():
    st.success("全部完成，感谢参与！你可以关闭页面。")
    st.caption("研究者提示：只看 Google Sheet 底部的 data_v2 页签即可查看数据。")

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
