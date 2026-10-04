"""Compatibility alias; implementation lives in fane.infrastructure.journal.router."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.infrastructure.journal.router")
