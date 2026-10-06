"""Verified GitHub synchronization for the automation adapter."""

import base64
import fcntl
import hashlib
import hmac
import json
import subprocess
from pathlib import Path


def handle(meta, config, *, root: Path):
    raw = base64.b64decode(meta["body"], validate=True)
    expected = (
        "sha256=" + hmac.new(config["secret"].encode(), raw, hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(expected, meta.get("signature", "")):
        return 401, "Invalid signature"
    if meta.get("event") != "push":
        return 200, "Ignored non-push event"
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return 400, "Invalid JSON"
    if not isinstance(data, dict):
        return 400, "Invalid JSON"
    if data.get("ref") != "refs/heads/" + config["branch"]:
        return 200, "Ignored branch"
    lock = root / "state/locks/n8n-finance.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 409, "Deployment in progress"
        try:
            path = config["repository"]
            subprocess.run(
                ["git", "merge", "--abort"], cwd=path, capture_output=True, timeout=30
            )
            for args in [
                ["fetch", "origin", config["branch"]],
                ["reset", "--hard", "origin/" + config["branch"]],
                ["clean", "-fd"],
            ]:
                result = subprocess.run(
                    ["git", *args], cwd=path, capture_output=True, timeout=180
                )
                if result.returncode:
                    return 500, "Deploy failed"
            return 200, "Deploy success"
        except (OSError, subprocess.SubprocessError):
            return 500, "Deploy failed"
