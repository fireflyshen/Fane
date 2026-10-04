"""Compatibility alias; implementation lives in fane.providers.wechat.types."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.providers.wechat.types")
