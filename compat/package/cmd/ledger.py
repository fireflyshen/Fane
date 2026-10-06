"""Compatibility alias; implementation lives in fane.ledger.cli."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.ledger.cli")
