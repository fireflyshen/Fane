"""Compatibility alias; implementation lives in fane.entrypoints.cli.setup."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.entrypoints.cli.setup")
