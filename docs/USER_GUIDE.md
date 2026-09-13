# Fane 功能使用手册

## 1. 产品边界

Fane 把支付宝、微信导出的表格账单转换成 Beancount 分录。所有处理都在本机完成。

处理链路：

```text
账单文件 -> Provider -> 统一订单 IR -> YAML 规则 -> Beancount 模板 -> 输出或导入
```

当前支持：

| Provider | 输入 | 参数 |
|---|---|---|
| 支付宝 | CSV | `--provider alipay` |
| 微信 | XLSX | `--provider wechat` |

## 2. 命令总览

```text
fa init       创建最小配置
fa doctor     检查配置和规则，不处理账单
fa inspect    只读统计账单与待分类数量
fa trans      转换并输出到标准输出
fa import     转换并写入 Beancount journal
fa sync       按 jobs 配置增量处理多个账单来源
```

所有命令都可指定配置：

```bash
fa --config /path/to/config.yaml COMMAND
```

`--config/-c` 是全局参数，必须放在子命令之前。没有指定时使用
`~/.flow/config.yaml`。

## 3. 初始化与配置体检

### 3.1 创建配置

```bash
fa init
fa --config /custom/config.yaml init
```

如果文件已经存在，Fane 不会覆盖。只有明确确认时才使用：

```bash
fa --config /custom/config.yaml init --force
```

### 3.2 检查配置

```bash
fa doctor
fa --config /custom/config.yaml doctor
```

普通模式下，错误返回失败状态，警告只提示。这保证旧配置继续可用。若要在自动化中把
警告也视为失败：

```bash
fa doctor --strict
```

体检覆盖：

- YAML 和 Pydantic 类型错误；
- 拼错或未识别的字段；
- 缺失的默认账户、默认币种；
- 可能不合法的 Beancount 账户名；
- 金额区间上下界；
- 会匹配所有交易的空条件规则；
- 外币信用卡还款所引用的账本文件；
- 当前只为历史兼容保留、但不参与解析的规则字段。

`doctor` 不修改任何文件，也不会显示交易内容。

## 4. 基础配置

最小配置：

```yaml
title: Fane
default-minus-account: Assets:FIXME
default-plus-account: Expenses:FIXME
default-currency: CNY

alipay:
  rules: []

wechat:
  rules: []
```

未匹配的交易使用默认账户，因此不会直接丢失。推荐先使用 `FIXME`，通过
`inspect` 检查待分类数量，再补充规则。

## 5. 规则配置

### 5.1 基本规则

```yaml
alipay:
  rules:
    - peer: 中国移动
      target-account: Expenses:Utilities:Phone

    - method: 余额宝
      method-account: Assets:MMF:Alipay:YuEBao
```

`target-account` 表示交易去向，`method-account` 表示支付或收款账户。收入与退款会
按交易方向交换账户。

### 5.2 可用匹配字段

支付宝：

```text
peer note item category type method
time day-range timestamp-range min-price max-price
```

微信：

```text
peer item category tx_type method
time day-range timestamp-range min-price max-price
```

`min-amount`/`max-amount` 是 `min-price`/`max-price` 的兼容别名。

多个文本值可用 `separator` 分隔，默认是逗号：

```yaml
- peer: 星巴克,瑞幸
  separator: ","
  target-account: Expenses:Food:Coffee
```

文本匹配当前采用“包含”语义。历史字段 `full-match` 仍会被读取，但当前不改变匹配
方式；`doctor` 会明确提示，避免误认为它已经执行精确匹配。

### 5.3 金额和时间

```yaml
- timestamp-range: 2026-06-01..2026-06-30
  min-price: 100.00
  max-price: 200.00
  target-account: Expenses:Food:Groceries

- day-range: 15-16
  target-account: Expenses:Monthly:MidMonth

- time: 08:00..09:00
  target-account: Expenses:Transport:Bus
```

时间范围两端都包含。跨午夜时段也支持，例如 `23:00..02:00`。

### 5.4 标签和忽略

```yaml
- peer: 测试商户
  tags: work,reimbursable

- category: 不计收支
  ignore: true
```

`ignore: true` 会让匹配交易不进入输出，使用前应先通过 `trans` 或 `inspect` 验证。

### 5.5 规则顺序

普通交易会按 YAML 顺序检查全部规则；后面命中的账户设置可以覆盖前面的结果。
因此建议把通用规则放前面、具体规则放后面。`ignore` 命中后立即停止。

退款沿用历史兼容逻辑：首条命中规则处理后立即交换收支账户并返回。调整退款规则时应
使用真实脱敏样例做回归验证。

## 6. 只读检查账单

