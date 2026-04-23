from fastapi import FastAPI

app = FastAPI(title="hello", version="0.1.0")


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "hello world"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"message": "pong"}
