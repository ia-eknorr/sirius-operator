# sirius-platform-operator

Kubernetes operator that drives `BenchmarkRun` resources through their lifecycle on the sirius benchmark platform. One container, one process: kopf watches CRDs in a dedicated thread, FastAPI serves a REST surface on the main thread, and both share an in-memory run cache.

## Quick start

```bash
pip install -e .[dev]
python -m sirius_platform_operator
# in another terminal:
curl http://localhost:8080/healthz
```

Send `SIGTERM` (`kill -TERM <pid>` or `Ctrl-C`) to shut down. The kopf thread and uvicorn server should both stop within 5 seconds.

## Layout

```
src/sirius_platform_operator/
  __init__.py
  __main__.py       # python -m sirius_platform_operator
  main.py           # process entry point; coordinates kopf thread + uvicorn
  state.py          # RunCache + janus.Queue bridge between threads
  rest/
    app.py          # FastAPI app
```

## Context

This repo is the operator chapter of the sirius-platform venture. See `~/ventures/2026-05-24-sirius-platform/chapters/operator-scaffold/` for the research, design, and phased plan.
