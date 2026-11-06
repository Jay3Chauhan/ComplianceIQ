"""Data-access functions. All return plain dicts so API layers stay ORM-free."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select

from db.models import Conversation, Feedback, IngestJob, Message, QueryLog, utcnow
from db.session import session_scope

TITLE_MAX = 80


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _title_from(question: str) -> str:
    q = " ".join(question.split())
    return q if len(q) <= TITLE_MAX else q[: TITLE_MAX - 1].rsplit(" ", 1)[0] + "…"


def conversation_dict(c: Conversation) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "category": c.category,
        "answer_mode": c.answer_mode,
        "pinned": c.pinned,
        "archived": c.archived,
        "message_count": c.message_count,
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
    }


def message_dict(m: Message, feedback: Feedback | None = None) -> dict:
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "role": m.role,
        "content": m.content,
        "status": m.status,
        "mode": m.mode,
        "sources": m.sources or [],
        "verification": m.verification,
        "confidence": m.confidence,
        "revised": m.revised,
        "standalone_question": m.standalone_question,
        "model": m.model,
        "latency_ms": m.latency_ms,
        "created_at": _iso(m.created_at),
        "feedback": {"rating": feedback.rating, "reasons": feedback.reasons or [], "comment": feedback.comment}
        if feedback else None,
    }


# ── Conversations ────────────────────────────────────────────────────────────

def create_conversation(user_id: str, title: str | None = None, category: str = "ALL",
                        answer_mode: str = "auto") -> dict:
    with session_scope() as s:
        c = Conversation(user_id=user_id, title=title or "New conversation",
                         category=category, answer_mode=answer_mode)
        s.add(c)
        s.flush()
        return conversation_dict(c)


def list_conversations(user_id: str, limit: int = 30, offset: int = 0, q: str | None = None,
                       archived: bool = False) -> tuple[list[dict], int]:
    with session_scope() as s:
        stmt = select(Conversation).where(Conversation.user_id == user_id, Conversation.archived == archived)
        if q:
            like = f"%{q.strip()}%"
            matching = select(Message.conversation_id).where(Message.content.ilike(like))
            stmt = stmt.where(or_(Conversation.title.ilike(like), Conversation.id.in_(matching)))
        total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = s.scalars(
            stmt.order_by(Conversation.pinned.desc(), Conversation.updated_at.desc()).limit(limit).offset(offset)
        ).all()
        return [conversation_dict(c) for c in rows], total


def _owned_conversation(s, user_id: str, conversation_id: str) -> Conversation | None:
    c = s.get(Conversation, conversation_id)
    return c if c and c.user_id == user_id else None


def get_conversation(user_id: str, conversation_id: str, with_messages: bool = True) -> dict | None:
    with session_scope() as s:
        c = _owned_conversation(s, user_id, conversation_id)
        if not c:
            return None
        data = conversation_dict(c)
        if with_messages:
            fb = {
                f.message_id: f
                for f in s.scalars(
                    select(Feedback).join(Message).where(
                        Message.conversation_id == c.id, Feedback.user_id == user_id
                    )
                )
            }
            data["messages"] = [message_dict(m, fb.get(m.id)) for m in c.messages]
        return data


def update_conversation(user_id: str, conversation_id: str, **fields) -> dict | None:
    allowed = {"title", "pinned", "archived", "category", "answer_mode"}
    with session_scope() as s:
        c = _owned_conversation(s, user_id, conversation_id)
        if not c:
            return None
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(c, key, value)
        c.updated_at = utcnow()
        return conversation_dict(c)


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    with session_scope() as s:
        c = _owned_conversation(s, user_id, conversation_id)
        if not c:
            return False
        s.delete(c)
        return True


def delete_all_conversations(user_id: str) -> int:
    with session_scope() as s:
        rows = s.scalars(select(Conversation).where(Conversation.user_id == user_id)).all()
        for c in rows:
            s.delete(c)
        return len(rows)


def conversation_exists(user_id: str, conversation_id: str) -> bool:
    with session_scope() as s:
        return _owned_conversation(s, user_id, conversation_id) is not None


# ── Messages ─────────────────────────────────────────────────────────────────

def add_message(conversation_id: str, role: str, content: str, **fields) -> dict:
    with session_scope() as s:
        c = s.get(Conversation, conversation_id)
        if c is None:
            raise ValueError("conversation not found")
        m = Message(conversation_id=conversation_id, role=role, content=content, **fields)
        s.add(m)
        if role == "user" and c.message_count == 0 and c.title == "New conversation":
            c.title = _title_from(content)
        c.message_count += 1
        c.updated_at = utcnow()
        s.flush()
        return message_dict(m)


def history_for_rag(conversation_id: str, turns: int = 3) -> list[dict]:
    """Last N (question, answer) pairs, oldest first."""
    with session_scope() as s:
        msgs = s.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.status == "complete")
            .order_by(Message.created_at.desc())
            .limit(turns * 2)
        ).all()
    msgs = list(reversed(msgs))
    history: list[dict] = []
    pending: str | None = None
    for m in msgs:
        if m.role == "user":
            pending = m.content
        elif m.role == "assistant" and pending is not None:
            history.append({"question": pending, "answer": m.content})
            pending = None
    return history[-turns:]


def get_message(user_id: str, message_id: str) -> dict | None:
    with session_scope() as s:
        m = s.get(Message, message_id)
        if not m or m.conversation.user_id != user_id:
            return None
        return message_dict(m)


# ── Feedback ─────────────────────────────────────────────────────────────────

def upsert_feedback(user_id: str, message_id: str, rating: int, reasons: list[str] | None,
                    comment: str | None) -> dict | None:
    with session_scope() as s:
        m = s.get(Message, message_id)
        if not m or m.conversation.user_id != user_id or m.role != "assistant":
            return None
        fb = s.scalar(select(Feedback).where(Feedback.message_id == message_id, Feedback.user_id == user_id))
        if fb is None:
            fb = Feedback(message_id=message_id, user_id=user_id, rating=rating)
            s.add(fb)
        fb.rating, fb.reasons, fb.comment = rating, reasons, comment
        fb.created_at = utcnow()
        s.flush()
        return {"message_id": message_id, "rating": fb.rating, "reasons": fb.reasons or [],
                "comment": fb.comment, "created_at": _iso(fb.created_at)}


def delete_feedback(user_id: str, message_id: str) -> bool:
    with session_scope() as s:
        fb = s.scalar(select(Feedback).where(Feedback.message_id == message_id, Feedback.user_id == user_id))
        if not fb:
            return False
        s.delete(fb)
        return True


# ── Query logs / analytics ───────────────────────────────────────────────────

def log_query(**fields) -> None:
    with session_scope() as s:
        s.add(QueryLog(**fields))


def usage_stats(days: int = 7) -> dict:
    since = utcnow() - timedelta(days=days)
    with session_scope() as s:
        logs = s.scalars(select(QueryLog).where(QueryLog.created_at >= since)).all()
        fb_rows = s.execute(
            select(Feedback.rating, func.count()).where(Feedback.created_at >= since).group_by(Feedback.rating)
        ).all()
        recent_unanswered = s.scalars(
            select(QueryLog.question)
            .where(QueryLog.created_at >= since, QueryLog.mode == "not_found")
            .order_by(QueryLog.created_at.desc())
            .limit(10)
        ).all()

    total = len(logs)
    latencies = sorted(l.latency_ms for l in logs if l.latency_ms is not None)
    by_mode: dict[str, int] = {}
    by_verification: dict[str, int] = {}
    for l in logs:
        by_mode[l.mode or "error"] = by_mode.get(l.mode or "error", 0) + 1
        if l.verification_status:
            by_verification[l.verification_status] = by_verification.get(l.verification_status, 0) + 1
    feedback = {("positive" if r > 0 else "negative"): n for r, n in fb_rows}

    def pct(p: float) -> int | None:
        return latencies[min(len(latencies) - 1, int(p * len(latencies)))] if latencies else None

    return {
        "window_days": days,
        "total_queries": total,
        "by_mode": by_mode,
        "grounded_rate": round(sum(1 for l in logs if l.grounded) / total, 3) if total else None,
        "verification": by_verification,
        "revised_answers": sum(1 for l in logs if l.revised),
        "errors": sum(1 for l in logs if l.error),
        "latency_ms": {"p50": pct(0.5), "p95": pct(0.95)},
        "feedback": {"positive": feedback.get("positive", 0), "negative": feedback.get("negative", 0)},
        "recent_unanswered": list(recent_unanswered),
    }


# ── Ingest jobs ──────────────────────────────────────────────────────────────

def job_dict(j: IngestJob) -> dict:
    return {
        "id": j.id, "doc_id": j.doc_id, "filename": j.filename, "status": j.status, "stage": j.stage,
        "progress": round(j.progress, 3), "result": j.result, "error": j.error,
        "created_at": _iso(j.created_at), "started_at": _iso(j.started_at), "finished_at": _iso(j.finished_at),
    }


def create_job(doc_id: str, filename: str) -> dict:
    with session_scope() as s:
        j = IngestJob(doc_id=doc_id, filename=filename)
        s.add(j)
        s.flush()
        return job_dict(j)


def update_job(job_id: str, **fields) -> None:
    with session_scope() as s:
        j = s.get(IngestJob, job_id)
        if not j:
            return
        for k, v in fields.items():
            setattr(j, k, v)


def get_job(job_id: str) -> dict | None:
    with session_scope() as s:
        j = s.get(IngestJob, job_id)
        return job_dict(j) if j else None


def list_jobs(limit: int = 20) -> list[dict]:
    with session_scope() as s:
        return [job_dict(j) for j in s.scalars(select(IngestJob).order_by(IngestJob.created_at.desc()).limit(limit))]


def active_job_for(doc_id: str) -> dict | None:
    with session_scope() as s:
        j = s.scalar(select(IngestJob).where(IngestJob.doc_id == doc_id, IngestJob.status.in_(("queued", "running"))))
        return job_dict(j) if j else None
