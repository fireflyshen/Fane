"""Compatibility alias; implementation lives in fane.application.repayments."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.application.repayments")
