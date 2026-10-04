"""Compatibility alias; implementation lives in fane.config.ledger."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.config.ledger")
