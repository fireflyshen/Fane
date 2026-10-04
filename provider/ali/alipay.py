"""Compatibility alias; implementation lives in fane.providers.alipay.reader."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.providers.alipay.reader")
