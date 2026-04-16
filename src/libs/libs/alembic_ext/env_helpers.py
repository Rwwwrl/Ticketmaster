from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, create_engine, pool


def run_alembic(settings_url: str, target_metadata: MetaData) -> None:
    # NOTE @sosov: Sync psycopg instead of async asyncpg — asyncio.run() hangs on
    # shutdown due to SSL transport cleanup bug in asyncpg.
    config = context.config

    if config.config_file_name is not None:
        fileConfig(config.config_file_name)

    sync_url = settings_url.replace("+asyncpg", "+psycopg").replace("?ssl=", "?sslmode=")
    engine = create_engine(url=sync_url, poolclass=pool.NullPool)

    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_server_default=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
