"""Compatibility alias; implementation lives in fane.core.results."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.core.results")
