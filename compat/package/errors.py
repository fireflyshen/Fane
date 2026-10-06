"""Compatibility alias; implementation lives in fane.shared.errors."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.shared.errors")
