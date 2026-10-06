"""Historical standalone CLI; new callers use fa classify."""

import argparse
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from fane.classify import service
from fane.shared.config.ledger import resolve_context


def _default_fane() -> str | None:
    return shutil.which("fa")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.environ["BILLS_ROOT"])
        if os.environ.get("BILLS_ROOT")
        else None,
        help="Bills 仓库根目录",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Fane 配置；默认使用 ~/.flow/config.yaml",
    )
    parser.add_argument(
        "--ledger", type=Path, default=None, help="账本入口；默认由 Fane 配置解析"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract", help="输出待 AI 分类的 FixMe JSON")
    extract.add_argument("--output", default="-", help="输出文件；- 表示 stdout")

    apply = subparsers.add_parser("apply", help="校验并应用 AI JSON 决策")
    input_group = apply.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input", help="AI JSON 文件；- 表示 stdin")
    input_group.add_argument(
        "--input-base64",
        help="AI JSON 的 UTF-8 Base64；适合 n8n Execute Command 安全传参",
    )
    apply.add_argument("--min-confidence", type=float, default=0.92)
    apply.add_argument("--allow-partial", action="store_true")
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument(
        "--fane",
        default=_default_fane(),
        help="fa 可执行文件；传空字符串可跳过 doctor",
    )
    apply.add_argument(
        "--validator",
        action="append",
        default=None,
        help="成功落盘前必须通过的命令，可重复；默认 fa ledger validate",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = (
        (args.config or Path.home() / ".flow" / "config.yaml").expanduser().resolve()
    )
    if args.root is None:
        try:
            args.root = resolve_context(args.ledger, config_path).root
        except ValueError as error:
            parser.error(str(error))
    root = args.root.resolve()
    try:
        if args.command == "extract":
            payload = service.extraction_payload(root)
            content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            if args.output == "-":
                sys.stdout.write(content)
            else:
                service._atomic_write(Path(args.output), content)
            return 0
        payload = service._load_decisions(args.input, args.input_base64)
        decisions = service.validate_decisions(
            root,
            payload,
            min_confidence=args.min_confidence,
            allow_partial=args.allow_partial,
        )
        result = service._apply_changes(
            root,
            decisions,
            config_path=config_path,
            dry_run=args.dry_run,
            fane_command=args.fane or None,
            validators=args.validator
            or [
                shlex.join(
                    [
                        sys.executable,
                        "-m",
                        "fane",
                        "--config",
                        str(config_path),
                        "check",
                        "--ledger",
                        str(resolve_context(args.ledger, config_path).ledger),
                    ]
                )
            ],
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except service.FixmeError as error:
        print(
            json.dumps({"status": "rejected", "error": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
