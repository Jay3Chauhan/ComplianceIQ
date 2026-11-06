"""Small thread-safe TTL caches shared by retrieval and catalog lookups."""

import threading
import time
from collections import OrderedDict
from typing import Any, Hashable

_registry: list["TTLCache"] = []


class TTLCache:
    def __init__(self, ttl_seconds: int, max_items: int = 512) -> None:
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._data: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        _registry.append(self)

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if expires < time.monotonic():
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + self.ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_items:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


def clear_all_caches() -> None:
    for cache in _registry:
        cache.clear()
