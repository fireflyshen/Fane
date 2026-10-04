"""Legacy global config API; new code uses explicit Config values."""
from pathlib import Path
from typing import Any

from fane.config import Config
from fane.config.loader import DEFAULT_CONFIG_PATH, load_config
from fane.core.errors import ConfigError

_config: dict[str, Any] | None = None


def init_config(file: str | Path) -> dict[str, Any]:
    global _config
    _config = load_config(file)
    return _config


def get_config() -> dict[str, Any]:
    if _config is None:
        raise ConfigError("配置尚未加载")
    return _config


def get_config_model() -> Config:
    return Config.model_validate(get_config())