```bash
fa inspect --provider wechat --source bill.xlsx
fa inspect --provider wechat --source bill.xlsx --json
```

人类可读输出包含总数、支出、收入、待分类和月份分布。`--json` 适合脚本使用。

“待分类”表示最终仍使用默认正向或负向账户的交易。若某条规则有意设置回默认账户，它
也会被计入，这是偏保守的安全策略。

## 7. 转换输出

### 7.1 兼容 JSON（默认）

```bash
fa trans --provider alipay --source bill.csv
```

输出结构保持历史兼容：

```json
{"expense":{"08":["..."]},"income":{"08":["..."]}}
```

### 7.2 Beancount 文本

```bash
fa trans --provider alipay --source bill.csv --format beancount
```

### 7.3 JSONL

```bash
fa trans --provider wechat --source bill.xlsx --format jsonl
```

每行包含日期、月份、类型、指纹、Beancount 文本、来源和订单号，适合 UNIX 管道。

## 8. 导入账本

### 8.1 预览

```bash
fa import --provider wechat --source bill.xlsx \
  --journal-dir ~/.flow/account/journal --dry-run
```

`--dry-run` 输出计划写入的 JSONL，不创建 journal 或去重索引。

### 8.2 正式导入

```bash
fa import --provider wechat --source bill.xlsx \
  --journal-dir ~/.flow/account/journal
```

默认文件路由：

```text
支出 -> JOURNAL_DIR/YEAR/YEAR-MM.bean
收入 -> JOURNAL_DIR/YEAR/income.bean
```

标准输出保持兼容：

```json
{"written": 12, "skipped": 3}
```

### 8.3 安全选项

导入前把摘要写到标准错误，不污染机器读取的 JSON 标准输出：

```bash
fa import ... --summary
```

如果仍有待分类交易就拒绝写入：

```bash
fa import ... --require-classified
```

推荐日常组合：

```bash
fa import ... --summary --require-classified
```

### 8.4 去重

默认索引：

```text
JOURNAL_DIR/../.fane/imported.jsonl
```

自定义位置：

```bash
fa import ... --dedupe-index /path/to/imported.jsonl
```

平台订单号优先作为指纹；没有订单号时使用时间、金额、对方、商品和支付方式等字段生成
SHA-256。再次导入相同账单会计入 `skipped`。

`--force` 会绕过去重并可能产生重复分录，只应在明确修复历史数据时使用。

写入账本和去重索引后都会执行刷新与 `fsync`，降低系统异常造成的缓存数据丢失风险。

## 9. 自动同步任务

`sync` 把“找当天账单、判断文件是否变化、转换、去重、路由、写入、校验”收进 Fane，
用于替代外围的 `sed | jq | base64` 写入脚本。`trans` 和 `import` 的原有用法不受影响。

### 9.1 配置一个每日任务

下面的配置等价于常见的支付宝 CSV + 微信 XLSX 每日导入方式：

```yaml
jobs:
  daily:
    timezone: Asia/Shanghai
    journal-dir: /root/.flow/account/journal
    state-file: /root/.flow/account/.fane/sync-state.json
    lock-file: /root/.flow/account/.fane/sync.lock
    dedupe-index: /root/.flow/account/.fane/imported.jsonl
    on-missing: skip
    require-classified: true
    change-detection: sha256
    write-mode: append

    routing:
      expense: "{year}/{year}-{month}.bean"
      income: "{year}/income.bean"

    sources:
      - id: alipay-daily
        provider: alipay
        path: "/root/.flow/data/alipay/{date}.csv"

      - id: wechat-daily
        provider: wechat
        path: "/root/.flow/data/wechat/{date}.xlsx"

    validators:
      - command: ["make", "validate"]
        cwd: /root/.flow/account
        timeout-seconds: 300
```

`path` 支持 `{date}`、`{year}`、`{month}`、`{day}`。需要一次处理多个文件时，将
`path` 换成 `glob`，例如：

```yaml
glob: "/root/.flow/data/wechat/{year}-{month}-*.xlsx"
```

每个来源必须有唯一 `id`，并且只能配置 `path` 或 `glob` 其中一个。来源级
`on-missing` 可以覆盖任务级设置：`skip` 表示账单未到时正常跳过，`error` 表示失败。

路由变量包括 `{year}`、`{month}`、`{kind}`、`{provider}`。年份和月份来自交易日期，
不是脚本执行日期，因此跨年补录会写入正确年份。路由只能生成 `journal-dir` 内的相对
路径，不能使用绝对路径或 `..`。

### 9.2 运行、预演和补跑

