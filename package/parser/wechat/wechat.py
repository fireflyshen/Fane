from ir.ir import Order
from package.config import Config
from package.parser.rule_resolver import MatchField, RuleAccountResolver

WECHAT_RESOLVER = RuleAccountResolver(
    match_fields=(
        MatchField("peer", "peer"),
        MatchField("tx_type", "tx_type_original"),
        MatchField("item", "item"),
        MatchField("method", "method"),
        MatchField("category", "category"),
    )
)


class WechatAnalyser:
    def get_account_and_tags(self, o: Order, cfg: Config) -> tuple:

        # 如果没有配置规则，返回事先配置的默认配置
        if cfg.wechat == None or cfg.wechat.rules == None or len(cfg.wechat.rules) == 0:
            return (
                False,
                cfg.default_minus_account,
                cfg.default_plus_account,
                {},
                [],
            )
        return WECHAT_RESOLVER.resolve(
            o,
            cfg.wechat.rules,
            cfg.default_minus_account,
            cfg.default_plus_account,
        ).as_tuple()
