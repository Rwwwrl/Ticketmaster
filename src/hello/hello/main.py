from fastapi import FastAPI

from hello.settings import settings

app = FastAPI(title="hello", version="0.2.0")


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "hello world"}


@app.get("/health-check")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"message": "pong"}


@app.get("/config-check")
async def config_check() -> dict[str, str]:
    return {"hello": settings.hello, "log_level": settings.log_level}
