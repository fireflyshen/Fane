"""Compatibility alias; implementation lives in fane.infrastructure.ledger.snapshot."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.infrastructure.ledger.snapshot")
