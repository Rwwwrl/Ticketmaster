from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from libs.sqlmodel_ext import BaseSqlModel, Session
from libs.sqlmodel_ext.settings import PostgresSettingsMixin

_TEST_DB_NAME = "test"


@pytest_asyncio.fixture(scope="session")
async def sqlmodel_engine(settings: PostgresSettingsMixin) -> AsyncGenerator[AsyncEngine]:
    admin_url = make_url(settings.postgres_db_url).set(database="postgres")
    test_url = make_url(settings.postgres_db_url).set(database=_TEST_DB_NAME)

    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB_NAME}"))
        await conn.execute(text(f"CREATE DATABASE {_TEST_DB_NAME}"))
    await admin_engine.dispose()

    engine = create_async_engine(test_url)
    Session.configure(bind=engine)

    async with engine.begin() as conn:
        await conn.run_sync(BaseSqlModel.metadata.create_all)

    yield engine

    await engine.dispose()

    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB_NAME}"))
    await admin_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clear_sqlmodel_tables(request: pytest.FixtureRequest) -> AsyncGenerator[None]:
    yield

    if sqlmodel_engine.__name__ not in request.fixturenames:
        return

    try:
        tables: list[type[BaseSqlModel]] = request.getfixturevalue("autocleared_sqlmodel_tables")
    except pytest.FixtureLookupError:
        return

    async with Session() as session, session.begin():
        for table in tables:
            await session.execute(text(f'TRUNCATE TABLE "{table.__tablename__}" CASCADE'))
