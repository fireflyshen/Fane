"""Compatibility alias; implementation lives in fane.cli."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.cli")
