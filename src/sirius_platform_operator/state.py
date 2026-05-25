"""Cross-thread state primitives shared between the kopf thread and uvicorn.

Two primitives live here:

1. ``RunCache`` - a thread-safe map from BenchmarkRun name to its latest known
   state. kopf handlers write to it from their event loop; FastAPI handlers
   read from it (synchronously, via ``run_in_threadpool`` or directly in sync
   routes). Both sides may run concurrently, so every read and write must
   pass through the lock.

2. ``build_event_queue`` - factory for a :class:`janus.Queue` used to
   stream events from the kopf thread to the FastAPI SSE handler. ``janus``
   is a dual-ended queue: synchronous ``.sync_q`` on the kopf side,
   asynchronous ``.async_q`` on the FastAPI side. Constructed lazily inside
   the FastAPI event loop (janus binds to whichever loop is current at
   construction).
"""

from __future__ import annotations

import threading
from typing import Any

import janus


class RunCache:
    """Thread-safe in-memory cache of BenchmarkRun state.

    The cache is a write-mostly-from-kopf, read-mostly-from-FastAPI structure.
    Values are plain dicts representing the latest observed status for a run.

    Design considerations for the implementation:

    * **Lock granularity:** a single ``threading.Lock`` for the whole map is
      fine at this scale (handfuls of concurrent runs, sub-millisecond
      critical sections). No need for per-key locks.
    * **Snapshot vs. live reference:** ``get`` should return a *copy* of the
      stored value so callers can't mutate cache state outside the lock.
      A shallow copy is sufficient because values are flat status dicts.
    * **Missing keys:** return ``None`` for absent keys (FastAPI route maps
      that to a 404 cleanly).
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> dict[str, Any] | None:
        """Return a snapshot of the cached state for ``name``, or None."""
        with self._lock:
            value = self._data.get(name)
            return value.copy() if value is not None else None

    def set(self, name: str, value: dict[str, Any]) -> None:
        """Replace the cached state for ``name`` with ``value``."""
        with self._lock:
            self._data[name] = value.copy()

    def delete(self, name: str) -> None:
        """Remove ``name`` from the cache. No-op if absent."""
        with self._lock:
            self._data.pop(name, None)


def build_event_queue() -> janus.Queue[dict[str, Any]]:
    """Construct a janus queue inside the current asyncio loop.

    Call this from the uvicorn (FastAPI) thread, e.g. in a startup handler,
    so ``janus`` binds to the FastAPI event loop. The kopf thread then
    receives a reference and writes via ``queue.sync_q.put(event)``;
    FastAPI SSE handlers read via ``await queue.async_q.get()``.
    """
    return janus.Queue()
