"""Compatibility alias; implementation lives in fane.infrastructure.ledger.validation."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.infrastructure.ledger.validation")
