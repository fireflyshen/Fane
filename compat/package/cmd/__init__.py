"""Compatibility entrypoint for older installations."""
from fane.cli import app


def __getattr__(name):
    from fane import cli
    return getattr(cli, name)

__all__ = ["app", "setup", "sync", "trans"]
