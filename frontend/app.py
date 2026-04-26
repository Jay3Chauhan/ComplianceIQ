"""
ComplianceIQ — Streamlit Chat Frontend
Run: streamlit run frontend/app.py
"""

import streamlit as st
import requests
from datetime import datetime

API_BASE = "http://localhost:8000/api"

# ─────────────────────────────────────────────────────────────────────────────
# Page config (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ComplianceIQ — RBI · SEBI · AA",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS — full design system
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ── Base ─────────────────────────────────────────────────────────────── */
* { font-family: 'Inter', sans-serif !important; box-sizing: border-box; }

[data-testid="stAppViewContainer"] {
    background: #0d1117;
}
[data-testid="stMain"] { background: #0d1117; }
[data-testid="stSidebar"] {
    background: #13181f !important;
    border-right: 1px solid #21262d !important;
}
[data-testid="stSidebarContent"] { padding: 0 !important; }
.block-container { padding: 1.5rem 2rem 2rem 2rem !important; max-width: 900px; }

/* ── Sidebar inner padding ────────────────────────────────────────────── */
section[data-testid="stSidebar"] > div { padding: 0 !important; }

/* ── Hide default Streamlit chrome ───────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }

/* ── Scrollbar ───────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }

/* ── Chat messages ───────────────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    padding: 4px 0 !important;
}
/* User bubble */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) .stChatMessageContent {
    background: #1c2a3a !important;
    border: 1px solid #1f4068 !important;
    border-radius: 18px 18px 4px 18px !important;
    padding: 12px 16px !important;
    color: #c9d1d9 !important;
}
/* Assistant bubble */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) .stChatMessageContent {
    background: #161b22 !important;
    border: 1px solid #21262d !important;
    border-radius: 18px 18px 18px 4px !important;
    padding: 14px 18px !important;
    color: #c9d1d9 !important;
}
/* Avatar styling */
[data-testid="stChatMessageAvatarUser"] {
    background: #1f4068 !important;
    border: 2px solid #2d6a9f !important;
}
[data-testid="stChatMessageAvatarAssistant"] {
    background: #1a2744 !important;
    border: 2px solid #3b5998 !important;
}

