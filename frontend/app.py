"""
app.py — ContextFlow Streamlit frontend.
Zero business logic. All data fetched via HTTP from the FastAPI backend.
Dark-themed, premium design with custom CSS injected.
"""

import requests
import streamlit as st

# ─────────────────────────────── Config ───────────────────────────────────────

BACKEND_URL = "http://localhost:8000"

SAMPLE_CUSTOMERS = {
    "Priya Sharma (TechNova - Sales)": ("cust_priya_001", "Priya Sharma"),
    "Rahul Mehta (FastMove Logistics - Support)": ("cust_rahul_002", "Rahul Mehta"),
    "➕ New Customer": (None, None),
}

RISK_COLORS = {"low": "#22c55e", "medium": "#f59e0b", "high": "#ef4444"}
RISK_BG = {"low": "#052e16", "medium": "#1c1003", "high": "#1f0000"}

# ─────────────────────────────── Page Setup ───────────────────────────────────

st.set_page_config(
    page_title="ContextFlow — Context Intelligence Agent",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────── CSS Injection ────────────────────────────────

st.markdown(
    """
<style>
/* ── Global ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0f1117;
    color: #e2e8f0;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1200px; }

/* ── Hero header ── */
.hero-header {
    background: linear-gradient(135deg, #1e1b4b 0%, #0f1117 60%, #162032 100%);
    border: 1px solid #2d3a52;
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 2rem;
}
.hero-title {
    font-size: 2.2rem;
    font-weight: 700;
    background: linear-gradient(90deg, #818cf8, #38bdf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
}
.hero-subtitle {
    color: #94a3b8;
    font-size: 0.95rem;
    margin-top: 0.4rem;
}

/* ── Cards ── */
.cf-card {
    background: #1a1f2e;
    border: 1px solid #2d3a52;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.25rem;
}
.cf-card-title {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 0.75rem;
}
.cf-card-body {
    font-size: 0.95rem;
    line-height: 1.7;
    color: #cbd5e1;
}

/* ── Risk badge ── */
.risk-badge {
    display: inline-block;
    padding: 0.4rem 1.2rem;
    border-radius: 9999px;
    font-weight: 700;
    font-size: 1rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

/* ── Insight bullets ── */
.insight-bullet {
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
    margin-bottom: 0.6rem;
    font-size: 0.9rem;
    color: #cbd5e1;
}
.insight-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #818cf8;
    margin-top: 0.55rem;
    flex-shrink: 0;
}

/* ── Next steps ── */
.next-step {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: #0f2139;
    border-left: 3px solid #38bdf8;
    border-radius: 0 8px 8px 0;
    margin-bottom: 0.6rem;
    font-size: 0.9rem;
    color: #cbd5e1;
}

/* ── Vague commitment pill ── */
.vague-pill {
    display: inline-block;
    background: #451a03;
    color: #fb923c;
    border: 1px solid #7c2d12;
    border-radius: 9999px;
    font-size: 0.65rem;
    font-weight: 600;
    padding: 0.1rem 0.5rem;
    margin-left: 0.4rem;
    vertical-align: middle;
}

/* ── Status pill ── */
.status-pill {
    display: inline-block;
    border-radius: 9999px;
    font-size: 0.65rem;
    font-weight: 600;
    padding: 0.15rem 0.55rem;
}

/* ── Input area monospace ── */
.stTextArea textarea {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.85rem !important;
    background: #111827 !important;
    color: #e2e8f0 !important;
    border: 1px solid #2d3a52 !important;
    border-radius: 8px !important;
}

/* ── Selectbox & text input ── */
.stSelectbox > div > div,
.stTextInput > div > div > input {
    background: #1a1f2e !important;
    color: #e2e8f0 !important;
    border-color: #2d3a52 !important;
}

/* ── Button ── */
.stButton > button {
    background: linear-gradient(135deg, #4f46e5, #0ea5e9);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    font-size: 1rem;
    padding: 0.65rem 2.5rem;
    transition: opacity 0.2s;
}
.stButton > button:hover { opacity: 0.88; }

/* ── Divider ── */
.cf-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #2d3a52, transparent);
    margin: 1.5rem 0;
}

/* ── Meta tags (intent, language) ── */
.meta-tag {
    display: inline-block;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 0.2rem 0.6rem;
    font-size: 0.75rem;
    color: #94a3b8;
    margin-right: 0.4rem;
    font-family: 'JetBrains Mono', monospace;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────── Helpers ──────────────────────────────────────


def status_color(status: str) -> str:
    return {
        "pending": "#60a5fa",
        "vague": "#fb923c",
        "overdue": "#f87171",
        "fulfilled": "#4ade80",
        "cancelled": "#94a3b8",
    }.get(status, "#e2e8f0")


def confidence_bar(score: float) -> str:
    pct = int(score * 100)
    colour = "#4ade80" if score >= 0.7 else "#fb923c" if score >= 0.5 else "#f87171"
    return (
        f'<div style="background:#1e293b;border-radius:9999px;height:6px;width:100%;">'
        f'<div style="background:{colour};width:{pct}%;height:6px;border-radius:9999px;"></div>'
        f'</div><span style="font-size:0.7rem;color:#64748b;">{pct}% confidence</span>'
    )


def api_post(endpoint: str, payload: dict) -> dict | None:
    try:
        r = requests.post(f"{BACKEND_URL}{endpoint}", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot connect to backend. Is the FastAPI server running on port 8000?")
    except requests.exceptions.HTTPError as e:
        detail = e.response.json().get("detail", str(e)) if e.response else str(e)
        st.error(f"Backend error: {detail}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")
    return None


def api_get(endpoint: str) -> dict | None:
    try:
        r = requests.get(f"{BACKEND_URL}{endpoint}", timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot connect to backend. Is the FastAPI server running on port 8000?")
    except Exception as e:
        st.error(f"Error: {e}")
    return None


# ─────────────────────────────── Header ────────────────────────────────────────

st.markdown(
    """
<div class="hero-header">
  <p class="hero-title">🧠 ContextFlow</p>
  <p class="hero-subtitle">Follow-up & Context Intelligence Agent &nbsp;·&nbsp; Sales · Support · Ops</p>
</div>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────── Input Panel ──────────────────────────────────

col_left, col_right = st.columns([1, 2], gap="large")

with col_left:
    st.markdown("#### Customer")
    customer_label = st.selectbox(
        "Select customer",
        list(SAMPLE_CUSTOMERS.keys()),
        label_visibility="collapsed",
    )
    selected_id, selected_name = SAMPLE_CUSTOMERS[customer_label]

    if selected_id is None:
        new_cid = st.text_input("Customer ID", placeholder="e.g. cust_jane_003")
        new_name = st.text_input("Customer Name", placeholder="e.g. Jane Doe")
        customer_id = new_cid.strip()
        customer_name = new_name.strip()
    else:
        customer_id = selected_id
        customer_name = selected_name

    # Show customer history if an existing customer is selected
    if selected_id and st.button("📋 View History", use_container_width=True):
        history = api_get(f"/get-customer/{selected_id}")
        if history:
            st.markdown(f"**{len(history['interactions'])} interactions · {len(history['commitments'])} commitments**")
            for h in history["interactions"]:
                with st.expander(f"🗓 {h.get('timestamp','')[:10]} — {h.get('extracted',{}).get('intent','?')}"):
                    st.write(h.get("raw_input", ""))

with col_right:
    st.markdown("#### Interaction Note")
    raw_input = st.text_area(
        "Paste interaction note, transcript, or meeting summary",
        height=240,
        placeholder="Paste your interaction note here.\nSupports English, Hindi, and Hinglish.",
        label_visibility="collapsed",
    )

    analyze_clicked = st.button("⚡ Analyse Interaction", use_container_width=True)

# ─────────────────────────────── Analysis ─────────────────────────────────────

if analyze_clicked:
    if not customer_id:
        st.error("Please enter a Customer ID.")
    elif not raw_input or len(raw_input.strip()) < 10:
        st.error("Interaction note is too short. Please provide at least 10 characters.")
    else:
        with st.spinner("Running 5-step ContextFlow pipeline…"):
            result = api_post(
                "/add-interaction",
                {
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "raw_input": raw_input.strip(),
                },
            )

        if result:
            fo = result.get("final_output", {})
            extracted = result.get("extracted", {})
            reasoning = result.get("context_reasoning", {})
            commitments = result.get("all_commitments", [])

            st.markdown('<div class="cf-divider"></div>', unsafe_allow_html=True)

            # ── Row 1: Summary + Risk ───────────────────────────────────────
            r1a, r1b = st.columns([3, 1], gap="medium")

            with r1a:
                st.markdown(
                    f"""
<div class="cf-card">
  <div class="cf-card-title">📝 Interaction Summary</div>
  <div class="cf-card-body">{fo.get('summary','—')}</div>
  <div style="margin-top:1rem;">
    <span class="meta-tag">intent: {extracted.get('intent','—')}</span>
    <span class="meta-tag">sentiment: {extracted.get('sentiment','—')}</span>
    <span class="meta-tag">lang: {extracted.get('language_detected','—')}</span>
  </div>
</div>
""",
                    unsafe_allow_html=True,
                )

            with r1b:
                rl = fo.get("risk_level", "low")
                rc = RISK_COLORS.get(rl, "#64748b")
                rb = RISK_BG.get(rl, "#1a1f2e")
                st.markdown(
                    f"""
<div class="cf-card" style="text-align:center;background:{rb};border-color:{rc}44;">
  <div class="cf-card-title">⚠️ Risk Level</div>
  <div style="margin:1rem 0;">
    <span class="risk-badge" style="background:{rc}22;color:{rc};border:1px solid {rc}66;">{rl.upper()}</span>
  </div>
  <div style="font-size:0.78rem;color:#94a3b8;line-height:1.5;">{fo.get('risk_reason','—')}</div>
</div>
""",
                    unsafe_allow_html=True,
                )

            # ── Row 2: Context Insights + Next Steps ───────────────────────
            r2a, r2b = st.columns(2, gap="medium")

            with r2a:
                bullets_html = ""
                for insight in fo.get("context_insights", []):
                    bullets_html += (
                        f'<div class="insight-bullet">'
                        f'<div class="insight-dot"></div><span>{insight}</span></div>'
                    )
                if not bullets_html:
                    bullets_html = '<span style="color:#64748b;font-size:0.85rem;">No prior context available.</span>'

                intent_shift = reasoning.get("intent_shift", False)
                shift_banner = ""
                if intent_shift:
                    shift_banner = (
                        f'<div style="background:#1c1003;border:1px solid #92400e;border-radius:8px;'
                        f'padding:0.6rem 1rem;margin-bottom:0.75rem;font-size:0.82rem;color:#fbbf24;">'
                        f'🔄 Intent shift detected: {reasoning.get("intent_shift_description","")}</div>'
                    )

                st.markdown(
                    f"""
<div class="cf-card">
  <div class="cf-card-title">🔍 Context Insights</div>
  {shift_banner}
  {bullets_html}
</div>
""",
                    unsafe_allow_html=True,
                )

            with r2b:
                steps_html = ""
                for i, step in enumerate(fo.get("recommended_next_steps", []), 1):
                    steps_html += (
                        f'<div class="next-step">'
                        f'<span style="color:#38bdf8;font-weight:700;flex-shrink:0;">{i}.</span>'
                        f'<span>{step}</span></div>'
                    )
                if not steps_html:
                    steps_html = '<span style="color:#64748b;font-size:0.85rem;">No next steps generated.</span>'

                st.markdown(
                    f"""
<div class="cf-card">
  <div class="cf-card-title">🎯 Recommended Next Steps</div>
  {steps_html}
</div>
""",
                    unsafe_allow_html=True,
                )

            # ── Pending Actions Table ──────────────────────────────────────
            st.markdown(
                """
<div class="cf-card">
  <div class="cf-card-title">📌 Pending Actions & Commitments</div>
""",
                unsafe_allow_html=True,
            )

            if commitments:
                for c in commitments:
                    status = c.get("status", "pending")
                    is_vague = status == "vague"
                    sc = status_color(status)
                    vague_tag = '<span class="vague-pill">⚠ VAGUE</span>' if is_vague else ""
                    vague_reason_html = ""
                    if is_vague and c.get("vague_reason"):
                        vague_reason_html = (
                            f'<div style="font-size:0.75rem;color:#fb923c;margin-top:0.3rem;">'
                            f'Why vague: {c["vague_reason"]}</div>'
                        )

                    due = c.get("due_date") or "—"
                    owner = c.get("owner", "rep")
                    conf = float(c.get("confidence_score", 0.5))
                    conf_bar = confidence_bar(conf)

                    st.markdown(
                        f"""
<div style="padding:0.75rem 0;border-bottom:1px solid #1e293b;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;">
    <div style="flex:1;">
      <span style="font-size:0.9rem;color:#e2e8f0;">{c.get('description','—')}</span>
      {vague_tag}
      {vague_reason_html}
    </div>
    <div style="flex-shrink:0;text-align:right;font-size:0.75rem;color:#64748b;">
      <span class="meta-tag">👤 {owner}</span>
      <span class="meta-tag">📅 {due}</span>
      <br/><br/>
      <span class="status-pill" style="background:{sc}22;color:{sc};border:1px solid {sc}55;">{status.upper()}</span>
    </div>
  </div>
  <div style="margin-top:0.6rem;max-width:200px;">{conf_bar}</div>
</div>
""",
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<span style="color:#64748b;font-size:0.85rem;">No commitments tracked yet.</span>',
                    unsafe_allow_html=True,
                )

            st.markdown("</div>", unsafe_allow_html=True)

            # ── Objections from extracted ──────────────────────────────────
            objections = extracted.get("objections", [])
            if objections:
                obj_html = "".join(
                    f'<span class="meta-tag" style="margin-bottom:0.3rem;">⚡ {o}</span> '
                    for o in objections
                )
                st.markdown(
                    f"""
<div class="cf-card">
  <div class="cf-card-title">🚧 Objections Raised</div>
  <div style="line-height:2;">{obj_html}</div>
</div>
""",
                    unsafe_allow_html=True,
                )

# ─────────────────────────────── Footer ───────────────────────────────────────

st.markdown(
    """
<div style="text-align:center;margin-top:3rem;color:#334155;font-size:0.75rem;">
  ContextFlow &nbsp;·&nbsp; Context Intelligence Agent &nbsp;·&nbsp; Powered by Groq · LLaMA 3.3 70B
</div>
""",
    unsafe_allow_html=True,
)
