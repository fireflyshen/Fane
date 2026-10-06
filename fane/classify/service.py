#!/usr/bin/env python3
"""Safely bridge AI classifications into the Bills ledger and Fane rules.

The AI never edits files directly. ``extract`` emits a constrained JSON payload;
``apply`` accepts decisions, validates them against the current transaction text,
updates only FIXME account tokens, appends narrow Fane rules, and rolls every
file back if a validator fails.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

SCHEMA_VERSION = 1
PLACEHOLDER_RE = re.compile(
    r"^(?P<indent>\s+)(?P<account>(?:Assets|Liabilities|Income|Expenses):"
    r"(?:FIXME|FixMe|Fix))(?P<suffix>\s+.*)?$"
)
HEADER_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<flag>[*!])\s+"
    r'"(?P<payee>(?:[^"\\]|\\.)*)"\s+"(?P<narration>(?:[^"\\]|\\.)*)"'
)
DIRECTIVE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+")
META_RE = re.compile(r'^\s+(?P<key>[A-Za-z_][A-Za-z0-9_-]*):\s+"(?P<value>.*)"\s*$')
OPEN_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+open\s+(?P<account>[A-Z][A-Za-z0-9:-]*)"
    r"(?P<tail>.*?)(?:\s+;\s*(?P<comment>.*))?$"
)
ACCOUNT_RE = re.compile(
    r"^(?:Assets|Liabilities|Equity|Income|Expenses)"
    r"(?::[A-Z][A-Za-z0-9-]*)+$"
)
PROVIDER_ALIASES = {
    "alipay": "alipay",
    "ali": "alipay",
    "支付宝": "alipay",
    "wechat": "wechat",
    "weixin": "wechat",
    "微信": "wechat",
}
MATCH_FIELDS = {
    "alipay": ("peer", "item", "category", "type", "method"),
    "wechat": ("peer", "item", "category", "tx_type", "method"),
}
ACCOUNT_FILES = {
    "Assets": "assets.bean",
    "Liabilities": "liabilities.bean",
    "Equity": "equity.bean",
    "Income": "income.bean",
    "Expenses": "expenses.bean",
}


class FixmeError(RuntimeError):
    """Raised when an AI proposal is unsafe or stale."""


@dataclass(frozen=True)
class Posting:
    posting_id: str
    line_index: int
    line_number: int
    placeholder_account: str
    raw: str


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    content_hash: str
    relative_file: str
    start_index: int
    end_index: int
    start_line: int
    date: str
    flag: str
    payee: str
    narration: str
    metadata: dict[str, str]
    postings: tuple[Posting, ...]
    lines: tuple[str, ...]

    @property
    def provider(self) -> str | None:
        value = self.metadata.get("source", "")
        return PROVIDER_ALIASES.get(value.strip().lower()) or PROVIDER_ALIASES.get(
            value.strip()
        )

    def fields_for_rules(self) -> dict[str, str]:
        values = {
            "peer": self.payee,
            "item": self.narration,
            "category": self.metadata.get("category", ""),
            "type": self.metadata.get("type", ""),
            "tx_type": self.metadata.get("tx_type", ""),
            "method": self.metadata.get("method", ""),
            "status": self.metadata.get("status", ""),
        }
        return {key: value for key, value in values.items() if value}


def _unescape_bean_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value


def _stable_hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _iter_bean_files(root: Path) -> Iterable[Path]:
    journal = root / "journal"
    if not journal.is_dir():
        raise FixmeError(f"账本目录不存在: {journal}")
    yield from sorted(journal.rglob("*.bean"))


def scan_transactions(root: Path) -> list[Transaction]:
    transactions: list[Transaction] = []
    for path in _iter_bean_files(root):
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        indexes = [index for index, line in enumerate(lines) if HEADER_RE.match(line)]
        for position, start in enumerate(indexes):
            next_headers = [
                index
                for index in range(start + 1, len(lines))
                if DIRECTIVE_RE.match(lines[index])
            ]
            end = next_headers[0] if next_headers else len(lines)
            header = HEADER_RE.match(lines[start])
            assert header is not None
            block = lines[start:end]
            metadata: dict[str, str] = {}
            postings: list[Posting] = []
            relative = str(path.relative_to(root))
            content_hash = _stable_hash(relative, "".join(block))
            order_id = ""
            for offset, line in enumerate(block):
                meta = META_RE.match(line)
                if meta:
                    metadata[meta.group("key")] = _unescape_bean_string(
                        meta.group("value")
                    )
                    order_id = metadata.get("order_id", order_id)
            transaction_id = _stable_hash(
                relative,
                str(start),
                order_id,
                header.group("date"),
                _unescape_bean_string(header.group("payee")),
                _unescape_bean_string(header.group("narration")),
                content_hash,
            )
            for offset, line in enumerate(block):
                match = PLACEHOLDER_RE.match(line.rstrip("\n"))
                if not match:
                    continue
                placeholder = match.group("account")
                posting_id = _stable_hash(
                    transaction_id, str(offset), placeholder, line.rstrip("\n")
                )
                postings.append(
                    Posting(
                        posting_id=posting_id,
                        line_index=start + offset,
                        line_number=start + offset + 1,
                        placeholder_account=placeholder,
                        raw=line.rstrip("\n"),
                    )
                )
            if postings:
                transactions.append(
                    Transaction(
                        transaction_id=transaction_id,
                        content_hash=content_hash,
                        relative_file=relative,
                        start_index=start,
                        end_index=end,
                        start_line=start + 1,
                        date=header.group("date"),
                        flag=header.group("flag"),
                        payee=_unescape_bean_string(header.group("payee")),
                        narration=_unescape_bean_string(header.group("narration")),
                        metadata=metadata,
                        postings=tuple(postings),
                        lines=tuple(block),
                    )
                )
    return transactions


def account_catalog(root: Path) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    data_dir = root / "accounts" / "data"
    for path in sorted(data_dir.glob("*.bean")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = OPEN_RE.match(line)
            if not match:
                continue
            result.append(
                {
                    "name": match.group("account"),
                    "comment_zh": (match.group("comment") or "").strip(),
                }
            )
    return sorted(result, key=lambda item: item["name"])


def extraction_payload(root: Path) -> dict[str, Any]:
    transactions = scan_transactions(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "policy": {
            "minimum_confidence": 0.92,
            "preserve_transaction_facts": True,
            "prefer_existing_accounts": True,
            "new_accounts_allowed": ["Expenses", "Income"],
            "ambiguous_economic_ownership_action": "defer",
        },
        "accounts": account_catalog(root),
        "allowed_rule_fields": MATCH_FIELDS,
        "transactions": [
            {
                "transaction_id": tx.transaction_id,
                "content_hash": tx.content_hash,
                "file": tx.relative_file,
                "line": tx.start_line,
                "date": tx.date,
                "flag": tx.flag,
                "provider": tx.provider,
                "payee": tx.payee,
                "narration": tx.narration,
                "metadata": tx.metadata,
                "rule_source_fields": tx.fields_for_rules(),
                "placeholder_postings": [
                    {
                        "posting_id": posting.posting_id,
                        "line": posting.line_number,
                        "placeholder_account": posting.placeholder_account,
                        "raw": posting.raw.strip(),
                        "suggested_rule_account_field": (
                            "method-account"
                            if posting.placeholder_account.lower().startswith("assets:")
                            else "target-account"
                        ),
                    }
                    for posting in tx.postings
                ],
            }
            for tx in transactions
        ],
    }


def _load_decisions(path: str | None, encoded: str | None = None) -> dict[str, Any]:
    if encoded is not None:
        try:
            text = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as error:
            raise FixmeError(f"AI 输出不是有效的 UTF-8 Base64: {error}") from error
    elif path == "-":
        text = sys.stdin.read()
    elif path is not None:
        text = Path(path).read_text(encoding="utf-8")
    else:
        raise FixmeError("必须提供 --input 或 --input-base64")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise FixmeError(f"AI 输出不是有效 JSON: {error}") from error
    if not isinstance(value, dict):
        raise FixmeError("AI 输出顶层必须是 JSON object")
    return value


def _normalize_provider(value: Any) -> str:
    if not isinstance(value, str):
        raise FixmeError("rule.provider 必须是字符串")
    provider = PROVIDER_ALIASES.get(value.strip().lower()) or PROVIDER_ALIASES.get(
        value.strip()
    )
    if provider is None:
        raise FixmeError(f"不支持的 provider: {value!r}")
    return provider


def _validate_account(value: Any) -> str:
    if not isinstance(value, str) or not ACCOUNT_RE.fullmatch(value):
        raise FixmeError(f"无效的 Beancount 账户名: {value!r}")
    if "FIXME" in value.upper() or value.endswith(":Fix"):
        raise FixmeError(f"替换账户仍然是占位账户: {value}")
    return value


def _validate_rule(
    decision: dict[str, Any], transaction: Transaction, replacement: str
) -> dict[str, Any]:
    raw_rule = decision.get("rule")
    if not isinstance(raw_rule, dict):
        raise FixmeError("每条 apply 决策都必须包含 rule")
    provider = _normalize_provider(raw_rule.get("provider"))
    if transaction.provider != provider:
        raise FixmeError(
            f"provider 与原交易不一致: {provider!r} != {transaction.provider!r}"
        )
    account_field = raw_rule.get("account_field")
    expected_field = (
        "method-account"
        if decision["_posting"].placeholder_account.lower().startswith("assets:")
        else "target-account"
    )
    if account_field != expected_field:
        raise FixmeError(
            f"rule.account_field 应为 {expected_field!r}，收到 {account_field!r}"
        )
    raw_match = raw_rule.get("match")
    if not isinstance(raw_match, dict):
        raise FixmeError("rule.match 必须是 JSON object")
    allowed = MATCH_FIELDS[provider]
    source_fields = transaction.fields_for_rules()
    match: dict[str, str] = {}
    for key, value in raw_match.items():
        if key not in allowed:
            raise FixmeError(f"{provider} 不支持规则字段 {key!r}")
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise FixmeError(f"规则字段 {key!r} 的值无效")
        if any(char in value for char in "|,\n\r"):
            raise FixmeError(f"规则字段 {key!r} 只能使用当前交易的单个精确值")
        if source_fields.get(key) != value:
            raise FixmeError(
                f"规则 {key!r} 必须精确取自当前交易；期望 "
                f"{source_fields.get(key)!r}，收到 {value!r}"
            )
        match[key] = value
    if not ({"peer", "item"} & match.keys()):
        raise FixmeError("规则至少需要 peer 或 item，禁止只按金额/类型做宽泛分类")
    if len(match) < 2:
        raise FixmeError("自动规则至少需要两个精确匹配字段，避免污染未来交易")
    return {
        "provider": provider,
        "account_field": account_field,
        "match": {key: match[key] for key in allowed if key in match},
        "replacement_account": replacement,
    }


def _validate_new_account(
    root: Path,
    replacement: str,
    raw: Any,
    existing: set[str],
) -> dict[str, str] | None:
    if replacement in existing:
        if raw not in (None, {}):
            raise FixmeError(f"账户 {replacement} 已存在，不应提供 new_account")
        return None
    prefix = replacement.split(":", 1)[0]
    if prefix not in {"Expenses", "Income"}:
        raise FixmeError(
            f"自动创建账户仅允许 Expenses/Income；{replacement} 需要人工确认经济含义"
        )
    if not isinstance(raw, dict):
        raise FixmeError(f"新账户 {replacement} 必须提供 new_account")
    comment = raw.get("comment_zh")
    if (
        not isinstance(comment, str)
        or not comment.strip()
        or len(comment.strip()) > 80
        or any(char in comment for char in "\r\n;")
    ):
        raise FixmeError("new_account.comment_zh 必须是 1-80 字且不能包含换行或分号")
    result = {"comment_zh": comment.strip()}
    if prefix == "Expenses":
        label = raw.get("flux_label")
        if (
            not isinstance(label, str)
            or not label.strip()
            or len(label.strip()) > 40
            or any(char in label for char in '\r\n"')
        ):
            raise FixmeError("新支出账户必须提供 1-40 字的 flux_label")
        result["flux_label"] = label.strip()
    return result


def validate_decisions(
    root: Path,
    payload: dict[str, Any],
    *,
    min_confidence: float,
    allow_partial: bool,
) -> list[dict[str, Any]]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise FixmeError(
            f"schema_version 必须是 {SCHEMA_VERSION}，收到 {payload.get('schema_version')!r}"
        )
    raw_decisions = payload.get("decisions")
    if not isinstance(raw_decisions, list):
        raise FixmeError("AI 输出必须包含 decisions 数组")
    transactions = scan_transactions(root)
    posting_map: dict[str, tuple[Transaction, Posting]] = {
        posting.posting_id: (tx, posting)
        for tx in transactions
        for posting in tx.postings
    }
    existing = {item["name"] for item in account_catalog(root)}
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    deferred: set[str] = set()
    for index, raw in enumerate(raw_decisions):
        if not isinstance(raw, dict):
            raise FixmeError(f"decisions[{index}] 必须是 object")
        posting_id = raw.get("posting_id")
        if not isinstance(posting_id, str) or posting_id not in posting_map:
            raise FixmeError(f"decisions[{index}] 引用了不存在或已变化的 posting_id")
        if posting_id in seen:
            raise FixmeError(f"posting_id 重复决策: {posting_id}")
        seen.add(posting_id)
        action = raw.get("action")
        if action == "defer":
            reason = raw.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise FixmeError("defer 决策必须说明 reason")
            deferred.add(posting_id)
            continue
        if action != "apply":
            raise FixmeError(f"action 只能是 apply 或 defer，收到 {action!r}")
        confidence = raw.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise FixmeError("confidence 必须是 0-1 数字")
        if not 0 <= float(confidence) <= 1 or float(confidence) < min_confidence:
            raise FixmeError(
                f"置信度 {confidence!r} 低于自动应用阈值 {min_confidence:.2f}"
            )
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise FixmeError("apply 决策必须说明 reason")
        tx, posting = posting_map[posting_id]
        replacement = _validate_account(raw.get("replacement_account"))
        decision = dict(raw)
        decision["_transaction"] = tx
        decision["_posting"] = posting
        decision["_replacement"] = replacement
        decision["_new_account"] = _validate_new_account(
            root, replacement, raw.get("new_account"), existing
        )
        decision["_rule"] = _validate_rule(decision, tx, replacement)
        validated.append(decision)
    missing = set(posting_map) - seen
    unresolved = missing | deferred
    if unresolved and not allow_partial:
        raise FixmeError(
            f"仍有 {len(unresolved)} 个 FixMe 未获高置信度分类；本次不修改任何文件"
        )
    return validated


def _replace_posting(line: str, placeholder: str, replacement: str) -> str:
    match = PLACEHOLDER_RE.match(line.rstrip("\n"))
    if not match or match.group("account") != placeholder:
        raise FixmeError("待修改分录已变化，拒绝继续")
    newline = "\n" if line.endswith("\n") else ""
    return f"{match.group('indent')}{replacement}{match.group('suffix') or ''}{newline}"


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_rule(rule: dict[str, Any]) -> str:
    lines = ["    # AI 自动分类：精确匹配当前交易字段"]
    first = True
    for key, value in rule["match"].items():
        prefix = "    - " if first else "      "
        lines.append(f"{prefix}{key}: {_yaml_quote(value)}")
        first = False
    lines.append(f"      {rule['account_field']}: {rule['replacement_account']}")
    return "\n".join(lines) + "\n"


def _append_rule(config_text: str, rule: dict[str, Any]) -> str:
    provider = rule["provider"]
    section = re.search(rf"(?m)^{re.escape(provider)}:\s*$", config_text)
    if section is None:
        raise FixmeError(f"bill.yaml 缺少 {provider}: 段")
    next_top = re.search(r"(?m)^[A-Za-z][A-Za-z0-9_-]*:", config_text[section.end() :])
    insert_at = (
        section.end() + next_top.start() if next_top is not None else len(config_text)
    )
    rendered = _render_rule(rule)
    section_text = config_text[section.start() : insert_at]
    account_line = f"      {rule['account_field']}: {rule['replacement_account']}"
    match_lines = [
        f"{key}: {_yaml_quote(value)}" for key, value in rule["match"].items()
    ]
    if account_line in section_text and all(
        line in section_text for line in match_lines
    ):
        return config_text
    # config init uses an empty inline list; turn it into a block list before
    # adding entries, preserving surrounding configuration and comments.
    section_text = re.sub(
        r"(?m)^  rules:\s*\[\]\s*(#.*)?$", r"  rules: \1", section_text
    )
    if not re.search(r"(?m)^  rules:\s*(?:#.*)?$", section_text):
        if re.search(r"(?m)^  rules:", section_text):
            raise FixmeError(
                "自动追加规则要求 rules 使用缩进列表；请先展开行内 YAML 列表"
            )
        section_text = section_text.rstrip() + "\n  rules:\n"
    prefix = config_text[: section.start()] + section_text.rstrip() + "\n\n"
    suffix = config_text[insert_at:].lstrip("\n")
    updated = prefix + rendered + "\n" + suffix
    try:
        yaml.safe_load(updated)
    except yaml.YAMLError as error:
        raise FixmeError(f"追加规则后的 YAML 无效: {error}") from error
    return updated


def _append_account(text: str, date: str, account: str, details: dict[str, str]) -> str:
    prefix = account.split(":", 1)[0]
    directive = f"{date} open {account}"
    if prefix != "Expenses":
        directive = f"{directive:<59}CNY"
    spacing = " " * max(2, 75 - len(directive))
    entry = f"{directive}{spacing}; {details['comment_zh']}\n"
    if prefix == "Expenses":
        entry += f"  flux_label: {_yaml_quote(details['flux_label'])}\n"
    marker = "; AI-managed accounts"
    if marker not in text:
        return text.rstrip() + f"\n\n{marker}\n" + entry
    return text.rstrip() + "\n" + entry


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _run_command(command: list[str], cwd: Path, label: str) -> None:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise FixmeError(f"{label} 无法执行: {error}") from error
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise FixmeError(f"{label} 失败 ({result.returncode}): {detail}")


def _apply_changes(
    root: Path,
    decisions: list[dict[str, Any]],
    *,
    config_path: Path,
    dry_run: bool,
    validators: list[str],
) -> dict[str, Any]:
    files: dict[Path, str] = {}
    changed_postings: list[dict[str, str]] = []
    new_accounts: dict[str, tuple[str, dict[str, str]]] = {}
    rules: list[dict[str, Any]] = []
    for decision in decisions:
        tx: Transaction = decision["_transaction"]
        posting: Posting = decision["_posting"]
        replacement: str = decision["_replacement"]
        path = root / tx.relative_file
        if path not in files:
            files[path] = path.read_text(encoding="utf-8")
        lines = files[path].splitlines(keepends=True)
        lines[posting.line_index] = _replace_posting(
            lines[posting.line_index], posting.placeholder_account, replacement
        )
        files[path] = "".join(lines)
        changed_postings.append(
            {
                "file": tx.relative_file,
                "line": str(posting.line_number),
                "from": posting.placeholder_account,
                "to": replacement,
            }
        )
        if decision["_new_account"] is not None:
            previous = new_accounts.get(replacement)
            details = decision["_new_account"]
            current = (tx.date, details)
            if previous is not None:
                if previous[1] != details:
                    raise FixmeError(f"新账户 {replacement} 的定义相互冲突")
                current = (min(previous[0], tx.date), details)
            new_accounts[replacement] = current
        rules.append(decision["_rule"])

    for account, (date, details) in new_accounts.items():
        prefix = account.split(":", 1)[0]
        path = root / "accounts" / "data" / ACCOUNT_FILES[prefix]
        original = files.get(path, path.read_text(encoding="utf-8"))
        if re.search(
            rf"(?m)^\d{{4}}-\d{{2}}-\d{{2}}\s+open\s+{re.escape(account)}(?:\s|$)",
            original,
        ):
            continue
        files[path] = _append_account(original, date, account, details)

    config_text = files.get(config_path, config_path.read_text(encoding="utf-8"))
    for rule in rules:
        config_text = _append_rule(config_text, rule)
    files[config_path] = config_text

    def display_path(path: Path) -> str:
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)

    result = {
        "status": "dry-run" if dry_run else "applied",
        "changed_postings": changed_postings,
        "new_accounts": sorted(new_accounts),
        "rules_considered": len(rules),
        "files": sorted(display_path(path) for path in files),
    }
    if dry_run:
        return result

    snapshots = {path: path.read_bytes() if path.exists() else None for path in files}
    try:
        for path, content in files.items():
            _atomic_write(path, content)
        for validator in validators:
            command = shlex.split(validator)
            if not command:
                raise FixmeError("validator 不能为空")
            _run_command(command, root, f"校验命令 {validator!r}")
    except Exception:
        for path, content in snapshots.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise
    return result


def apply_decisions(
    root: Path,
    payload: dict[str, Any],
    *,
    config_path: Path,
    ledger: Path,
    write: bool = False,
    min_confidence: float = 0.92,
    allow_partial: bool = False,
    validators: list[str] | None = None,
    check_config: bool = True,
) -> dict[str, Any]:
    """CLI 和账单流程共用的分类校验、写入及失败回滚。"""
    decisions = validate_decisions(
        root, payload, min_confidence=min_confidence, allow_partial=allow_partial
    )
    command = [sys.executable, "-m", "fane", "--config", str(config_path)]
    checks = (
        list(validators)
        if validators
        else [shlex.join([*command, "check", "--ledger", str(ledger)])]
    )
    if check_config:
        checks.insert(0, shlex.join([*command, "config", "check"]))
    return _apply_changes(
        root, decisions, config_path=config_path, dry_run=not write, validators=checks
    )
