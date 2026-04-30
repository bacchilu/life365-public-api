from fastapi import FastAPI

app: FastAPI = FastAPI(title="Life365 Public API", version="0.1.0")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
