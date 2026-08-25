from pathlib import Path
from typing import ClassVar

from libs.settings import BaseAppSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseAppSettings):
    env_dev_yaml: ClassVar[Path] = BASE_DIR / "env.dev.yaml"


settings = Settings()
