"""Legacy analyser registry facade."""
from fane.bill.build import PROVIDER_SPECS, Analyser

ANALYSERS = {name: spec.analyser for name, spec in PROVIDER_SPECS.items()}


def create_analyser(provider_name: str) -> Analyser | None:
    factory = ANALYSERS.get(provider_name)
    return factory() if factory else None
