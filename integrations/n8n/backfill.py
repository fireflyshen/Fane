"""One-off, resumable monthly report delivery. Runtime state stays private on rn."""

import argparse
import base64
import fcntl
import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("/root/.flow")
BATCH = ROOT / "state/monthly-reports/backfill/20261006"
MONTH = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])\Z")


def read(name):
    return json.loads((BATCH / name).read_text())


def write(name, data):
    path = BATCH / name
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False))
    temporary.chmod(0o600)
    temporary.replace(path)


def initialize():
    BATCH.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (BATCH / "manifest.json").exists():
        return read("manifest.json")
    from datetime import date

    from fane.flow.snapshot import snapshot as extract

    as_of = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    snapshot = extract(
        ROOT / "data/account/main.bean", cutoff=date.fromisoformat(as_of)
    )
    months = sorted(snapshot["ledger"])
    assert months and months[-1] <= as_of[:7]
    assert not any(
        re.search("fixme", text, re.I) for text in snapshot["ledger"].values()
    ), "Ledger still contains FIXME"
    for month in months:
        source = ROOT / f"data/account/journal/{month[:4]}/{month}.bean"
        assert not source.exists() or not re.search(
            "fixme", source.read_text(), re.I
        ), "Journal still contains FIXME"
    snapshot["partialComparison"] = extract(
        ROOT / "data/account/main.bean",
        cutoff=date.fromisoformat(as_of),
        day=int(as_of[-2:]),
    )
    write("snapshot.json", snapshot)
    db = sqlite3.connect(
        "file:" + str(ROOT / "state/n8n/database.sqlite") + "?mode=ro", uri=True
    )
    db.row_factory = sqlite3.Row
    actions = [
        dict(row)
        for row in db.execute("SELECT * FROM data_table_user_eRhKVHIQoJ6SPCLw")
    ]
    db.close()
    write("actions.json", actions)
    manifest = {
        "asOf": as_of,
        "selected": None,
        "months": {month: {"status": "pending", "attempts": 0} for month in months},
    }
    write("manifest.json", manifest)
    return manifest


def selected(manifest):
    month = manifest["selected"]
    if (
        not isinstance(month, str)
        or not MONTH.fullmatch(month)
        or month not in manifest["months"]
    ):
        raise ValueError("No selected month")
    return month, manifest["months"][month]


def operate(operation, month=None, request=None):
    manifest = initialize()
    if operation == "status":
        return {
            "asOf": manifest["asOf"],
            "months": {m: row["status"] for m, row in manifest["months"].items()},
        }
    if operation == "select":
        assert month in manifest["months"] and MONTH.fullmatch(month)
        manifest["selected"] = month
        write("manifest.json", manifest)
        return {"selected": month, "status": manifest["months"][month]["status"]}
    month, row = selected(manifest)
    snapshot = read("snapshot.json")
    if operation == "prepare":
        assert row["status"] in ("pending", "ready"), "Month cannot be regenerated"
        year, number = map(int, month.split("-"))
        before = f"{year - (number == 1):04d}-{number - 1 if number > 1 else 12:02d}"
        mode = "partial" if month == manifest["asOf"][:7] else "history"
        previous_snapshot = (
            snapshot["partialComparison"] if mode == "partial" else snapshot
        )
        context = {
            "analysisMonth": month,
            "previousMonth": before,
            "asOf": manifest["asOf"],
            "reportMode": mode,
            "facts": snapshot["facts"][month],
            "previousFacts": previous_snapshot["facts"].get(before),
            "previousActions": [
                a for a in read("actions.json") if a["target_month"] == month
            ],
            "ledgerData": f"CURRENT_MONTH {month}\n{snapshot['ledger'][month]}\nPREVIOUS_MONTH {before}\n{previous_snapshot['ledger'].get(before, '(No transactions available)')}",
            "validationFeedback": row.get("feedback", ""),
        }
        row["attempts"] += 1
        write("manifest.json", manifest)
        return context
    if operation == "store":
        assert row["status"] in ("pending", "ready")
        report = request["report"]
        assert (
            report["analysisMonth"] == month
            and report["email_html"]
            and report["email_text"]
        )
        assert report["template_version"] == 2
        subject = (
            f"{month} 财务报告（截至 {manifest['asOf']}）"
            if month == manifest["asOf"][:7]
            else f"{month} 月度财务报告（历史补发）"
        )
        write(month + ".json", {"report": report, "subject": subject})
        row.update(
            status="ready",
            generatedAt=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        )
        write("manifest.json", manifest)
        return {"stored": True, "month": month}
    if operation == "feedback":
        assert row["status"] == "pending"
        row["feedback"] = str(request["error"])[:500]
        write("manifest.json", manifest)
        return {"retry": True}
    if operation == "begin":
        assert row["status"] == "ready", (
            "Already sent or delivery uncertain; do not resend"
        )
        payload = read(month + ".json")
        row.update(
            status="sending",
            sendStarted=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        )
        write("manifest.json", manifest)
        return {**payload["report"], "mail_subject": payload["subject"]}
    if operation == "sent":
        assert row["status"] in ("sending", "sent")
        assert (
            request["accepted_count"] > 0
            and request["rejected_count"] == 0
            and request["messageId"]
        )
        now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        row.update(status="sent", sentAt=now, receipt=request)
        write("manifest.json", manifest)
        # Complete missing closed-month records without replacing already sent history.
        if month < manifest["asOf"][:7]:
            report = read(month + ".json")["report"]
            year, number = map(int, month.split("-"))
            before = (
                f"{year - (number == 1):04d}-{number - 1 if number > 1 else 12:02d}"
            )
            digest = hashlib.sha256(
                (
                    snapshot["ledger"][month]
                    + "\0"
                    + snapshot["ledger"].get(before, "")
                ).encode()
            ).hexdigest()
            db = sqlite3.connect(ROOT / "state/monthly-reports/reports.sqlite")
            with db:
                db.execute(
                    """INSERT INTO reports(month,status,token,source_hash,generated_at,sent_at,report_json)
                    VALUES(?,'sent',?,?,?,?,?) ON CONFLICT(month) DO UPDATE SET status='sent',
                    token=excluded.token,source_hash=excluded.source_hash,generated_at=excluded.generated_at,
                    sent_at=excluded.sent_at,report_json=excluded.report_json WHERE reports.status!='sent'""",
                    (
                        month,
                        "backfill-20261006",
                        digest,
                        row["generatedAt"],
                        now,
                        json.dumps(report, ensure_ascii=False),
                    ),
                )
            db.close()
        return {"sent": True, "month": month}
    raise ValueError("Unknown operation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=["status", "select", "prepare", "store", "feedback", "begin", "sent"],
    )
    parser.add_argument("--month")
    parser.add_argument("--request-base64")
    args = parser.parse_args()
    BATCH.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (BATCH / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        request = (
            json.loads(base64.b64decode(args.request_base64, validate=True))
            if args.request_base64
            else None
        )
        print(
            json.dumps(operate(args.operation, args.month, request), ensure_ascii=False)
        )


if __name__ == "__main__":
    main()
