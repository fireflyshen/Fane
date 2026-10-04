"""Publish a validated snapshot with one object replacement; no source-ledger writes."""

import json
from datetime import date
from pathlib import Path

from fane.config.ledger import Policy

from .snapshot import export_snapshot
from .validation import validate_ledger


def publish_snapshot(
    client,
    *,
    ledger: Path,
    policy: Policy,
    config: Path | None,
    bucket: str,
    key: str,
    version: str,
    generator_version: str,
    force: bool = False,
    accrual_prefixes=(),
) -> bool:
    from botocore.exceptions import ClientError

    if not version.strip():
        raise ValueError("Snapshot version must not be empty")
    today = date.today().isoformat()
    if not force:
        try:
            remote = client.head_object(Bucket=bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                raise
        else:
            metadata = remote.get("Metadata", {})
            if (
                metadata.get("bills-version") == version
                and metadata.get("generator-version") == generator_version
                and metadata.get("as-of") == today
            ):
                return False
    failures = validate_ledger(ledger, policy, config)
    if failures:
        raise ValueError("Ledger validation failed:\n" + "\n".join(failures))
    snapshot = export_snapshot(
        ledger,
        version=version,
        include_transactions=True,
        accrual_prefixes=accrual_prefixes,
    )
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode(),
        ContentType="application/json",
        Metadata={
            "bills-version": version,
            "generator-version": generator_version,
            "as-of": today,
        },
    )
    return True
