# 模块

```text
fane/
  cli.py              入口与本次调用上下文
  modules.py          延迟加载命令
  compat.py           旧 Python 路径别名
  shared/             公共数据类型、配置、模板、文件写入和校验
  bill/               支付宝/微信读取、转换、还款和同步
  classify/           提取与应用外部分类决策
  subscriptions/      订阅计划与月度分录
  ledger/             断言、快照、Fava 和云发布
  query/              日期范围查询、JSON 和 HTTP
  flow/               可拆卸自动化适配层，组合正式命令与报告状态
compat/               package、provider、ir 历史导入壳
config/               用户规则示例
tools/                历史脚本和既有个人订阅计划
tests/                回归、模块拆卸、查询契约和管道测试
docs/                 guide、cli、config、modules、n8n
```

每个功能目录包含自己的 `cli.py` 和业务代码。新增功能只需一个目录和 `modules.py` 的命令映射。
业务模块只能依赖本模块、公共底座，以及入口提供的调用上下文；不能导入其他业务模块。
`flow/` 是最外层的可选编排适配器，仅在执行组合操作时加载对应功能；业务模块和底座均不能依赖它。移除它不影响原有五个功能，移除某个业务模块只会使主动调用该功能的组合操作不可用。
公共底座不能依赖功能模块。入口只在执行指定命令时加载对应模块，根帮助和版本不加载业务模块。

`shared/` 是必需的运行底座。共享配置保持原 YAML 模型，模板继续只有一份 `normal.j2`，交易金额、指纹、日期、账户及默认写入约定保持不变。
共享不会变成功能间依赖：拆卸 `ledger/` 后，分类校验、订阅生成、账单还款、查询仍可运行。

## 拆卸

```sh
FANE_MODULES=query fa modules
FANE_MODULES=query fa query 2026-09-01 2026-09-30 --ledger main.bean
```

也可以从安装包或源码中移除任意功能目录。其他目录和公共底座不需要修改；缺失模块的命令给出明确错误。
模块选择在每次调用时生效。卸下 bill 后不会再提供账单转换；旧 Python 导入对应的已卸下功能也无法使用。
主动组合某个已卸下功能的管道会按退出码失败，使用 `set -o pipefail` 传播错误。

账单来源也按目录发现：移除 `bill/providers/alipay/` 不会阻止微信转换。
目前第三方依赖仍随完整 Fane 安装，避免改变既有安装习惯；模块禁用或删除不会调用这些依赖。

## 兼容

旧 `fa trans/import/sync/init/doctor` 的默认值保持原样，隐藏在根帮助中。
`package/provider/ir` 位于 `compat/`，由安装包提供旧导入名。
原 `fane.core/config/application/infrastructure/entrypoints` 路径通过别名转发；模块对象保持一致，无第二份业务实现。
源码开发先执行 `uv pip install -e .` 或 `pip install -e .`，使历史顶层导入名可用。

## 验证

```sh
FANE_STATE_HOME=/tmp/fane-test-state python -m unittest discover -s tests -v
python -m compileall -q fane compat tools tests
```

测试会实际复制公共底座并仅保留一个模块，逐个验证六个模块的独立工作；同时检查静态依赖边界、查询金额和 API、交易去重、模板、写入回滚及旧入口。
