import pytest
from sqlalchemy import text
from ticketmaster.settings import Settings
from ticketmaster.utils import init_sqlmodel_engine


@pytest.mark.asyncio(loop_scope="session")
async def test_init_sqlmodel_engine_sets_statement_timeout_on_every_connection(settings: Settings) -> None:
    engine = init_sqlmodel_engine(db_url=settings.postgres_pooler_db_url)

    try:
        async with engine.connect() as connection:
            statement_timeout = (await connection.execute(statement=text("SHOW statement_timeout"))).scalar_one()
    finally:
        await engine.dispose()

    assert statement_timeout == "15s"
