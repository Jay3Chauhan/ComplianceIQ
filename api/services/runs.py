"""
In-process registry of answers being generated, keyed by conversation.

- One answer at a time per conversation (a second send gets 409 conversation_busy)
- POST /conversations/{id}/stop sets the cancel flag of the running answer

State lives in this process only: run a single API instance, or route a
conversation's requests to the same instance.
"""

import threading

from api.errors import APIError


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, threading.Event] = {}

    def start(self, conversation_id: str) -> threading.Event:
        with self._lock:
            if conversation_id in self._runs:
                raise APIError(
                    409, "conversation_busy",
                    "An answer is still being generated in this conversation. Stop it or wait for it to finish.",
                )
            cancel = threading.Event()
            self._runs[conversation_id] = cancel
            return cancel

    def finish(self, conversation_id: str) -> None:
        with self._lock:
            self._runs.pop(conversation_id, None)

    def cancel(self, conversation_id: str) -> bool:
        with self._lock:
            event = self._runs.get(conversation_id)
        if event is None:
            return False
        event.set()
        return True

    def is_active(self, conversation_id: str) -> bool:
        with self._lock:
            return conversation_id in self._runs

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()


runs = RunRegistry()
