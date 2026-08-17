from fastapi import FastAPI
from libs.fastapi_ext.schemas.base_schemas import BaseResponseSchema

app = FastAPI(title="Hello World", version="0.1.0")


class HelloWorldResponseSchema(BaseResponseSchema):
    message: str


@app.get("/health-check")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness-check")
async def readiness_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/hello-world")
async def hello_world() -> HelloWorldResponseSchema:
    return HelloWorldResponseSchema(message="hello-world")
