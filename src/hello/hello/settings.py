from pathlib import Path
from typing import ClassVar

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    _env_dev_yaml: ClassVar[Path] = _BASE_DIR / "env.dev.yaml"

    hello: str
    log_level: str

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        if cls._env_dev_yaml.exists():
            sources.append(YamlConfigSettingsSource(settings_cls=settings_cls, yaml_file=cls._env_dev_yaml))
        return tuple(sources)


settings = Settings()
