"""Legacy post-processing facade."""
from collections.abc import Callable

from fane.bill.build import PROVIDER_SPECS
from fane.shared.config import Config
from fane.shared.models import IR

PostProcessor = Callable[[IR, Config], IR]
POST_PROCESSORS = {name: spec.post_processor for name, spec in PROVIDER_SPECS.items() if spec.post_processor}


def apply_post_processor(provider_name: str, ir: IR, config: Config) -> IR:
    processor = POST_PROCESSORS.get(provider_name)
    return processor(ir, config) if processor else ir
