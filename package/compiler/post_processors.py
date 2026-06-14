from collections.abc import Callable

from ir.ir import IR
from package.config import Config

PostProcessor = Callable[[IR, Config], IR]


def _post_process_alipay(ir: IR, config: Config) -> IR:
    from provider.ali.processor import post_process

    return post_process(ir, config)


POST_PROCESSORS: dict[str, PostProcessor] = {
    "alipay": _post_process_alipay,
}


def apply_post_processor(provider_name: str, ir: IR, config: Config) -> IR:
    post_processor = POST_PROCESSORS.get(provider_name)
    if post_processor is None:
        return ir
    return post_processor(ir, config)
