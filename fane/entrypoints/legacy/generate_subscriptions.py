"""Compatibility subscription CLI; installed users use fa subscriptions."""

import argparse
import datetime as dt
import sys
from pathlib import Path

from fane.application.subscriptions import SubscriptionService
from fane.config.ledger import resolve_context


def parse_args(argv, default_config):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=default_config)
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument(
        "--fane-config", type=Path, default=Path.home() / ".flow" / "config.yaml"
    )
    date_range = parser.add_mutually_exclusive_group()
    date_range.add_argument(
        "--month",
        help="generate one calendar month only, formatted as YYYY-MM",
    )
    date_range.add_argument(
        "--until",
        default=dt.date.today().strftime("%Y-%m-%d"),
        help="generate from each subscription start date until this date",
    )
    parser.add_argument("--write", action="store_true", help="append generated entries")
    parser.add_argument("--check", action="store_true", help="validate config only")
    return parser.parse_args(argv)


def main(argv=None, *, default_config=None) -> int:
    args = parse_args(
        sys.argv[1:] if argv is None else argv,
        default_config or Path.home() / ".flow/subscriptions.json",
    )
    try:
        context = resolve_context(args.ledger, args.fane_config)
        service = SubscriptionService(context.ledger, args.config)
        if args.check:
            result = service.check()
            print(f"Subscription config valid. subscriptions={result['subscriptions']}")
            return 0
        result = service.generate(
            month=args.month, until=None if args.month else args.until, write=args.write
        )
        for entry in result["entries"]:
            print(f"{entry['date']} {entry['subscription_id']} -> {entry['target']}")
        if not result["total"]:
            print("No subscription entries to generate.")
        elif not args.write:
            print("Dry run only. Re-run with --write to append these entries.")
        else:
            print(f"wrote {result['written']} entries")
        return 0
    except (ValueError, OSError) as error:
        print(f"Subscription generation failed: {error}", file=sys.stderr)
        return 1
