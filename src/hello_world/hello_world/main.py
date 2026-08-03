from fastapi import FastAPI

app = FastAPI(title="Hello World", version="0.1.0")


@app.get("/health-check")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness-check")
async def readiness_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/hello-world")
async def hello_world() -> dict[str, str]:
    return {"message": "hello-world"}
