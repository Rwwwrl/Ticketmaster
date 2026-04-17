import ticketmaster.models  # noqa: F401
from libs.alembic_ext.env_helpers import run_alembic
from libs.sqlmodel_ext import BaseSqlModel
from ticketmaster.settings import settings

run_alembic(settings_url=settings.postgres_db_url, target_metadata=BaseSqlModel.metadata)
