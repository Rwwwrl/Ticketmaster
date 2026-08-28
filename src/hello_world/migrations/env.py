import hello_world.models  # noqa: F401
from hello_world.settings import settings
from libs.alembic_ext.env_helpers import run_alembic
from libs.sqlmodel_ext import BaseSqlModel

run_alembic(settings_url=settings.postgres_db_url, target_metadata=BaseSqlModel.metadata)
