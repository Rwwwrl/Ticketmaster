from importlib.metadata import version
from pathlib import Path
from typing import ClassVar

from libs.common.schemas.dto import DTO
from libs.logging.settings import LoggingSettingsMixin
from libs.redis_ext.settings import RedisSettingsMixin
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


class Settings(SentrySettingsMixin, LoggingSettingsMixin, PostgresSettingsMixin, RedisSettingsMixin, BaseAppSettings):
    model_config = SettingsConfigDict(extra="ignore", env_nested_delimiter="__")
    env_dev_yaml: ClassVar[Path] = BASE_DIR / "env.dev.yaml"

    # NOTE @sosov: Only needed for local dev. In prod, boto3 picks up the task role
    # credentials from ECS-injected env vars automatically, so the whole block can be None.
    aws_task_role: AWSTaskRoleSettings | None = None

    aws_region: str

    jwt_audience: str

    lambda_jwt_kms_key_arn: str
    lambda_jwt_issuer: str

    admin_jwt_kms_key_arn: str
    admin_jwt_issuer: str

    cognito_audience: str

    version: str


settings = Settings(version=version("ticketmaster"))
