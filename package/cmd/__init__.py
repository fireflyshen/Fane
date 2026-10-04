"""Compatibility entrypoint for older installations."""
from fane.entrypoints.cli import app, setup, sync, trans

__all__ = ["app", "setup", "sync", "trans"]
