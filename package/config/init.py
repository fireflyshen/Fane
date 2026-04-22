import logging
from pathlib import Path

import yaml

_config = None


def init_config(file: str):
    global _config

    try:
        if file == "":
            file = Path.home() / ".flow" / "bflow.yaml"

        with open(file, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)

    except FileNotFoundError as fe:
        logging.error("找不到配置文件，请手动创建: %s", file)
        raise


def get_config():
    return _config
