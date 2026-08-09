"""
ComplianceIQ — production chat frontend.
Run: streamlit run frontend/app.py
"""

from __future__ import annotations

import html
import json
import os
from datetime import datetime

import requests
import streamlit as st

API_BASE = os.getenv("COMPLIANCEIQ_API_URL", "http://localhost:8000/api").rstrip("/")

st.set_page_config(
    page_title="ComplianceIQ",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1000px 420px at 8% -8%, rgba(37,99,235,.16), transparent 55%),
    radial-gradient(800px 360px at 92% 0%, rgba(14,165,233,.10), transparent 50%),
    #0b1220;
}
[data-testid="stSidebar"] {
  background: #0f172a;
  border-right: 1px solid #1e293b;
}
.block-container { padding-top: 1.2rem; padding-bottom: 5rem; max-width: 880px; }
#MainMenu, footer, [data-testid="stToolbar"] { display: none !important; }

[data-testid="stChatMessage"] { background: transparent; border: none; }
.stChatMessageContent p, .stChatMessageContent li { color: #e2e8f0; line-height: 1.7; }

.status-pill {
  display: inline-flex; align-items: center; gap: 8px;
  background: #0f172a; border: 1px solid #334155; color: #93c5fd;
  border-radius: 999px; padding: 6px 12px; font-size: 0.82rem; margin: 4px 0 10px;
}
.status-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #38bdf8;
  box-shadow: 0 0 0 0 rgba(56,189,248,.7);
  animation: pulse 1.4s infinite;
}
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(56,189,248,.55); }
  70% { box-shadow: 0 0 0 8px rgba(56,189,248,0); }
  100% { box-shadow: 0 0 0 0 rgba(56,189,248,0); }
}

