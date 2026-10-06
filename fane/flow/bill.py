"""Bill intake composition through the installed project commands."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fane.bill.archive import unpack

ROOT = Path.home() / ".flow"
CONFIG = str(ROOT / "config/fane.yaml")
LEDGER = ROOT / "data/account"


def command(stage, *args):
    result = subprocess.run(
        [sys.executable, "-m", "fane", "--config", CONFIG, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError(stage)
    return json.loads(result.stdout)


def prepare(meta):
    provider = meta["provider"]
    if provider not in ("alipay", "wechat"):
        raise ValueError("unknown provider")
    identifier = meta["file"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.zip", identifier):
        raise ValueError("invalid temporary filename")
    incoming = ROOT / "state/bills/incoming" / identifier
    day = meta.get("date") or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    datetime.strptime(day, "%Y-%m-%d")
    suffix = {"alipay": "csv", "wechat": "xlsx"}[provider]
    target = ROOT / "data/bills" / provider
    target.mkdir(parents=True, exist_ok=True)
    stage = "unzip"
    try:
        raw = unpack(incoming, suffix, meta.get("password"))
        output = target / (day + "." + suffix)
        if meta.get("preview"):
            if (
                not output.exists()
                or hashlib.sha256(raw).digest()
                != hashlib.sha256(output.read_bytes()).digest()
            ):
                raise ValueError("preview bill differs from existing output")
        else:
            with tempfile.NamedTemporaryFile(dir=target, delete=False) as temporary:
                temporary.write(raw)
                temporary.flush()
                os.fsync(temporary.fileno())
                filename = temporary.name
            os.replace(filename, output)
            os.replace(incoming, target / (day + ".zip"))
        stage = "import"
        flags = [] if meta.get("preview") else ["--write"]
        report = command(
            stage, "bill", "sync", "daily", "--date", day, "--json", *flags
        )
        if not meta.get("preview"):
            for source in report.get("sources", []):
                if source.get("status") not in (
                    "changed",
                    "unchanged",
                ) or not source.get("path"):
                    continue
                path = Path(source["path"])
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != source["sha256"]:
                    raise RuntimeError(stage)
                marker = Path(str(path) + ".md5")
                temporary = Path(str(marker) + ".n8n-tmp")
                temporary.write_text(hashlib.md5(data).hexdigest() + "\n")
                os.replace(temporary, marker)
        stage = "extract"
        payload = command(stage, "classify", "extract", "--root", str(LEDGER))
        if payload.get("schema_version") != 1 or not isinstance(
            payload.get("transactions"), list
        ):
            raise RuntimeError(stage)
        return [
            {
                "ok": True,
                "payload": payload,
                "import": report,
                "has_fixme": bool(payload["transactions"]),
            }
        ]
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
    ):
        return [{"ok": False, "stage": stage, "provider": provider}]
    finally:
        incoming.unlink(missing_ok=True)


def finish(meta):
    flags = [] if meta.get("preview") else ["--write"]
    results = {"ok": True}
    stage = "classify"
    try:
        if meta.get("decisions_b64"):
            results["classification"] = command(
                stage,
                "classify",
                "apply",
                "--root",
                str(LEDGER),
                "--input-base64",
                meta["decisions_b64"],
                "--validator",
                "docker exec fava bean-check /bean/main.bean",
                *flags,
            )
        stage = "subscriptions"
        results["subscriptions"] = command(
            stage,
            "sub",
            "generate",
            "--ledger",
            str(LEDGER / "main.bean"),
            "--subscriptions",
            str(ROOT / "config/subscriptions.json"),
            "--json",
            *flags,
        )
        return results
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return {"ok": False, "stage": stage}

