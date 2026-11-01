"""Bill export ranges verified against successful import fingerprints."""

import hashlib
import re
from datetime import datetime, timedelta

RANGE = re.compile(
    r"起始时间\D*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
    r".*?终止时间\D*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",
    re.S,
)


def imported_range(path):
    marker = path.with_name(path.name + ".md5")
    if not marker.is_file():
        return None
    raw = path.read_bytes()
    if marker.read_text().strip() != hashlib.md5(raw).hexdigest():
        return None
    if path.suffix == ".csv":
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                text = "\n".join(raw.decode(encoding).splitlines()[:20])
                break
            except UnicodeDecodeError:
                continue
        else:
            return None
    else:
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            text = "\n".join(
                " ".join(str(v or "") for v in row)
                for row in workbook.active.iter_rows(max_row=20, values_only=True)
            )
        finally:
            workbook.close()
    match = RANGE.search(text)
    if not match:
        return None
    start, end = (datetime.fromisoformat(value) for value in match.groups())
    return (start, end + timedelta(seconds=1)) if end >= start else None


def missing_sources(root, month, providers):
    start = datetime.fromisoformat(month + "-01")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    missing = []
    for provider in providers:
        if provider not in ("alipay", "wechat"):
            raise ValueError("Unknown required bill source")
        suffix = "csv" if provider == "alipay" else "xlsx"
        ranges = []
        for path in (root / "data/bills" / provider).glob("*." + suffix):
            span = imported_range(path)
            if span:
                ranges.append(span)
        covered = start
        for left, right in sorted(ranges):
            if left > covered:
                break
            covered = max(covered, right)
            if covered >= end:
                break
        if covered < end:
            missing.append(provider)
    return missing
