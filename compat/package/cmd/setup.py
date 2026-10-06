"""Compatibility alias; implementation lives in fane.shared.setup."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.shared.setup")
