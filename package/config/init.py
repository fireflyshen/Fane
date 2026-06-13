import logging
from pathlib import Path

import yaml

from package.errors import ConfigError

_config = None


def init_config(file: str):
    global _config

    try:
        if file == "":
            file = Path.home() / ".flow" / "bflow.yaml"

        with open(file, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)
        if _config is None:
            raise ConfigError(f"配置文件为空: {file}")

    except FileNotFoundError as fe:
        logging.error("找不到配置文件，请手动创建: %s", file)
        raise ConfigError(f"找不到配置文件，请手动创建: {file}") from fe
    except yaml.YAMLError as ye:
        logging.error("配置文件 YAML 格式错误: %s", file)
        raise ConfigError(f"配置文件 YAML 格式错误: {file}") from ye


def get_config():
    return _config
