"""Compatibility alias; implementation lives in fane.ledger.snapshot."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.ledger.snapshot")
