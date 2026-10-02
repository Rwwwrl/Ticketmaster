from pydantic_settings import BaseSettings


class PostgresSettingsMixin(BaseSettings):
    postgres_direct_db_url: str
    postgres_pooler_db_url: str
