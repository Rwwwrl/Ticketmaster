from pathlib import Path
from typing import ClassVar

from libs.common.schemas.dto import DTO
from libs.logging.settings import LoggingSettingsMixin
from libs.sentry_ext import SentrySettingsMixin
from libs.settings import BaseAppSettings
from libs.sqlmodel_ext.settings import PostgresSettingsMixin
from pydantic_settings import SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class AWSTaskRoleSettings(DTO):
    region: str
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None


class Settings(SentrySettingsMixin, LoggingSettingsMixin, PostgresSettingsMixin, BaseAppSettings):
    model_config = SettingsConfigDict(extra="ignore", env_nested_delimiter="__")
    env_dev_yaml: ClassVar[Path] = BASE_DIR / "env.dev.yaml"

    aws_task_role: AWSTaskRoleSettings
    lambda_jwt_kms_key_arn: str
    lambda_jwt_audience: str
    lambda_jwt_issuer: str


settings = Settings()
