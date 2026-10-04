#!/usr/bin/env python3
"""Compatibility launcher. Prefer fa classify extract/apply/schema."""

from fane.entrypoints.legacy.ai_fixme import main

if __name__ == "__main__":
    raise SystemExit(main())
