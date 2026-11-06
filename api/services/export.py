"""Conversation export (Markdown for people, JSON for systems)."""

import re
from datetime import datetime, timezone

MODE_LABELS = {
    "regulatory": "Answered from loaded documents",
    "general": "General knowledge (no document citations)",
    "not_found": "Not covered by the loaded documents",
}
VERIFICATION_LABELS = {
    "verified": "verified against sources",
    "partially_verified": "partially verified",
    "unverified": "could not be verified",
}


def export_filename(conversation: dict, extension: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", conversation["title"].lower()).strip("-")[:60] or "conversation"
    return f"complianceiq-{slug}.{extension}"


def _when(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M UTC")
    except ValueError:
        return iso


def _source_line(s: dict) -> str:
    parts = [f"**[{s['id']}]** {s['doc_name']}"]
    if s.get("circular_id"):
        parts.append(s["circular_id"])
    if s.get("section"):
        parts.append(s["section"])
    parts.append(f"page {s['page_number']}")
    line = " · ".join(parts)
    return f"{line} ([source]({s['source_url']}))" if s.get("source_url") else line


def to_markdown(conversation: dict) -> str:
    lines = [
        f"# {conversation['title']}",
        "",
        f"_Exported from ComplianceIQ · {_when(datetime.now(timezone.utc).isoformat())} · "
        f"{conversation['message_count']} messages_",
        "",
        "> ComplianceIQ answers from the regulatory documents loaded at the time of each answer. "
        "Verify against the regulator's current circulars before relying on it.",
    ]
    for m in conversation["messages"]:
        lines += ["", "---", ""]
        if m["role"] == "user":
            lines += [f"### Question · {_when(m['created_at'])}", "", m["content"]]
            continue
        meta = [MODE_LABELS.get(m.get("mode") or "", "")]
        ver = (m.get("verification") or {}).get("status")
        if ver in VERIFICATION_LABELS:
            meta.append(VERIFICATION_LABELS[ver])
        if m["status"] == "stopped":
            meta.append("stopped before completion")
        elif m["status"] == "error":
            meta.append("failed")
        lines += ["### Answer", "", f"_{' · '.join(x for x in meta if x)}_", "", m["content"] or "_(no answer)_"]
        if m.get("sources"):
            lines += ["", "**Sources**", ""] + [f"- {_source_line(s)}" for s in m["sources"]]
    lines.append("")
    return "\n".join(lines)
