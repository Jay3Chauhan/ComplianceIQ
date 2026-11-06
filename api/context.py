"""Per-request context (request id) available anywhere via contextvars."""

from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)