.mode-pill {
  display: inline-block; margin-top: 8px; padding: 3px 10px; border-radius: 999px;
  font-size: 0.72rem; font-weight: 600;
}
.mode-reg { background: #0c1a3a; border: 1px solid #1e3a5f; color: #60a5fa; }
.mode-gen { background: #1a1030; border: 1px solid #3b2660; color: #c4b5fd; }
.mode-nf  { background: #3f1d0a; border: 1px solid #9a3412; color: #fdba74; }

.meta-row { margin-top: 8px; color: #94a3b8; font-size: 0.75rem; }
.source-card {
  background: #020617; border: 1px solid #1e293b; border-radius: 10px;
  padding: 10px 12px; margin: 6px 0;
}
.source-title { color: #60a5fa; font-weight: 600; font-size: 0.85rem; }
.source-meta { color: #64748b; font-size: 0.72rem; margin-top: 2px; }
.source-snip { color: #94a3b8; font-size: 0.78rem; margin-top: 8px; line-height: 1.5; }
.hero-h { font-size: 1.45rem; font-weight: 700; color: #f8fafc; margin-bottom: 6px; }
.hero-p { color: #64748b; font-size: 0.9rem; line-height: 1.6; max-width: 560px; margin: 0 auto 8px; }
.sb-brand { font-size: 1.05rem; font-weight: 700; color: #f8fafc; }
.sb-sub { color: #64748b; font-size: 0.72rem; margin-top: 2px; }
.doc-line { color: #cbd5e1; font-size: 0.78rem; margin: 4px 0; }
</style>
""",
    unsafe_allow_html=True,
)

for key, default in [
    ("history", []),
    ("docs_cache", None),
    ("api_ok", None),
    ("_prefill", None),
    ("_stream_meta", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def fetch_docs(force: bool = False) -> list[dict]:
    if not force and st.session_state.docs_cache is not None:
        return st.session_state.docs_cache
    try:
        r = requests.get(f"{API_BASE}/documents", timeout=15)
        r.raise_for_status()
        st.session_state.docs_cache = r.json()
        st.session_state.api_ok = True
    except Exception:
        st.session_state.docs_cache = []
        st.session_state.api_ok = False
    return st.session_state.docs_cache


def dedup(sources: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for s in sources:
        key = (s.get("doc_name"), s.get("page_number"))
        prev = seen.get(key)
        if prev is None or s.get("relevance_score", 0) > prev.get("relevance_score", 0):
            seen[key] = s
    return sorted(seen.values(), key=lambda x: x.get("relevance_score", 0), reverse=True)


def mode_label(mode: str) -> str:
    return {
        "regulatory": '<span class="mode-pill mode-reg">Regulatory — cited from documents</span>',
        "general": '<span class="mode-pill mode-gen">General finance — AI knowledge</span>',
        "not_found": '<span class="mode-pill mode-nf">Not found in loaded corpus</span>',
    }.get(mode, "")


def render_sources(sources: list[dict]) -> None:
    unique = dedup(sources)
    if not unique:
        return
    with st.expander(f"Sources ({len(unique)})", expanded=False):
        for i, s in enumerate(unique, 1):
            snip = html.escape((s.get("snippet") or "")[:220])
            link = ""
            if s.get("source_url"):
                link = f'<div style="margin-top:6px"><a href="{html.escape(s["source_url"])}" target="_blank">Official circular</a></div>'
            st.markdown(
                f"""
<div class="source-card">
  <div class="source-title">[{i}] {html.escape(s.get('doc_name', ''))}</div>
  <div class="source-meta">{html.escape(s.get('circular_id', ''))} · Page {s.get('page_number', '?')} · score {s.get('relevance_score', 0):.2f}</div>
  <div class="source-snip">{snip}…</div>
  {link}
</div>
""",
                unsafe_allow_html=True,
            )


def export_markdown(history: list[dict]) -> str:
    lines = ["# ComplianceIQ conversation\n"]
    for turn in history:
        lines.append(f"## User\n{turn['question']}\n")
        lines.append(f"## Assistant ({turn.get('mode', '')})\n{turn['answer']}\n")
    return "\n".join(lines)


def stream_query(
    question: str,
    category: str,
    top_k: int,
    answer_mode: str,
    history_payload: list | None,
):
    """Yields ('status'|'token'|'error', content) tuples."""
    st.session_state._stream_meta = {
        "sources": [],
        "mode": "general",
        "usage": {},
        "latency_ms": 0,
    }
    try:
        with requests.post(
            f"{API_BASE}/query/stream",
            json={
                "question": question,
                "category": category,
                "top_k": top_k,
                "answer_mode": answer_mode,
                "history": history_payload,
            },
            stream=True,
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    ev = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                kind = ev.get("type")
                if kind == "status":
                    yield ("status", ev.get("message", "Working…"))
                elif kind == "token":
                    yield ("token", ev.get("content", ""))
                elif kind == "meta":
                    st.session_state._stream_meta["sources"] = ev.get("sources", [])
                    st.session_state._stream_meta["mode"] = ev.get("mode", "general")
                    yield ("status", f"Mode: {ev.get('mode', 'general')}")
                elif kind == "usage":
                    if ev.get("usage"):
                        st.session_state._stream_meta["usage"] = ev["usage"]
                    st.session_state._stream_meta["latency_ms"] = ev.get("latency_ms", 0)
                elif kind == "error":
                    yield ("error", ev.get("content", "Something went wrong."))
    except requests.exceptions.ConnectionError:
        yield (
            "error",
            "API is offline. Start it with: uvicorn api.main:app --reload --port 8000",
        )
    except requests.exceptions.Timeout:
        yield ("error", "Request timed out. Please try again.")
    except Exception as e:
        yield ("error", f"Unexpected error: {e}")


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sb-brand">⚖️ ComplianceIQ</div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-sub">RBI · SEBI · AA · Finance</div>', unsafe_allow_html=True)
    st.divider()

    docs = fetch_docs()
    if st.session_state.api_ok:
        st.success("API online", icon="✅")
    else:
        st.error("API offline", icon="⚠️")

    answer_mode_label = st.selectbox(
        "Answer mode",
        ["Auto (recommended)", "Regulatory only", "General finance"],
        help="Auto cites documents when confident; otherwise uses general finance knowledge.",
    )
    answer_mode = {
        "Auto (recommended)": "auto",
        "Regulatory only": "regulatory",
        "General finance": "general",
    }[answer_mode_label]

    category = st.selectbox("Document scope", ["ALL", "RBI", "SEBI", "AA"])
    top_k = st.slider("Chunks to retrieve", 3, 10, 6)
    show_sources = st.toggle("Show sources", value=True)

    st.subheader("Knowledge base")
    if st.button("Refresh documents", use_container_width=True):
        fetch_docs(force=True)
        st.rerun()
    if not docs:
        st.caption("No documents ingested yet.")
    else:
        for doc in docs:
            color = {"RBI": "🔵", "SEBI": "🟠", "AA": "🟢"}.get(doc.get("category"), "⚪")
            st.markdown(
                f'<div class="doc-line">{color} {html.escape(doc.get("doc_name", ""))}</div>',
                unsafe_allow_html=True,
            )

    st.subheader("Session")
    st.caption(f"{len(st.session_state.history)} messages in this chat")
    if st.session_state.history:
        st.download_button(
            "Export chat (.md)",
            data=export_markdown(st.session_state.history),
            file_name=f"complianceiq-{datetime.now().strftime('%Y%m%d-%H%M')}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    if st.button("New conversation", use_container_width=True, type="primary"):
        st.session_state.history = []
        st.session_state._prefill = None
        st.rerun()

# ── Header ───────────────────────────────────────────────────────────────────
left, right = st.columns([3, 1])
with left:
    st.markdown("### ComplianceIQ")
    st.caption("Grounded regulatory Q&A with page citations")
with right:
    st.markdown(f"**Scope:** {category if category != 'ALL' else 'All regulators'}")

SUGGESTIONS = {
    "Compliance": [
        "What KYC documents are required for opening accounts?",
        "What are penalties for KYC non-compliance under RBI?",
        "What are RBI norms for digital lending apps?",
        "How does the Account Aggregator framework work?",
    ],
    "Finance": [
        "What is SIP and how does it work?",
        "Difference between ELSS and PPF for tax saving?",
        "What is an IPO and how do I apply?",
        "How does UPI work at a high level?",
    ],
}

if not st.session_state.history:
    st.markdown('<div style="text-align:center;padding:28px 0 8px">', unsafe_allow_html=True)
    st.markdown('<div class="hero-h">Ask a compliance or finance question</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-p">Auto mode cites loaded circulars when retrieval is confident, '
        "otherwise answers with careful general finance guidance.</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    for section, chips in SUGGESTIONS.items():
        st.caption(section.upper())
        cols = st.columns(2)
        for i, text in enumerate(chips):
            if cols[i % 2].button(text, key=f"sug_{section}_{i}", use_container_width=True):
                st.session_state._prefill = text
                st.rerun()

# ── History ──────────────────────────────────────────────────────────────────
for idx, turn in enumerate(st.session_state.history):
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        st.markdown(turn["answer"])
        label = mode_label(turn.get("mode", ""))
        if label:
            st.markdown(label, unsafe_allow_html=True)
        latency = turn.get("latency_ms")
        if latency:
            st.markdown(
                f'<div class="meta-row">Answered in {latency / 1000:.1f}s</div>',
                unsafe_allow_html=True,
            )
        if show_sources and turn.get("sources"):
            render_sources(turn["sources"])
        st.download_button(
            "Download answer",
            data=turn["answer"],
            file_name=f"answer-{idx + 1}.md",
            mime="text/markdown",
            key=f"dl_{idx}",
        )

# ── Input ────────────────────────────────────────────────────────────────────
prefill = st.session_state._prefill
if prefill:
    st.session_state._prefill = None

question = st.chat_input("Ask about regulations, finance, investments, compliance…") or prefill

if question:
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        status_box = st.empty()
        answer_box = st.empty()
        status_box.markdown(
            '<div class="status-pill"><span class="status-dot"></span>Starting…</div>',
            unsafe_allow_html=True,
        )

        history_payload = [
            {"question": t["question"], "answer": t["answer"]}
            for t in st.session_state.history[-4:]
        ] or None

        buf: list[str] = []
        errored = False
        for kind, content in stream_query(
            question, category, int(top_k), answer_mode, history_payload
        ):
            if kind == "status":
                status_box.markdown(
                    f'<div class="status-pill"><span class="status-dot"></span>'
                    f"{html.escape(content)}</div>",
                    unsafe_allow_html=True,
                )
            elif kind == "token":
                buf.append(content)
                answer_box.markdown("".join(buf) + " ▌")
            elif kind == "error":
                errored = True
                status_box.empty()
                answer_box.error(content)
                buf = [content]
                break

        raw_answer = "".join(buf)
        if not errored:
            status_box.empty()
            answer_box.markdown(raw_answer)

        meta = st.session_state.get("_stream_meta", {})
        sources = meta.get("sources", [])
        mode = meta.get("mode", "general")
        latency_ms = meta.get("latency_ms", 0)

        if not errored:
            label = mode_label(mode)
            if label:
                st.markdown(label, unsafe_allow_html=True)
            if latency_ms:
                st.markdown(
                    f'<div class="meta-row">Answered in {latency_ms / 1000:.1f}s</div>',
                    unsafe_allow_html=True,
                )
            if show_sources and sources:
                render_sources(sources)

    st.session_state.history.append(
        {
            "question": question,
            "answer": raw_answer,
            "sources": sources if not errored else [],
            "mode": mode if not errored else "error",
            "usage": meta.get("usage", {}),
            "latency_ms": latency_ms,
            "time": datetime.now().strftime("%I:%M %p"),
        }
    )
    st.rerun()
