from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from libs.common.enums import EnvironmentEnum
from libs.settings import is_data_sensitive_env, is_stand_env


class SentrySettingsMixin(BaseSettings):
    environment: EnvironmentEnum
    sentry_dsn: str | None = None
    sentry_send_pii: bool | None = None
    sentry_traces_sample_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_sentry_settings(self) -> Self:
        errors: list[str] = []

        if is_stand_env(environment=self.environment):
            if self.sentry_dsn is None:
                errors.append("sentry_dsn is required for stand environments")
            if self.sentry_send_pii is None:
                errors.append("sentry_send_pii is required for stand environments")
            if self.sentry_traces_sample_rate is None:
                errors.append("sentry_traces_sample_rate is required for stand environments")
            if is_data_sensitive_env(environment=self.environment) and self.sentry_send_pii is True:
                errors.append("sentry_send_pii must be False in production")
        else:
            if self.sentry_dsn is not None:
                errors.append("sentry_dsn must not be set for non-stand environments")
            if self.sentry_send_pii is not None:
                errors.append("sentry_send_pii must not be set for non-stand environments")
            if self.sentry_traces_sample_rate is not None:
                errors.append("sentry_traces_sample_rate must not be set for non-stand environments")

        if errors:
            raise ValueError("; ".join(errors))

        return self
