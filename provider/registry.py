"""Legacy provider registry facade; register new sources in fane.bootstrap."""
from fane.bootstrap import PROVIDER_SPECS, supported_provider_names
from fane.core.ports import Provider, ProviderFactory

PROVIDERS = {name: spec.reader for name, spec in PROVIDER_SPECS.items()}


def create_provider(provider_name: str) -> Provider | None:
    factory = PROVIDERS.get(provider_name)
    return factory() if factory else None
