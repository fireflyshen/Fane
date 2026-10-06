#!/usr/bin/env python3
"""Compatibility launcher. Prefer fa classify extract/apply/schema."""

from fane.classify.legacy import main

if __name__ == "__main__":
    raise SystemExit(main())
