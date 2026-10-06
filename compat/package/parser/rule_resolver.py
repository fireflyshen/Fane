"""Compatibility alias; implementation lives in fane.shared.rules."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.shared.rules")
