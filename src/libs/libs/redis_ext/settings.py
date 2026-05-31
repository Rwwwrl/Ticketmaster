from pydantic_settings import BaseSettings


class RedisSettingsMixin(BaseSettings):
    redis_url: str
