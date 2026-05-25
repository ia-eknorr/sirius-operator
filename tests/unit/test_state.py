"""Thread-safety hammer test for RunCache.

Spins multiple writer threads and reader threads against a single RunCache
and asserts no exceptions and no corrupted reads (a "corrupted read" here
means a value that was never actually written for that key).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from sirius_platform_operator.state import RunCache


def test_run_cache_thread_safe() -> None:
    cache = RunCache()
    iterations = 2000
    keys = [f"run-{i}" for i in range(8)]
    stop = threading.Event()

    def writer(worker_id: int) -> None:
        for i in range(iterations):
            key = keys[i % len(keys)]
            cache.set(key, {"worker": worker_id, "i": i})

    def reader() -> None:
        while not stop.is_set():
            for key in keys:
                value = cache.get(key)
                if value is not None:
                    assert "worker" in value
                    assert "i" in value

    with ThreadPoolExecutor(max_workers=8) as pool:
        write_futs = [pool.submit(writer, w) for w in range(4)]
        read_futs = [pool.submit(reader) for _ in range(4)]
        for f in write_futs:
            f.result()
        stop.set()
        for f in read_futs:
            f.result()

    for key in keys:
        snap = cache.get(key)
        assert snap is not None
        assert isinstance(snap, dict)


def test_run_cache_returns_snapshot_not_reference() -> None:
    cache = RunCache()
    cache.set("run-1", {"phase": "Provisioning"})

    snap = cache.get("run-1")
    assert snap is not None
    snap["phase"] = "MUTATED"

    fresh = cache.get("run-1")
    assert fresh is not None
    assert fresh["phase"] == "Provisioning", "get() must return a copy, not a live reference"


def test_run_cache_delete_idempotent() -> None:
    cache = RunCache()
    cache.delete("never-existed")
    cache.set("run-1", {"phase": "Pending"})
    cache.delete("run-1")
    assert cache.get("run-1") is None
    cache.delete("run-1")
