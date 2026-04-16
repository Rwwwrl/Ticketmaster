from pathlib import Path
from typing import ClassVar

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from libs.common.enums import EnvironmentEnum


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    env_dev_yaml: ClassVar[Path]

    environment: EnvironmentEnum

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # NOTE @sosov: YAML source is conditional on file existence. In production, config is
        # injected via env vars; in local dev, env.dev.yaml provides values.
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        if cls.env_dev_yaml.exists():
            sources.append(YamlConfigSettingsSource(settings_cls=settings_cls, yaml_file=cls.env_dev_yaml))
        return tuple(sources)
