import logging
from pathlib import Path
from typing import Any, cast

import yaml

from package.config.config import Config
from package.errors import ConfigError

DEFAULT_CONFIG_PATH = Path.home() / ".flow" / "config.yaml"
_config: dict[str, Any] | None = None


def load_config(file: str | Path) -> dict[str, Any]:
    config_path = Path(file) if file else DEFAULT_CONFIG_PATH

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        if config is None:
            raise ConfigError(f"配置文件为空: {config_path}")
        if not isinstance(config, dict):
            raise ConfigError(f"配置文件格式错误，应为 YAML 对象: {config_path}")
        return cast(dict[str, Any], config)
    except FileNotFoundError as fe:
        logging.error("找不到配置文件，请手动创建: %s", config_path)
        raise ConfigError(f"找不到配置文件，请手动创建: {config_path}") from fe
    except yaml.YAMLError as ye:
        logging.error("配置文件 YAML 格式错误: %s", config_path)
        raise ConfigError(f"配置文件 YAML 格式错误: {config_path}") from ye


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
