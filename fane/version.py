"""Distribution version, with a source-checkout fallback."""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def get_version() -> str:
    try:
        return version("Fane")
    except PackageNotFoundError:
        source = Path(__file__).resolve().parents[1] / "pyproject.toml"
        return (
            tomllib.loads(source.read_text())["project"]["version"]
            if source.is_file()
            else "Unknown"
        )
