#!/usr/bin/env python3
"""Compatibility launcher. Prefer fa subscriptions check/generate."""

from pathlib import Path

from fane.subscriptions.legacy import main

if __name__ == "__main__":
    raise SystemExit(
        main(default_config=Path(__file__).with_name("auto_subscriptions.json"))
    )
