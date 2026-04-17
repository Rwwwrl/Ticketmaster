from pathlib import Path
from typing import ClassVar

from libs.logging.settings import LoggingSettingsMixin
from libs.sentry_ext import SentrySettingsMixin
from libs.settings import BaseAppSettings
from libs.sqlmodel_ext.settings import PostgresSettingsMixin

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(SentrySettingsMixin, LoggingSettingsMixin, PostgresSettingsMixin, BaseAppSettings):
    env_dev_yaml: ClassVar[Path] = BASE_DIR / "env.dev.yaml"


settings = Settings()
