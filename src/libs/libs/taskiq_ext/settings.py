from pydantic_settings import BaseSettings


class TaskIQSettingsMixin(BaseSettings):
    rabbitmq_url: str
