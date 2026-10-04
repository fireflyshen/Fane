"""Compatibility alias; implementation lives in fane.infrastructure.journal.writer."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.infrastructure.journal.writer")
