"""账单流程直接组合业务函数；n8n 只需调用 fa flow bill。"""

import hashlib
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fane.bill.archive import unpack
from fane.bill.sync import SyncService
from fane.classify import service as classify
from fane.shared.config import load_config_model
from fane.shared.errors import FaneError
from fane.subscriptions.service import SubscriptionService


@dataclass(frozen=True)
class BillFlow:
    root: Path
    config: Path

    @property
    def ledger(self):
        return self.root / "data/account"

    def prepare(self, meta):
        provider = meta["provider"]
        if provider not in ("alipay", "wechat"):
            raise ValueError("unknown provider")
        identifier = meta["file"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.zip", identifier):
            raise ValueError("invalid temporary filename")
        incoming = self.root / "state/bills/incoming" / identifier
        day = (
            meta.get("date")
            or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        )
        datetime.strptime(day, "%Y-%m-%d")
        suffix = {"alipay": "csv", "wechat": "xlsx"}[provider]
        target = self.root / "data/bills" / provider
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
            config = load_config_model(self.config)
            if not config.jobs or "daily" not in config.jobs:
                raise ValueError("daily sync job is not configured")
            job = config.jobs["daily"].model_copy(deep=True)

            # The flow's paths are relative to its data root, as in the SSH command.
            def absolute(value):
                path = Path(value).expanduser()
                return str(path if path.is_absolute() else self.root / path)

            job.journal_dir = absolute(job.journal_dir)
            for field in ("state_file", "lock_file", "dedupe_index"):
                if value := getattr(job, field):
                    setattr(job, field, absolute(value))
            for source in job.sources:
                if source.path is not None:
                    source.path = absolute(source.path)
                if source.glob is not None:
                    source.glob = absolute(source.glob)
            for validator in job.validators:
                validator.cwd = (
                    absolute(validator.cwd) if validator.cwd else str(self.root)
                )
            report = (
                SyncService(config, "daily", job)
                .run(
                    run_date=date.fromisoformat(day), dry_run=bool(meta.get("preview"))
                )
                .to_dict()
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
            payload = classify.extraction_payload(self.ledger)
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
            FaneError,
            zipfile.BadZipFile,
        ):
            return [{"ok": False, "stage": stage, "provider": provider}]
        finally:
            incoming.unlink(missing_ok=True)

    def finish(self, meta):
        write = not meta.get("preview")
        results = {"ok": True}
        stage = "classify"
        try:
            if meta.get("decisions_b64"):
                payload = classify._load_decisions(None, meta["decisions_b64"])
                results["classification"] = classify.apply_decisions(
                    self.ledger,
                    payload,
                    config_path=self.config.resolve(),
                    ledger=self.ledger / "main.bean",
                    write=write,
                    validators=["docker exec fava bean-check /bean/main.bean"],
                )
            stage = "subscriptions"
            config = load_config_model(self.config)
            results["subscriptions"] = SubscriptionService(
                self.ledger / "main.bean", self.root / "config/subscriptions.json"
            ).generate(
                write=write,
                template_file=Path(config.template_file)
                if config.template_file
                else None,
            )
            return results
        except (OSError, ValueError, RuntimeError, FaneError):
            return {"ok": False, "stage": stage}
