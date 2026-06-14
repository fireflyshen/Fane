from ir.ir import Account, Order
from package.config import Config
from package.parser.rule_resolver import (
    AccountResolutionTuple,
    ExtraAccountField,
    MatchField,
    RuleAccountResolver,
)

ALIPAY_RESOLVER = RuleAccountResolver(
    match_fields=(
        MatchField("peer", "peer"),
        MatchField("type", "type_original"),
        MatchField("item", "item"),
        MatchField("method", "method"),
        MatchField("category", "category"),
        MatchField("note", "note"),
    ),
    extra_account_fields=(ExtraAccountField("pnl_account", Account.pnl_account.value),),
)


class AlipayAnalyser:
    def get_account_and_tags(self, o: Order, cfg: Config) -> AccountResolutionTuple:

        if cfg.ali is None or cfg.ali.rules is None or len(cfg.ali.rules) == 0:
            return (
                False,
                cfg.default_minus_account,
                cfg.default_plus_account,
                {},
                [],
            )

        return ALIPAY_RESOLVER.resolve(
            o,
            cfg.ali.rules,
            cfg.default_minus_account,
            cfg.default_plus_account,
        ).as_tuple()
