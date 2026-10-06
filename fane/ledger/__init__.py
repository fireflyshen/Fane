"""Ledger tools and historical shared-adapter exports."""


def __getattr__(name):
    from importlib import import_module

    destinations = {"validation": "fane.shared.check", "balance": "fane.shared.balance"}
    if name not in destinations:
        raise AttributeError(name)
    return import_module(destinations[name])
