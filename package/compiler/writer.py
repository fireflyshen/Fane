import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from package.compiler.results import RenderedEntry


class JournalWriter:
    def __init__(
        self,
        journal_dir: str | Path,
        *,
        dedupe_index: str | Path | None = None,
        force: bool = False,
    ):
        self.journal_dir = Path(journal_dir)
        self.dedupe_index = Path(dedupe_index) if dedupe_index else (
            self.journal_dir.parent / ".fane" / "imported.jsonl"
        )
        self.force = force
        self._seen = self._load_seen()

    def write(self, entries: list[RenderedEntry]) -> dict[str, int]:
        written = 0
        skipped = 0
        for entry in sorted(entries, key=lambda item: (item.date, item.content)):
            if not self.force and entry.fingerprint in self._seen:
                skipped += 1
                continue
            target_file = self.target_file(entry)
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with open(target_file, "a", encoding="utf-8") as output:
                output.write(entry.content)
                if not entry.content.endswith("\n"):
                    output.write("\n")
                output.write("\n")
            self._record(entry, target_file)
            self._seen.add(entry.fingerprint)
            written += 1
        return {"written": written, "skipped": skipped}

    def target_file(self, entry: RenderedEntry) -> Path:
        year_dir = self.journal_dir / f"{entry.date.year}"
        if entry.kind == "income":
            return year_dir / "income.bean"
        return year_dir / f"{entry.date.year}-{entry.month}.bean"

    def _load_seen(self) -> set[str]:
        if not self.dedupe_index.is_file():
            return set()
        seen: set[str] = set()
        with open(self.dedupe_index, "r", encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fingerprint = data.get("fingerprint")
                if isinstance(fingerprint, str):
                    seen.add(fingerprint)
        return seen

    def _record(self, entry: RenderedEntry, target_file: Path) -> None:
        self.dedupe_index.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(entry)
        data["date"] = entry.date.isoformat()
        data["target"] = str(target_file)
        data["imported_at"] = datetime.now().isoformat(timespec="seconds")
        with open(self.dedupe_index, "a", encoding="utf-8") as index:
            index.write(json.dumps(data, ensure_ascii=False))
            index.write("\n")
