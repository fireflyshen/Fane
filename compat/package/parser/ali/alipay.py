"""Compatibility alias; implementation lives in fane.bill.rules.alipay."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.bill.rules.alipay")
