"""Compatibility alias; implementation lives in fane.infrastructure.runtime."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.infrastructure.runtime")
