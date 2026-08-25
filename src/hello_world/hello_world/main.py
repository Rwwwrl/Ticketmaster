import hashlib

from fastapi import FastAPI

from hello_world.schemas.response_schemas import HelloWorldResponseSchema
from hello_world.settings import settings

app = FastAPI(title="Hello World", version="0.1.0")


@app.get("/health-check")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness-check")
async def readiness_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/hello-world")
async def hello_world() -> HelloWorldResponseSchema:
    return HelloWorldResponseSchema(
        message="hello-world",
        environment=settings.environment,
        secret_fingerprint=hashlib.sha256(settings.secret.encode()).hexdigest()[:8],
    )
