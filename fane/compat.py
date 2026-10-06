"""Old import paths alias the actual modules; no duplicate implementations."""

import sys
from importlib import import_module
from importlib.abc import Loader, MetaPathFinder
from importlib.util import spec_from_loader
from types import ModuleType

ALIASES = {
    "fane.core": "fane.shared",
    "fane.config": "fane.shared.config",
    "fane.infrastructure.journal": "fane.shared.journal",
    "fane.infrastructure.rendering": "fane.shared.render",
    "fane.infrastructure.runtime": "fane.shared.runtime",
    "fane.infrastructure.ledger.balance": "fane.shared.balance",
    "fane.infrastructure.ledger.validation": "fane.shared.check",
    "fane.infrastructure.ledger": "fane.ledger",
    "fane.providers": "fane.bill.providers",
    "fane.application.classification": "fane.bill.rules",
    "fane.application.repayments": "fane.bill.repayments",
    "fane.application.sync": "fane.bill.sync",
    "fane.bootstrap": "fane.bill.build",
    "fane.application.fixme": "fane.classify.service",
    "fane.application.subscriptions": "fane.subscriptions.service",
    "fane.entrypoints.legacy.ai_fixme": "fane.classify.legacy",
    "fane.entrypoints.legacy.generate_subscriptions": "fane.subscriptions.legacy",
    "fane.entrypoints.cli.root": "fane.cli",
    "fane.entrypoints.cli.common": "fane.shared.output",
    "fane.entrypoints.cli.ledger": "fane.ledger.cli",
    "fane.entrypoints.cli.bill": "fane.bill.cli",
    "fane.entrypoints.cli.trans": "fane.bill.legacy",
    "fane.entrypoints.cli.sync": "fane.bill.jobs",
    "fane.entrypoints.cli.catalog": "fane.shared.catalog",
    "fane.entrypoints.cli.setup": "fane.shared.setup",
    "fane.entrypoints.cli.configuration": "fane.shared.settings",
    "fane.entrypoints.cli.classify": "fane.classify.cli",
    "fane.entrypoints.cli.subscriptions": "fane.subscriptions.cli",
    "fane.entrypoints.cli": "fane.cli",
}
NAMESPACES = {
    "fane.application",
    "fane.infrastructure",
    "fane.entrypoints",
    "fane.entrypoints.legacy",
    "fane.entrypoints.cli",
}


class Aliases(MetaPathFinder, Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in NAMESPACES:
            return spec_from_loader(fullname, self, is_package=True)
        for old in sorted(ALIASES, key=len, reverse=True):
            if fullname == old or fullname.startswith(old + "."):
                destination = ALIASES[old] + fullname[len(old) :]
                return spec_from_loader(fullname, AliasLoader(destination))
        return None

    def create_module(self, spec):
        module = ModuleType(spec.name)
        module.__path__ = []
        if spec.name == "fane.entrypoints.cli":
            module.__getattr__ = lambda name: getattr(import_module("fane.cli"), name)
        return module

    def exec_module(self, module):
        pass


class AliasLoader(Loader):
    def __init__(self, destination):
        self.destination = destination

    def create_module(self, spec):
        return import_module(self.destination)

    def exec_module(self, module):
        pass


def install():
    if not any(isinstance(finder, Aliases) for finder in sys.meta_path):
        sys.meta_path.insert(0, Aliases())
