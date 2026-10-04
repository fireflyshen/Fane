"""Legacy analyser registry facade."""
from fane.bootstrap import Analyser, PROVIDER_SPECS

ANALYSERS = {name: spec.analyser for name, spec in PROVIDER_SPECS.items()}


def create_analyser(provider_name: str) -> Analyser | None:
    factory = ANALYSERS.get(provider_name)
    return factory() if factory else None
