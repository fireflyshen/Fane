import logging
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from fane.shared.config.models import Config
from fane.shared.errors import ConfigError

DEFAULT_CONFIG_PATH = Path.home() / ".flow" / "config.yaml"


def load_config(file: str | Path) -> dict[str, Any]:
    config_path = Path(file).expanduser() if file else DEFAULT_CONFIG_PATH

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        if config is None:
            raise ConfigError(f"配置文件为空: {config_path}")
        if not isinstance(config, dict):
            raise ConfigError(f"配置文件格式错误，应为 YAML 对象: {config_path}")
        template = config.get("template-file")
        if isinstance(template, str) and template:
            path = Path(template).expanduser()
            config["template-file"] = str(
                (
                    path if path.is_absolute() else config_path.resolve().parent / path
                ).resolve()
            )
        repayments = config.get("foreign-credit-card-repayments", []) or []
        for repayment in repayments if isinstance(repayments, list) else []:
            if not isinstance(repayment, dict):
                continue
            location = repayment.get("ledger-file")
            if isinstance(location, str) and location:
                path = Path(location).expanduser()
                if not path.is_absolute():
                    path = config_path.resolve().parent / path
                repayment["ledger-file"] = str(path.resolve())
        return cast(dict[str, Any], config)
    except FileNotFoundError as fe:
        logging.error("找不到配置文件，请手动创建: %s", config_path)
        raise ConfigError(f"找不到配置文件，请手动创建: {config_path}") from fe
    except yaml.YAMLError as ye:
        logging.error("配置文件 YAML 格式错误: %s", config_path)
        raise ConfigError(f"配置文件 YAML 格式错误: {config_path}") from ye


def load_config_model(file: str | Path) -> Config:
    try:
        return Config.model_validate(load_config(file))
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_url=False, include_input=False)
        )
        raise ConfigError(f"配置字段错误: {details}") from error
