import hashlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from libs.sqlmodel_ext import Session
from libs.sqlmodel_ext.utils import health_check as postgres_health_check
from sqlmodel import func, select

from hello_world.models import Visit
from hello_world.schemas.response_schemas import HelloWorldResponseSchema
from hello_world.settings import settings
from hello_world.utils import init_sqlmodel_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    engine = init_sqlmodel_engine(db_url=settings.postgres_db_url)
    Session.configure(bind=engine)
    app.state.sqlmodel_engine = engine

    yield

    await engine.dispose()


app = FastAPI(title="Hello World", version="0.1.0", lifespan=lifespan)


@app.get("/health-check")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness-check")
async def readiness_check() -> dict[str, str]:
    await postgres_health_check()
    return {"status": "ok"}


@app.get("/hello-world")
async def hello_world() -> HelloWorldResponseSchema:
    async with Session() as session, session.begin():
        session.add(Visit())
        visit_count = (await session.exec(select(func.count()).select_from(Visit))).one()

    return HelloWorldResponseSchema(
        message="hello-world",
        environment=settings.environment,
        secret_fingerprint=hashlib.sha256(settings.secret.encode()).hexdigest()[:8],
        visit_count=visit_count,
    )
