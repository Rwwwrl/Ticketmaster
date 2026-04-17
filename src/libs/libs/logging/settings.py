from pydantic_settings import BaseSettings

from libs.common.enums import EnvironmentEnum
from libs.logging.enums import LogLevelEnum


class LoggingSettingsMixin(BaseSettings):
    environment: EnvironmentEnum
    log_level: LogLevelEnum = LogLevelEnum.INFO
