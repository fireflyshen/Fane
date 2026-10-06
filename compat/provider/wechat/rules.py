"""Compatibility alias; implementation lives in fane.shared.config.wechat."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("fane.shared.config.wechat")
