"""Request-ID + access-log middleware (pure ASGI so streaming responses are untouched)."""

import re
import time
import uuid

from loguru import logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.context import set_request_id

_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        set_request_id(request_id)
        start = time.perf_counter()
        status_holder = {"status": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                elapsed = f"{(time.perf_counter() - start) * 1000:.0f}"
                message.setdefault("headers", [])
                message["headers"] += [
                    (b"x-request-id", request_id.encode()),
                    (b"x-response-time-ms", elapsed.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if not path.startswith(("/docs", "/openapi", "/redoc")):
                logger.info(
                    f"{scope.get('method')} {path} → {status_holder['status']} "
                    f"({(time.perf_counter() - start) * 1000:.0f}ms) rid={request_id}"
                )