/* ── Chat input bar ──────────────────────────────────────────────────── */
[data-testid="stChatInput"] {
    background: #161b22 !important;
    border: 1.5px solid #30363d !important;
    border-radius: 14px !important;
    padding: 4px 8px !important;
    transition: border-color 0.2s;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #58a6ff !important;
    box-shadow: 0 0 0 3px rgba(88,166,255,0.1) !important;
}
[data-testid="stChatInput"] textarea {
    color: #c9d1d9 !important;
    background: transparent !important;
    font-size: 0.9rem !important;
}
[data-testid="stChatInput"] textarea::placeholder { color: #484f58 !important; }

/* ── Answer text ─────────────────────────────────────────────────────── */
.stChatMessageContent p { color: #c9d1d9 !important; line-height: 1.7 !important; }
.stChatMessageContent strong { color: #e6edf3 !important; }
.stChatMessageContent code {
    background: #1f2937 !important;
    color: #79c0ff !important;
    border-radius: 4px !important;
    padding: 1px 5px !important;
    font-size: 0.85em !important;
}

/* ── Expander (sources) ──────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #0d1117 !important;
    border: 1px solid #21262d !important;
    border-radius: 10px !important;
    margin-top: 10px !important;
}
[data-testid="stExpander"] summary {
    color: #8b949e !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    padding: 8px 12px !important;
}
[data-testid="stExpander"] summary:hover { color: #58a6ff !important; }
[data-testid="stExpanderDetails"] { padding: 0 12px 12px 12px !important; }

/* ── Suggestion buttons ──────────────────────────────────────────────── */
.suggestion-btn > button {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 20px !important;
    color: #8b949e !important;
    font-size: 0.78rem !important;
    padding: 6px 14px !important;
    transition: all 0.18s !important;
    white-space: normal !important;
    height: auto !important;
    line-height: 1.4 !important;
}
.suggestion-btn > button:hover {
    background: #1c2a3a !important;
    border-color: #58a6ff !important;
    color: #58a6ff !important;
}

/* ── Sidebar elements ────────────────────────────────────────────────── */
.sb-logo {
    display: flex; align-items: center; gap: 10px;
    padding: 20px 16px 16px; border-bottom: 1px solid #21262d;
    margin-bottom: 4px;
}
.sb-logo-icon { font-size: 1.6rem; }
.sb-title { font-size: 1rem; font-weight: 700; color: #e6edf3; }
.sb-sub { font-size: 0.68rem; color: #484f58; margin-top: 1px; }

.sb-section {
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #484f58;
    padding: 14px 16px 6px;
}

.doc-item {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 8px 16px; margin: 0; cursor: default;
    transition: background 0.15s;
}
.doc-item:hover { background: #161b22; }
.doc-dot {
    width: 8px; height: 8px; border-radius: 50%;
    flex-shrink: 0; margin-top: 4px;
}
.doc-dot-rbi  { background: #388bfd; }
.doc-dot-sebi { background: #f78166; }
.doc-dot-aa   { background: #56d364; }
.doc-dot-other{ background: #8b949e; }
.doc-item-name { font-size: 0.75rem; color: #8b949e; line-height: 1.4; }
.doc-item-meta { font-size: 0.65rem; color: #484f58; margin-top: 1px; }

.status-pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 20px;
    font-size: 0.68rem; font-weight: 500;
}
.status-online  { background: #0d2818; border: 1px solid #1a4731; color: #56d364; }
.status-offline { background: #2d1117; border: 1px solid #67060c; color: #f85149; }

/* ── Source cards ────────────────────────────────────────────────────── */
.src-card {
    background: #0d1117; border: 1px solid #21262d;
    border-radius: 10px; padding: 12px 14px; margin: 6px 0;
    transition: border-color 0.15s;
}
.src-card:hover { border-color: #388bfd; }
.src-card-top { display: flex; justify-content: space-between; align-items: flex-start; }
.src-doc { font-size: 0.8rem; font-weight: 600; color: #79c0ff; }
.src-meta { font-size: 0.68rem; color: #484f58; font-family: monospace; margin-top: 2px; }
.src-badge {
    font-size: 0.68rem; font-weight: 600; padding: 2px 8px;
    border-radius: 10px; flex-shrink: 0; margin-left: 8px;
}
.src-badge-high { background: #0d2818; color: #56d364; border: 1px solid #1a4731; }
.src-badge-med  { background: #2d1b00; color: #e3b341; border: 1px solid #4d2d00; }
.src-badge-low  { background: #2d1117; color: #f85149; border: 1px solid #67060c; }
.src-snippet { font-size: 0.75rem; color: #8b949e; line-height: 1.55; margin-top: 8px; }
.src-link {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 0.7rem; color: #388bfd;
    text-decoration: none; margin-top: 8px;
}
.src-link:hover { color: #58a6ff; text-decoration: underline; }

/* ── Token usage ─────────────────────────────────────────────────────── */
.token-row {
    display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap;
}
.token-chip {
    display: inline-flex; align-items: center; gap: 4px;
    background: #161b22; border: 1px solid #21262d;
    border-radius: 20px; padding: 2px 10px;
    font-size: 0.67rem; color: #484f58;
}
.token-chip span { color: #8b949e; }

/* ── Empty state ─────────────────────────────────────────────────────── */
.empty-wrap {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 48px 16px 32px; text-align: center;
}
.empty-icon { font-size: 3rem; margin-bottom: 12px; }
.empty-h { font-size: 1.3rem; font-weight: 700; color: #e6edf3; margin-bottom: 8px; }
.empty-p { font-size: 0.85rem; color: #484f58; max-width: 480px; line-height: 1.6; }

/* ── Page header ─────────────────────────────────────────────────────── */
.page-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 6px; padding-bottom: 14px;
    border-bottom: 1px solid #21262d;
}
.page-title { font-size: 1.4rem; font-weight: 700; color: #e6edf3; }
.page-desc { font-size: 0.8rem; color: #484f58; margin-top: 3px; }
.page-badge {
    display: flex; align-items: center; gap: 6px;
    background: #161b22; border: 1px solid #21262d;
    border-radius: 8px; padding: 6px 12px;
}
.page-badge-cat { font-size: 0.72rem; font-weight: 600; color: #8b949e; }
.page-badge-val { font-size: 0.72rem; color: #58a6ff; font-weight: 600; }

/* ── Selectbox, number_input ─────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #c9d1d9 !important;
    border-radius: 8px !important;
    font-size: 0.82rem !important;
}
[data-testid="stSelectbox"] label,
[data-testid="stNumberInput"] label { color: #8b949e !important; font-size: 0.75rem !important; }

/* ── Checkbox ────────────────────────────────────────────────────────── */
[data-testid="stCheckbox"] label { color: #8b949e !important; font-size: 0.78rem !important; }

/* ── Sidebar button ──────────────────────────────────────────────────── */
.sb-btn > button {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #8b949e !important;
    border-radius: 8px !important;
    font-size: 0.78rem !important;
    transition: all 0.15s !important;
}
.sb-btn > button:hover {
    background: #2d1117 !important;
    border-color: #f85149 !important;
    color: #f85149 !important;
}

/* ── Divider ─────────────────────────────────────────────────────────── */
hr { border-color: #21262d !important; margin: 6px 0 !important; }

/* ── Warning / error ─────────────────────────────────────────────────── */
[data-testid="stAlert"] { border-radius: 8px !important; font-size: 0.8rem !important; }

/* ── Timestamp ───────────────────────────────────────────────────────── */
.msg-ts { font-size: 0.63rem; color: #30363d; margin-top: 6px; text-align: right; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
for k, v in [("history", []), ("docs_cache", None), ("docs_ok", None), ("_prefill", None)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def fetch_docs() -> list[dict]:
    if st.session_state.docs_cache is not None:
        return st.session_state.docs_cache
    try:
        r = requests.get(f"{API_BASE}/documents", timeout=15)
        r.raise_for_status()
        st.session_state.docs_cache = r.json()
        st.session_state.docs_ok = True
    except Exception:
        st.session_state.docs_cache = []
        st.session_state.docs_ok = False
    return st.session_state.docs_cache


def dedup_sources(sources: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for s in sources:
        key = (s["doc_name"], s["page_number"])
        if key not in seen or s.get("relevance_score", 0) > seen[key].get("relevance_score", 0):
            seen[key] = s
    return sorted(seen.values(), key=lambda x: x.get("relevance_score", 0), reverse=True)


def dot_class(cat: str) -> str:
    return {"RBI": "rbi", "SEBI": "sebi", "AA": "aa"}.get(cat, "other")


def badge_class(score: float) -> str:
    return "src-badge-high" if score >= 0.70 else "src-badge-med" if score >= 0.50 else "src-badge-low"


def render_sources(sources: list[dict]) -> None:
    unique = dedup_sources(sources)
    with st.expander(f"📎 {len(unique)} source{'s' if len(unique) != 1 else ''} cited  ·  click to expand"):
        for src in unique:
            score = src.get("relevance_score", 0)
            bcls = badge_class(score)
            cat_dot = dot_class(src["category"])
            cat_labels = {"RBI": "RBI", "SEBI": "SEBI", "AA": "AA"}
            cat_label = cat_labels.get(src["category"], src["category"])
            link = (f'<a class="src-link" href="{src["source_url"]}" target="_blank">'
                    f'↗ View official circular</a>') if src.get("source_url") else ""
            snippet = src.get("snippet", "")[:280].replace("<", "&lt;").replace(">", "&gt;")
            st.markdown(f"""
<div class="src-card">
  <div class="src-card-top">
    <div>
      <div class="src-doc">
        <span class="src-badge {bcls}" style="margin-right:6px">{cat_label}</span>
        {src['doc_name']}
      </div>
      <div class="src-meta">{src['circular_id']}  ·  Page {src['page_number']}</div>
    </div>
    <span class="src-badge {bcls}">{score:.0%} match</span>
  </div>
  <div class="src-snippet">"{snippet}…"</div>
  {link}
</div>""", unsafe_allow_html=True)


def render_token_row(usage: dict) -> None:
    if not usage:
        return
    st.markdown(f"""
<div class="token-row">
  <div class="token-chip">🔢 total <span>{usage.get('total_tokens',0):,}</span></div>
  <div class="token-chip">📥 prompt <span>{usage.get('prompt_tokens',0):,}</span></div>
  <div class="token-chip">📤 reply <span>{usage.get('completion_tokens',0):,}</span></div>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:

    # Logo / brand
    st.markdown("""
<div class="sb-logo">
  <span class="sb-logo-icon">⚖️</span>
  <div>
    <div class="sb-title">ComplianceIQ</div>
    <div class="sb-sub">RBI · SEBI · Account Aggregator</div>
  </div>
</div>""", unsafe_allow_html=True)

    # API status
    docs = fetch_docs()
    if st.session_state.docs_ok:
        st.markdown('<div style="padding:8px 16px"><span class="status-pill status-online">● API online</span></div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div style="padding:8px 16px"><span class="status-pill status-offline">● API offline</span></div>',
                    unsafe_allow_html=True)

    # ── Query settings ──────────────────────────────────────────
    st.markdown('<div class="sb-section">Query Settings</div>', unsafe_allow_html=True)

    with st.container():
        category = st.selectbox("Scope", ["ALL", "RBI", "SEBI", "AA"],
                                help="Filter retrieval to one regulator")
        col_a, col_b = st.columns([1, 1])
        with col_a:
            top_k = st.number_input("Chunks", min_value=3, max_value=10, value=5)
        with col_b:
            show_sources = st.checkbox("Show sources", value=True)

    # ── Documents ───────────────────────────────────────────────
    st.markdown('<div class="sb-section">Loaded Documents</div>', unsafe_allow_html=True)

    if not docs:
        st.markdown('<div style="padding:4px 16px 12px;font-size:0.75rem;color:#484f58">No documents ingested yet.</div>',
                    unsafe_allow_html=True)
    else:
        for doc in docs:
            dc = dot_class(doc["category"])
            name = doc["doc_name"].replace("&", "&amp;")
            date = doc.get("date", "")
            cid  = doc.get("circular_id", "")
            st.markdown(f"""
<div class="doc-item">
  <div class="doc-dot doc-dot-{dc}" style="margin-top:5px"></div>
  <div>
    <div class="doc-item-name">{name}</div>
    <div class="doc-item-meta">{cid}{' · ' + date if date else ''}</div>
  </div>
</div>""", unsafe_allow_html=True)

        if st.session_state.docs_ok is False:
            with st.container():
                st.markdown('<div class="sb-btn">', unsafe_allow_html=True)
                if st.button("↻  Refresh list", use_container_width=True):
                    st.session_state.docs_cache = None
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

    # ── Session ─────────────────────────────────────────────────
    st.markdown('<div class="sb-section">Session</div>', unsafe_allow_html=True)
    n = len(st.session_state.history)
    st.markdown(f'<div style="padding:0 16px 8px;font-size:0.75rem;color:#484f58">'
                f'{n} message{"s" if n != 1 else ""}</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="sb-btn">', unsafe_allow_html=True)
        if st.button("🗑  Clear conversation", use_container_width=True):
            st.session_state.history = []
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Page header
# ─────────────────────────────────────────────────────────────────────────────
scope_label = category if category != "ALL" else "All regulators"
st.markdown(f"""
<div class="page-header">
  <div>
    <div class="page-title">⚖️ ComplianceIQ</div>
    <div class="page-desc">Ask questions about RBI, SEBI and AA regulations — every answer cites exact pages.</div>
  </div>
  <div class="page-badge">
    <span class="page-badge-cat">Scope:</span>
    <span class="page-badge-val">{scope_label}</span>
  </div>
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Empty state + suggestion chips
# ─────────────────────────────────────────────────────────────────────────────
SUGGESTIONS = [
    ("📋", "KYC documents required to open a demat account?"),
    ("🏦", "What are RBI norms for digital lending apps?"),
    ("🔗", "How does the Account Aggregator framework work?"),
    ("⚠️", "Penalties for KYC non-compliance under RBI?"),
    ("📑", "Net Owned Fund requirement for an NBFC-AA?"),
    ("🎥", "What is Video-based KYC (V-CIP) and its process?"),
    ("💰", "How should interest rates be disclosed in digital loans?"),
    ("📊", "SEBI norms for client fund segregation by stock brokers?"),
]

if not st.session_state.history:
    st.markdown("""
<div class="empty-wrap">
  <div class="empty-icon">💬</div>
  <div class="empty-h">Ask your first compliance question</div>
  <div class="empty-p">Answers are grounded exclusively in RBI Master Directions, SEBI circulars,
  and AA Framework guidelines — with page-level citations. No hallucinations.</div>
</div>""", unsafe_allow_html=True)

    st.markdown("**Try a question:**")
    rows = [SUGGESTIONS[:4], SUGGESTIONS[4:]]
    for row in rows:
        cols = st.columns(4)
        for col, (icon, text) in zip(cols, row):
            with col:
                st.markdown('<div class="suggestion-btn">', unsafe_allow_html=True)
                if st.button(f"{icon} {text}", key=f"sug_{text[:20]}", use_container_width=True):
                    st.session_state._prefill = text
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Render existing chat history
# ─────────────────────────────────────────────────────────────────────────────
for turn in st.session_state.history:
    with st.chat_message("user", avatar="👤"):
        st.markdown(turn["question"])
        if turn.get("time"):
            st.markdown(f'<div class="msg-ts">{turn["time"]}</div>', unsafe_allow_html=True)

    with st.chat_message("assistant", avatar="⚖️"):
        st.markdown(turn["answer"])
        render_token_row(turn.get("usage", {}))
        if show_sources and turn.get("sources"):
            render_sources(turn["sources"])

# ─────────────────────────────────────────────────────────────────────────────
# Chat input
# ─────────────────────────────────────────────────────────────────────────────
prefill = st.session_state._prefill
if prefill:
    st.session_state._prefill = None

question = st.chat_input(
    placeholder="e.g. What are the KYC requirements for a digital lending platform?",
) or prefill

if question:
    with st.chat_message("user", avatar="👤"):
        st.markdown(question)
        ts = datetime.now().strftime("%I:%M %p")
        st.markdown(f'<div class="msg-ts">{ts}</div>', unsafe_allow_html=True)

    with st.chat_message("assistant", avatar="⚖️"):
        thinking = st.empty()
        thinking.markdown(
            '<div style="color:#484f58;font-size:0.82rem">⏳ Searching regulatory documents…</div>',
            unsafe_allow_html=True,
        )
        try:
            history_payload = [
                {"question": t["question"], "answer": t["answer"]}
                for t in st.session_state.history[-3:]
            ] or None

            res = requests.post(
                f"{API_BASE}/query",
                json={"question": question, "category": category,
                      "top_k": int(top_k), "history": history_payload},
                timeout=60,
            )
            res.raise_for_status()
            data = res.json()

            answer  = data.get("answer", "No answer returned.")
            sources = data.get("sources", [])
            usage   = data.get("usage", {})

            thinking.empty()
            st.markdown(answer)
            render_token_row(usage)
            if show_sources and sources:
                render_sources(sources)

            st.session_state.history.append({
                "question": question,
                "answer":   answer,
                "sources":  sources,
                "usage":    usage,
                "time":     ts,
            })

        except requests.exceptions.ConnectionError:
            thinking.empty()
            st.error("⚡ Cannot reach the API. Make sure `uvicorn api.main:app --reload` is running on port 8000.")
        except requests.exceptions.Timeout:
            thinking.empty()
            st.warning("⏱️ Request timed out. The server may be loading the embedding model — please try again in a few seconds.")
        except Exception as e:
            thinking.empty()
            st.error(f"Unexpected error: {e}")
