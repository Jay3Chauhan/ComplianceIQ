"""
Auth and rate limiting dependencies.

- X-API-Key   server-to-server key (e.g. the Next.js backend). Required whenever
              API_KEYS is set; in production the API refuses to run open.
- X-User-Id   end-user identifier forwarded by the trusted caller; scopes
              conversations and feedback. Defaults to "anonymous".
- X-Admin-Key required for admin endpoints.
"""

import hmac
import re
import threading
import time
from collections import defaultdict, deque

from fastapi import Header, Request

from api.errors import APIError
from config import settings

USER_ID_RE = re.compile(r"^[A-Za-z0-9_.@:+-]{1,128}$")


def _matches(provided: str | None, valid: list[str]) -> bool:
    return bool(provided) and any(hmac.compare_digest(provided, k) for k in valid)


async def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    keys = settings.api_key_list
    if not keys:
        if settings.is_production:
            raise APIError(503, "auth_not_configured", "API_KEYS must be configured in production.")
        return "dev"
    if not _matches(x_api_key, keys):
        raise APIError(401, "unauthorized", "Missing or invalid X-API-Key header.")
    return x_api_key or ""


async def get_user_id(x_user_id: str | None = Header(default=None)) -> str:
    if not x_user_id:
        return "anonymous"
    if not USER_ID_RE.match(x_user_id):
        raise APIError(400, "invalid_user_id", "X-User-Id may contain letters, digits and . _ @ : + - (max 128).")
    return x_user_id


async def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not settings.admin_api_key:
        if settings.is_production:
            raise APIError(503, "admin_disabled", "Admin endpoints are disabled: set ADMIN_API_KEY.")
        return
    if not _matches(x_admin_key, [settings.admin_api_key]):
        raise APIError(401, "unauthorized", "Missing or invalid X-Admin-Key header.")


class SlidingWindowLimiter:
    """In-memory per-key limiter. Use Redis for multi-instance deployments."""

    def __init__(self, limit: int, window_s: float = 60.0) -> None:
        self.limit = limit
        self.window = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(1, int(self.window - (now - hits[0])) + 1)
            hits.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


chat_limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)


async def rate_limit_chat(
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    if settings.rate_limit_per_minute <= 0:
        return
    caller = x_api_key[-8:] if x_api_key else (request.client.host if request.client else "unknown")
    allowed, retry_after = chat_limiter.check(f"{caller}:{x_user_id or 'anonymous'}")
    if not allowed:
        raise APIError(
            429, "rate_limited",
            f"Too many questions. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )
