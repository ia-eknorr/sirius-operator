from fastapi import FastAPI

app = FastAPI(title="sirius-platform-operator", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}
