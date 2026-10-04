"""Compatibility alias; implementation lives in fane.config.wechat."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.config.wechat")
