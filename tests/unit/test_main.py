"""Subprocess smoke test for the binary's threading + shutdown behavior.

Launches ``python -m sirius_platform_operator`` as a subprocess, waits for
``/healthz`` to come up, sends SIGTERM, and asserts the process exits with
code 0 within the 5-second deadline. This validates the kopf-thread +
uvicorn-main-thread bridge end-to-end without needing a real cluster.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

PORT = 8080


@contextmanager
def _operator_process() -> Iterator[subprocess.Popen[bytes]]:
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "sirius_platform_operator"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)


def _wait_for_healthz(deadline_s: float = 10.0) -> None:
    start = time.monotonic()
    last_err: Exception | None = None
    while time.monotonic() - start < deadline_s:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/healthz", timeout=1.0
            ) as resp:
                assert resp.status == 200
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last_err = exc
            time.sleep(0.2)
    raise AssertionError(f"healthz never came up: {last_err!r}")


def test_kopf_thread_starts_and_stops() -> None:
    with _operator_process() as proc:
        _wait_for_healthz()
        proc.send_signal(signal.SIGTERM)
        try:
            code = proc.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            output = proc.stdout.read().decode() if proc.stdout else ""
            raise AssertionError(
                f"operator did not exit within 5s of SIGTERM. Tail of output:\n{output[-2000:]}"
            ) from exc
        assert code == 0, f"non-zero exit code {code}"
