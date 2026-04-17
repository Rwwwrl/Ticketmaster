import logging
import sys

from libs.common.enums import EnvironmentEnum, ServiceNameEnum
from libs.logging.enums import ProcessTypeEnum
from libs.logging.formatters import AWSJsonFormatter, DevFormatter
from libs.logging.settings import LoggingSettingsMixin
from libs.settings.utils import is_stand_env


def setup_logging(settings: LoggingSettingsMixin, service_name: ServiceNameEnum, process_type: ProcessTypeEnum) -> None:
    log_level = getattr(logging, settings.log_level.value.upper())

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(log_level)

    if is_stand_env(environment=settings.environment):
        handler.setFormatter(AWSJsonFormatter(service_name=service_name, process_type=process_type))
    elif settings.environment in {EnvironmentEnum.DEV, EnvironmentEnum.CICD}:
        handler.setFormatter(DevFormatter(service_name=service_name, process_type=process_type))
    else:
        raise ValueError(f"Unknown environment: {settings.environment}")

    root_logger.addHandler(handler)

    # NOTE @sosov: Suppressing noisy third-party loggers to WARNING+.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
