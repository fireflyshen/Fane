from ir.ir import Order, Type
from package.config import Config
from package.parser.utils.utils import split_find_contains


class WechatAnalyser:
    def get_account_and_tags(self, o: Order, cfg: Config) -> tuple:

        ignore = False
        # 如果没有配置规则，返回事先配置的默认配置
        if cfg.wechat == None or cfg.wechat.rules == None or len(cfg.wechat.rules) == 0:
            return (
                ignore,
                cfg.default_minus_account,
                cfg.default_plus_account,
                {},
                [],
            )
        # 初始化默认账户FixMe
        res_minus = cfg.default_minus_account
        res_plus = cfg.default_plus_account
        extra_account = {}
        tags = []

        for r in cfg.wechat.rules:
            match = True
            sep = ","

            match_func = split_find_contains

            if r.separator != None:
                sep = r.separator

            if r.peer != None:
                match = match_func(r.peer, o.peer, sep, match)

            if r.tx_type != None:
                match = match_func(r.tx_type, o.tx_type_original, sep, match)

            if r.item != None:
                match = match_func(r.item, o.item, sep, match)

            if r.method != None:
                match = match_func(r.method, o.method, sep, match)

            if r.category != None:
                match = match_func(r.category, o.category, sep, match)

            if match:
                if r.ignore:
                    ignore = True
                    break
                if r.target_account != None:
                    if o.type == Type.RECV:
                        res_minus = r.target_account
                    else:
                        res_plus = r.target_account
                if r.method_account != None:
                    if o.type == Type.RECV:
                        res_plus = r.method_account
                    else:
                        res_minus = r.method_account
                # if r.pnl_account != None:
                #     extra_account = {Account.pnl_account: r.pnl_account}
                if r.tags != None:
                    tags = r.tags.split(sep)
            # 循环内匹配后检查退款
            if match and str.startswith(o.item, "退款"):
                return ignore, res_plus, res_minus, extra_account, tags

        # 循环结束后再判断是否退款（没有规则匹配的情况）
        if str.startswith(o.item, "退款"):
            return ignore, res_plus, res_minus, extra_account, tags

        return ignore, res_minus, res_plus, extra_account, tags
        # 获取对应的匹配函数
