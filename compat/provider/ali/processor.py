"""Compatibility alias; implementation lives in fane.bill.repayments."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.bill.repayments")
