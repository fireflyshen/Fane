"""Legacy provider registry facade; register new sources in fane.bill.build."""
from fane.bill.build import PROVIDER_SPECS
from fane.bill.build import supported_provider_names as supported_provider_names
from fane.shared.ports import Provider
from fane.shared.ports import ProviderFactory as ProviderFactory

PROVIDERS = {name: spec.reader for name, spec in PROVIDER_SPECS.items()}


def create_provider(provider_name: str) -> Provider | None:
    factory = PROVIDERS.get(provider_name)
    return factory() if factory else None

