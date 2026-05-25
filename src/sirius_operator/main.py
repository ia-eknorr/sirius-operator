"""Process entry point.

Runs kopf and uvicorn in the same process but on different threads, with
isolated asyncio event loops. kopf's docs explicitly warn against sharing
a loop with other asyncio code, so the two never touch each other's loops.

Shutdown chain:

1. SIGTERM / SIGINT arrives.
2. uvicorn's ``Server.serve()`` enters ``capture_signals()``, which saves
   our handlers and installs its own ``handle_exit`` for the duration of
   serve. While serve runs, **uvicorn's handler is the one that fires**:
   it sets ``server.should_exit = True``.
3. uvicorn's main loop notices the flag, drains in-flight requests, and
   returns from ``serve()``.
4. ``capture_signals()`` exits: restores our handlers, then calls
   ``signal.raise_signal()`` to re-deliver the signal we captured. **This
   is where our ``_handler`` actually runs** - on the re-raise, with our
   handler restored. Without our handler, the *default* SIGTERM disposition
   (terminate with exit -15) would fire here and kill the process before
   the kopf cleanup below can run.
5. Our ``_handler`` signals ``kopf_stop`` and returns.
6. ``main()`` regains control, joins the kopf thread with a bounded grace
   period, and exits cleanly.

The full path from SIGTERM to process exit must complete inside the pod's
``terminationGracePeriodSeconds`` (default 30s in Kubernetes). The
subprocess test in ``tests/unit/test_main.py`` enforces a 5-second budget.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import threading
from typing import TYPE_CHECKING

import kopf
import uvicorn

from sirius_operator.rest.app import app

if TYPE_CHECKING:
    from types import FrameType

log = logging.getLogger(__name__)


def kopf_thread(ready_flag: threading.Event, stop_flag: threading.Event) -> None:
    """Run kopf's operator on its own asyncio event loop.

    ``ready_flag`` is set once kopf has started its watchers. ``stop_flag``
    is a sync ``threading.Event`` that kopf observes directly via the
    ``stop_flag=`` argument; kopf gracefully terminates when the flag is
    set, from any thread.
    """
    asyncio.run(
        kopf.operator(
            ready_flag=ready_flag,
            stop_flag=stop_flag,
        )
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    kopf_ready = threading.Event()
    kopf_stop = threading.Event()

    thread = threading.Thread(
        target=kopf_thread,
        args=(kopf_ready, kopf_stop),
        name="kopf",
        daemon=True,
    )
    thread.start()

    config = uvicorn.Config(app=app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)

    _install_signal_handlers(kopf_stop=kopf_stop)

    asyncio.run(server.serve())

    log.info("uvicorn stopped; waiting for kopf thread to exit")
    kopf_stop.set()
    thread.join(timeout=5.0)
    if thread.is_alive():
        log.warning("kopf thread did not exit within 5s; process will exit anyway (daemon)")


def _install_signal_handlers(*, kopf_stop: threading.Event) -> None:
    """Install fallback SIGTERM/SIGINT handlers.

    These run on the re-raise inside uvicorn's ``capture_signals()`` finally
    block (see module docstring). Their job is to (a) be a non-default
    handler so the process doesn't exit with -15 when the captured signal
    is re-raised, and (b) signal the kopf thread to start unwinding in
    parallel with the main thread's cleanup.

    Signal handlers can interrupt arbitrary bytecode, so the body is
    restricted to flag operations and a single log line. Setting an
    already-set Event is a no-op, so a duplicate SIGTERM is harmless.
    """

    def _handler(signum: int, _frame: FrameType | None) -> None:
        log.warning("shutdown signal observed (sig=%s)", signum)
        kopf_stop.set()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
