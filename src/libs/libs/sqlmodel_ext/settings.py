from pydantic_settings import BaseSettings


class PostgresSettingsMixin(BaseSettings):
    postgres_db_url: str
