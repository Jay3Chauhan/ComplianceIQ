"""RAG pipeline behaviour with retrieval and the LLM mocked out."""

import pytest

from llm.groq_client import Completion
from llm.prompt_templates import NOT_FOUND_ANSWER
from rag import pipeline
from rag.pipeline import RAGRequest
from retrieval.retriever import RetrievalResult

GOOD_ANSWER = "High risk customers must be updated at least once every two years [1]."


def _retrieval(chunks: list[dict], grounded: bool) -> RetrievalResult:
    return RetrievalResult(query="q", search_query="q", chunks=chunks if grounded else [], is_grounded=grounded,
                           gate_score=0.9 if grounded else 0.01, strategy="hybrid", reranked=True,
                           candidates=len(chunks), timings={"search_ms": 5})


@pytest.fixture
def fake_llm(monkeypatch):
    calls: list[list[dict]] = []
    replies: list[str] = []

    def complete(messages, **kwargs):
        calls.append(messages)
        return Completion(replies.pop(0) if replies else GOOD_ANSWER, "fake-model", {"total_tokens": 10})

    def stream(messages, **kwargs):
        calls.append(messages)
        text = replies.pop(0) if replies else GOOD_ANSWER
        yield {"type": "model", "model": "fake-model"}
        for word in text.split(" "):
            yield {"type": "token", "content": word + " "}

    monkeypatch.setattr(pipeline.groq_client, "complete", complete)
    monkeypatch.setattr(pipeline.groq_client, "stream", stream)
    return calls, replies


def _patch_retrieval(monkeypatch, chunks, grounded):
    monkeypatch.setattr(pipeline, "retrieve", lambda *a, **k: _retrieval(chunks, grounded))


def test_grounded_answer_is_regulatory_and_verified(monkeypatch, fake_llm, sample_chunks) -> None:
    _patch_retrieval(monkeypatch, sample_chunks, True)
    res = pipeline.answer(RAGRequest(question="How often is periodic KYC updation needed?"))
    assert res.mode == "regulatory"
    assert res.sources[0]["id"] == 1 and res.sources[0]["section"]
    assert res.verification["status"] == "verified"
    assert res.confidence == "high"
    system_prompt = fake_llm[0][0][0]["content"]
    assert "ONLY from the numbered source passages" in system_prompt


def test_regulatory_mode_without_grounding_refuses(monkeypatch, fake_llm, sample_chunks) -> None:
    _patch_retrieval(monkeypatch, sample_chunks, False)
    res = pipeline.answer(RAGRequest(question="What is the GST rate on restaurants?", answer_mode="regulatory"))
    assert res.mode == "not_found"
    assert res.answer == NOT_FOUND_ANSWER
    assert fake_llm[0] == []  # no LLM call


def test_auto_mode_without_grounding_falls_back_to_general(monkeypatch, fake_llm, sample_chunks) -> None:
    _patch_retrieval(monkeypatch, sample_chunks, False)
    fake_llm[1].append("A SIP is a way to invest a fixed amount regularly in a mutual fund.")
    res = pipeline.answer(RAGRequest(question="What is a SIP?"))
    assert res.mode == "general"
    assert res.sources == []
    assert res.confidence == "low"
    assert "GENERAL KNOWLEDGE" in fake_llm[0][0][0]["content"]


REFUSAL = "The loaded documents do not contain enough information to answer this question."


def test_model_refusal_becomes_not_found(monkeypatch, fake_llm, sample_chunks) -> None:
    _patch_retrieval(monkeypatch, sample_chunks, True)
    fake_llm[1].append(REFUSAL)
    res = pipeline.answer(RAGRequest(question="What is the penalty for late updation?", answer_mode="regulatory"))
    assert res.mode == "not_found"
    assert res.sources == []


def test_auto_mode_refusal_falls_back_to_general(monkeypatch, fake_llm, sample_chunks) -> None:
    _patch_retrieval(monkeypatch, sample_chunks, True)
    fake_llm[1].extend([REFUSAL, "A SIP invests a fixed amount at regular intervals."])
    res = pipeline.answer(RAGRequest(question="What is a SIP?"))
    assert res.mode == "general" and res.confidence == "low"
    assert res.sources == [] and res.verification is None
    assert res.answer.startswith("A SIP")
    assert "GENERAL KNOWLEDGE" in fake_llm[0][1][0]["content"]


def test_stream_auto_refusal_resets_text_then_answers_generally(monkeypatch, fake_llm, sample_chunks) -> None:
    _patch_retrieval(monkeypatch, sample_chunks, True)
    fake_llm[1].extend([REFUSAL, "A SIP invests a fixed amount at regular intervals."])
    events = list(pipeline.stream(RAGRequest(question="What is a SIP?")))
    reset = next(e for e in events if e["type"] == "revision")
    assert reset == {"type": "revision", "answer": "", "mode": "general", "sources": [],
                     "reason": "general_fallback"}
    after = events[events.index(reset):]
    assert "".join(e["content"] for e in after if e["type"] == "token").startswith("A SIP")
    assert not any(e["type"] == "verification" for e in events)
    done = events[-1]
    assert done["mode"] == "general" and done["answer"].startswith("A SIP") and done["confidence"] == "low"


def test_cited_partial_answer_is_not_treated_as_refusal(monkeypatch, fake_llm, sample_chunks) -> None:
    _patch_retrieval(monkeypatch, sample_chunks, True)
    fake_llm[1].append(
        GOOD_ANSWER + "\n\nThe loaded documents do not contain enough information about penalties."
    )
    res = pipeline.answer(RAGRequest(question="How often is periodic KYC updation needed?"))
    assert res.mode == "regulatory"
    assert res.sources


def test_clean_text_normalizes_model_typography() -> None:
    raw = "risk\u2011management at 10\u202f% 【2】 and [3†L4-L9]"
    assert pipeline.groq_client.clean_text(raw) == "risk-management at 10 % [2] and [3]"


def test_unverified_answer_is_repaired(monkeypatch, fake_llm, sample_chunks) -> None:
    _patch_retrieval(monkeypatch, sample_chunks, True)
    fake_llm[1].extend([
        "High risk customers must be updated every 3 years [1]. Banks may skip PAN checks for 7 days [4].",
        GOOD_ANSWER,
    ])
    res = pipeline.answer(RAGRequest(question="How often is periodic KYC updation needed?"))
    assert res.revised
    assert res.answer == GOOD_ANSWER
    assert res.verification["status"] == "verified"
    repair_prompt = fake_llm[0][1][1]["content"]
    assert "does not exist" in repair_prompt and "figure 3" in repair_prompt


def test_stream_event_order(monkeypatch, fake_llm, sample_chunks) -> None:
    _patch_retrieval(monkeypatch, sample_chunks, True)
    events = list(pipeline.stream(RAGRequest(question="How often is periodic KYC updation needed?")))
    types = [e["type"] for e in events]
    assert types[0] == "status" and events[0]["stage"] == "searching"
    assert types.index("retrieval") < types.index("token") < types.index("verification") < types.index("done")
    done = events[-1]
    assert done["type"] == "done" and done["mode"] == "regulatory" and done["answer"] == GOOD_ANSWER


def test_stream_not_found_has_no_llm_call(monkeypatch, fake_llm, sample_chunks) -> None:
    _patch_retrieval(monkeypatch, sample_chunks, False)
    events = list(pipeline.stream(RAGRequest(question="Who won the 2011 world cup?", answer_mode="regulatory")))
    assert [e["type"] for e in events] == ["status", "retrieval", "token", "done"]
    assert events[1]["mode"] == "not_found"
    assert fake_llm[0] == []
