from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from package.errors import SyncError


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SyncState:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"version": 1, "sources": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SyncError(f"无法读取同步状态 {self.path}: {error}") from error
        if not isinstance(value, dict) or not isinstance(value.get("sources"), dict):
            raise SyncError(f"同步状态格式无效: {self.path}")
        return value

    def source_digest(self, key: str) -> str | None:
        value = self.data["sources"].get(key)
        if isinstance(value, dict) and isinstance(value.get("sha256"), str):
            return value["sha256"]
        return None

    def update_source(self, key: str, value: dict[str, Any]) -> None:
        self.data["sources"][key] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            delete=False,
        )
        temporary = Path(handle.name)
        try:
            with handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()


class SyncLock:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self._handle = None

    def __enter__(self) -> "SyncLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._handle.close()
            self._handle = None
            raise SyncError(f"同步任务正在运行，锁文件: {self.path}") from error
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
