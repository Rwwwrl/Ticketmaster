import os

from libs.alembic_ext.env_helpers import create_migration_engine
from sqlalchemy import text


def test_create_migration_engine_sets_transaction_timeout_and_leaves_statement_timeout_off() -> None:
    engine = create_migration_engine(settings_url=os.environ["POSTGRES_DIRECT_DB_URL"])

    try:
        with engine.connect() as connection:
            transaction_timeout = connection.execute(statement=text("SHOW transaction_timeout")).scalar_one()
            statement_timeout = connection.execute(statement=text("SHOW statement_timeout")).scalar_one()
    finally:
        engine.dispose()

    assert transaction_timeout == "75s"
    assert statement_timeout == "0"
