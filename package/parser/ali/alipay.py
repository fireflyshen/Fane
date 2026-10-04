"""Compatibility alias; implementation lives in fane.application.classification.alipay."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.application.classification.alipay")
