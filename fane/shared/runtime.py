"""Shared runtime state paths, independent of the ledger working tree."""

import hashlib
import os
from pathlib import Path

from fane.shared.errors import SyncError


def state_directory(journal: Path) -> Path:
    base = os.environ.get("FANE_STATE_HOME")
    if base:
        root = Path(base).expanduser()
    else:
        root = (
            Path(
                os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
            ).expanduser()
            / "fane"
        )
    identity = (
        os.environ.get("FANE_STATE_NAMESPACE")
        or hashlib.sha256(str(journal.resolve()).encode()).hexdigest()[:24]
    )
    if identity in {".", ".."} or Path(identity).name != identity:
        raise SyncError("FANE_STATE_NAMESPACE must be a directory name")
    return root / identity


def ensure_state_migrated(journal: Path, destination: Path) -> None:
    legacy = journal.parent / ".fane" / destination.name
    if legacy.is_file() and not destination.exists():
        raise SyncError(
            f"Legacy state found at {legacy}; move it to {destination} or explicitly configure its path before importing"
        )
