import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    required_currencies: set[str] = Field(
        default_factory=set, alias="required-currencies"
    )
    required_metadata: dict[str, set[str]] = Field(
        default_factory=dict, alias="required-metadata"
    )
    disallowed_segments: set[str] = Field(
        default_factory=set, alias="disallowed-segments"
    )
    allowed_accounts: set[str] = Field(default_factory=set, alias="allowed-accounts")


class Assertions(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    output_dir: str | None = Field(None, alias="output-dir")
    index: str | None = None
    ignored_prefixes: tuple[str, ...] = Field((), alias="ignored-prefixes")
    precision: int = Field(2, ge=0)
    filename_template: str = Field("{date:%Y-%m}.bean", alias="filename-template")


class SnapshotSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    accrual_offset_prefixes: tuple[str, ...] = Field(
        (), alias="accrual-offset-prefixes"
    )


class LedgerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    file: str | None = None
    policy: Policy = Field(default_factory=Policy)
    assertions: Assertions = Field(default_factory=Assertions)
    snapshot: SnapshotSettings = Field(default_factory=SnapshotSettings)


class LedgerContext:
    def __init__(self, ledger: Path, settings: LedgerSettings, config: Path | None):
        self.ledger = ledger
        self.root = ledger.parent
        self.settings = settings
        self.config = config

    def output_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return path.resolve() if path.is_absolute() else (self.root / path).resolve()


def resolve_context(
    ledger: Path | None = None, config: Path | None = None
) -> LedgerContext:
    config = config.expanduser().resolve() if config else None
    settings = LedgerSettings()
    if config and config.is_file():
        data = yaml.safe_load(config.read_text()) or {}
        if not isinstance(data, dict):
            raise ValueError("Fane config must be a YAML object")
        settings = LedgerSettings.model_validate(data.get("ledger", {}))
    explicit = ledger or os.environ.get("FANE_LEDGER") or os.environ.get("BILLS_LEDGER")
    location = explicit or settings.file
    if not location:
        raise ValueError("Specify --ledger, FANE_LEDGER, or ledger.file in Fane config")
    path = Path(location).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() if explicit else config.parent) / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"Ledger does not exist: {path}")
    return LedgerContext(
        path, settings, config if config and config.is_file() else None
    )