```bash
# 使用任务时区中的今天
fa --config /root/.flow/bill.yaml sync daily

# 指定账单日期，适合补跑
fa --config /root/.flow/bill.yaml sync daily --date 2026-08-03

# 完整解析和分类，但不写 journal、索引或状态
fa --config /root/.flow/bill.yaml sync daily --date 2026-08-03 --dry-run

# 机器可读报告
fa --config /root/.flow/bill.yaml sync daily --date 2026-08-03 --json

# 忽略文件缓存重新解析；交易指纹去重仍生效
fa --config /root/.flow/bill.yaml sync daily --date 2026-08-03 --rescan
```

配置中的 `require-classified: true` 会阻止待分类交易写入。也可在某次运行中临时启用：

```bash
fa --config /root/.flow/bill.yaml sync daily --require-classified
```

### 9.3 增量、去重和失败恢复

`sync` 使用两层机制：

- 文件 SHA-256 用于快速跳过完全没变化的输入；
- 平台订单号或内容 SHA-256 形成交易指纹，保证账单文件增加新行后只追加新交易。

文件改名或 `--rescan` 不会绕过交易去重。状态只在账本写入和全部 `validators` 成功后
更新。如果写入、校验或状态保存失败，本次改动的 journal、去重索引和状态会恢复到
运行前。锁文件阻止 cron 重叠执行同一同步目录；如果账单在解析过程中仍被下载程序
改写，本次同步会停止，等待文件稳定后重跑即可。

`validators.command` 必须是参数数组，不通过 shell 展开；这既支持 `make validate`，也
避免字符串拼接带来的转义问题。任何非零退出码或超时都会让同步失败并回滚，默认超时
是 300 秒。

### 9.4 从现有 Bash 脚本迁移

配置并验证后，原脚本可缩减为：

```bash
#!/bin/bash
set -euo pipefail
cd /root/.flow
exec /root/.local/bin/fa -c /root/.flow/bill.yaml sync daily
```

安全切换顺序：

1. 运行 `fa -c /root/.flow/bill.yaml doctor`；
2. 对尚未导入的新日期运行 `sync daily --date YYYY-MM-DD --dry-run`；
3. 停用旧 Bash 的写入逻辑；
4. 从下一份未处理的账单开始正式运行 `sync`；
5. 确认一次正式运行和一次重复运行，后者应显示 `noop` 或全部去重。

不要让旧脚本和 `sync` 同时写账本。旧脚本写过的历史分录没有 Fane 交易指纹索引，
因此首次切换应从一份确定未写入的新账单开始；不要直接对历史文件批量运行 `sync`。

## 10. 外币信用卡还款

支付宝可配置来源特有的外币信用卡还款后处理：

```yaml
foreign-credit-card-repayments:
  - trigger-minus-account: Assets:MMF:Alipay:YuEBao
    trigger-plus-account: Assets:DebitCard:ICBC:4931
    liability-account: Liabilities:CreditCard:ICBC-USD
    ledger-file: /absolute/path/to/main.bean
    currency: USD
    peer: 工商银行
    item: 外币信用卡还款
```

Fane 会读取指定账本余额并补充对应还款分录。先运行 `doctor` 确认路径，再用
`trans --format beancount` 检查结果。

## 11. 常见问题

### 帮助命令提示配置不存在

新版已经允许在没有配置时执行所有 `--help`。若仍出现旧行为，先确认实际执行文件：

```bash
which fa
head -1 "$(which fa)"
```

源码调试时直接使用 `.venv/bin/python main.py`。

### 平台新增交易类型后导入失败

支付宝和微信会不定期增加状态或交易类型。错误信息会显示不支持的原始值；应先保留原始
账单，增加枚举和回归测试后再导入，不建议把未知类型直接忽略。

### `doctor` 报未知字段，但现有转换仍能运行

这是兼容设计：运行时保持 Pydantic 的历史宽松行为，`doctor` 负责把可能的拼写错误显式
暴露。确认字段确实是历史扩展时可继续使用；自动化可通过 `doctor --strict` 强制治理。

### `sync` 显示 unchanged，但我想重新解析

使用 `--rescan`。它只绕过文件 SHA-256 缓存，不会绕过交易指纹，因此不会因为重新解析
直接重复追加。如果确实要重复写入，仍应使用单文件 `import --force`，并先备份账本。

### 校验失败后为什么没有新分录

这是预期行为。`sync` 会回滚本次 journal 和索引改动，修复分类或校验错误后直接重跑
同一个日期即可。

## 12. 开发与验证

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q ir package provider tests
.venv/bin/python -m pip check
```

`tests/test_cli_tools.py` 和 `tests/test_sync.py` 是不依赖私人账单的版本化测试；
`example/` 存在时，还会运行本地支付宝/微信样例冒烟测试。
