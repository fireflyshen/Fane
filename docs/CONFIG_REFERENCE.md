# 配置与数据格式参考

CLI 参数见 [命令参考](COMMANDS.md)，实际操作见 [使用手册](USER_GUIDE.md)。本页说明 Fane YAML、订阅 JSON、外部分类 JSON 与环境变量。

## 1. 三种配置各管什么

| 文件 | 使用它的命令 | 内容 |
| --- | --- | --- |
| Fane YAML，`--config` 指定 | bill、config；ledger/classify/subscriptions 读取相关设置 | 账户规则、同步任务、账本位置、模板位置 |
| subscriptions.json | subscriptions check/generate | 固定月度计划，与账单来源无关 |
| decisions.json | classify apply | 外部人工/AI 对某批分录的决策，不是长期配置 |

最小 YAML 用 `fa config init` 创建。检查用 `fa config check --json`；严格检查加 `--strict`。命令行全局 --config 优先于 FANE_CONFIG，默认 ~/.flow/config.yaml。

## 2. Fane YAML 顶层

```yaml
title: My Bills
default-minus-account: Assets:FIXME
default-plus-account: Expenses:FIXME
default-currency: CNY

# 可选；相对当前 YAML 的目录。
# template-file: templates/my-normal.j2

alipay:
  rules:
    - method: 余额
      method-account: Assets:Cash:Alipay
    - peer: 示例餐厅
      target-account: Expenses:Food

wechat:
  rules:
    - method: 零钱
      method-account: Assets:Cash:WeChat
    - peer: 示例餐厅
      target-account: Expenses:Food

ledger:
  file: /path/to/Bills/main.bean
```

账户名必须对应主账本中的 open 声明；这里的账户只是示意。不要把用户自己的银行账户或账户名当成项目的内置默认值。

| 字段 | 默认 | 作用 |
| --- | --- | --- |
| default-minus-account | 未设置 | 未匹配的负数 posting 账户，初始化示例为 Assets:FIXME |
| default-plus-account | 未设置 | 未匹配的正数 posting 账户，初始化示例为 Expenses:FIXME |
| template-file | 未设置 | 外部 Jinja2 模板；相对 YAML 目录，`--template` 可覆盖 |
| alipay.rules / wechat.rules | 未设置 | 按来源配置分类规则列表 |
| jobs | 未设置 | 具名同步任务，用 `bill jobs` 查看 |
| ledger | 空设置 | 账本管理、分类、订阅的入口与策略 |
| foreign-credit-card-repayments | 未设置 | 支付宝外币信用卡还款扩展规则 |

以下顶层字段为历史模型兼容而保留：`title`、`default-currency`、`default-cash-account`、`default-position-account`、`default-commission-account`、`default-pnl-account`、`default-third-party-custody-account`。当前支付宝/微信 reader 生成 CNY 订单，title 不改变输出，default-currency 不执行汇率转换；其余默认特殊账户也没有在普通转换流程中自动填充。实际支付/费用账户请用 method-account/target-account，支付宝额外收益账户用规则 pnl-account。

顶层及来源规则中的未知字段会被模型忽略，config check 会给出警告；ledger 子设置禁止未知字段。避免依赖未识别字段实现行为。

## 3. 分类规则

### 3.1 匹配与顺序

规则从上往下遍历；同一规则的不同条件为 AND。同一字符串字段按 `separator`（默认逗号）拆成多个候选，候选为 OR，采用“候选是否包含于交易原字段”的子串匹配，不是正则或完整相等。

```yaml
wechat:
  rules:
    - peer: 餐厅,食堂
      item: 午餐
      min-price: 5
      max-price: 100
      time: '11:00..14:00'
      target-account: Expenses:Food
      tags: food,lunch
```

一条匹配规则可以只改支付账户，另一条再改费用账户。后面的匹配规则可以覆盖先前设置的同类账户或 tags。`ignore: true` 命中时跳过该交易并停止遍历。退款有历史处理：商品说明以“退款”开头时交换正负账户，并可能在匹配退款规则后提前返回。

不要添加没有条件的规则，除非确实需要匹配全部交易。`config check` 会警告。

### 3.2 可用条件

| 字段 | 支付宝 | 微信 | 说明 |
| --- | --- | --- | --- |
| peer | 有效 | 有效 | 交易对方 |
| item | 有效 | 有效 | 商品说明/商品 |
| method | 有效 | 有效 | 付款方式/支付方式 |
| category | 有效 | 模型支持，但当前微信导出不填该值 | 交易分类 |
| type | 有效 | 无效兼容字段 | 支付宝原始收/支字符串 |
| note | 有效 | 不支持 | 支付宝备注 |
| tx_type | 不支持 | 有效 | 微信交易类型，字段名含下划线 |
| time | 有效 | 有效 | 每日时间区间，如 09:00..18:00，支持跨午夜 22:00..02:00 |
| day-range | 有效 | 有效 | 每月日数，如 15..16、15-16 或单日 15，1..31 |
| timestamp-range | 有效 | 有效 | 日期时间区间，如 2026-10-01..2026-10-31；可省略一端 |
| min-price / min-amount | 有效 | 有效 | 最小金额，包含边界；两个名字为别名 |
| max-price / max-amount | 有效 | 有效 | 最大金额，包含边界；两个名字为别名 |

日期时间支持 YYYY-MM-DD、YYYY-MM-DD HH:MM、YYYY-MM-DD HH:MM:SS。日期作为结束边界时包含当日到 23:59:59。每日时段支持 HH:MM 和 HH:MM:SS；区间常用 `..` 分隔。

### 3.3 动作与兼容字段

| 字段 | 默认 | 作用 |
| --- | --- | --- |
| method-account | 未指定 | 支出时为负方支付账户，收入时为正方收款账户 |
| target-account | 未指定 | 支出时为正方费用账户，收入时为负方收入账户 |
| tags | 未指定 | 按 separator 拆分的标签字符串 |
| separator | `,` | 字符串候选和标签分隔符 |
| ignore | 未指定 | true 表示忽略该交易 |
| pnl-account | 未指定 | 支付宝额外收益账户；微信保留该字段但当前不使用 |
| status | 未指定 | 历史兼容，两个来源当前都不参与规则匹配 |
| full-match | 未指定 | 历史兼容，当前不参与匹配，不能开启完整相等匹配 |

无效兼容字段会在 config check 中警告；新配置应避免使用。分类导出的状态 metadata 仍可供人工阅读，不等于它可以成为自动规则条件。

## 4. 同步任务 jobs

```yaml
jobs:
  daily:
    timezone: Asia/Shanghai
    journal-dir: /path/to/Bills/journal
    on-missing: skip
    require-classified: true
    change-detection: sha256
    write-mode: append
    routing:
      expense: '{year}/{year}-{month}.bean'
      income: '{year}/income.bean'
    sources:
      - id: alipay
        provider: alipay
        path: '/path/to/imports/{date}-alipay.csv'
      - id: wechat
        provider: wechat
        glob: '/path/to/imports/{year}/{month}/*.xlsx'
        on-missing: error
    validators:
      - command: [fa, --config, /path/to/bill.yaml, ledger, validate, --ledger, /path/to/Bills/main.bean]
        cwd: /path/to/Bills
        timeout-seconds: 300
```

| 任务字段 | 必填/默认 | 说明 |
| --- | --- | --- |
| timezone | Asia/Shanghai | 未传 --date 时决定任务日期 |
| journal-dir | 必填 | journal 根目录 |
| sources | 必填 | 来源列表；单个来源字段见下表 |
| state-file | 未指定 | 覆盖文件级同步状态位置，默认外部状态目录 sync-state.json |
| lock-file | 未指定 | 覆盖任务锁，默认外部状态目录 sync.lock |
| dedupe-index | 未指定 | 覆盖交易指纹索引，默认外部状态目录 imported.jsonl |
| on-missing | skip | skip 或 error；来源可覆盖 |
| require-classified | false | 使用默认账户的交易导致同步失败；CLI 可以额外开启，不能关闭 YAML 已开启的约束 |
| change-detection | sha256 | sha256 或 none；none 每次重新解析但仍交易去重 |
| write-mode | append | 当前仅支持 append，不支持覆盖或删除历史分录 |
| routing.expense | `{year}/{year}-{month}.bean` | expense 类输出的相对路径 |
| routing.income | `{year}/income.bean` | income 类输出的相对路径 |
| validators | 空列表 | 正式写入后的校验命令；未配置就不会额外校验账本 |

| 来源字段 | 必填/默认 | 说明 |
| --- | --- | --- |
| id | 必填 | 任务内唯一来源 ID |
| provider | 必填 | alipay 或 wechat |
| path / glob | 恰好一个 | 单文件路径 / 通配路径；都支持日期占位符 |
| on-missing | 继承任务 | skip 或 error |

来源路径占位符使用**运行日期**：`{date}`=YYYY-MM-DD、`{year}`=四位、`{month}`/`{day}`=两位。路由占位符使用**交易日期**：`{year}`、`{month}`、`{kind}`、`{provider}`。路由必须留在 journal-dir 内，禁止绝对路径和 `..`。

任务中的相对路径按执行时的 cwd 解析，不相对 YAML；自动化建议使用绝对路径。validator 的 command 是参数数组，不是 Shell 字符串；cwd 不设置则继承 Fane 工作目录，超时默认 300 秒。

同步预览仍创建/打开外部任务锁文件，但不修改账本、指纹或同步状态。两个任务使用同一 journal 时默认共享锁、指纹和状态目录，状态通过任务及来源 ID 区分。

## 5. 账本 ledger

```yaml
ledger:
  file: /path/to/Bills/main.bean
  policy:
    required-currencies: [CNY]
    required-metadata:
      Expenses: [flux_label]
    disallowed-segments: [FIXME, FixMe, Temp]
    allowed-accounts: []
  assertions:
    output-dir: assertions
    index: assertions/index.bean
    ignored-prefixes: [Assets:Internal]
    precision: 2
    filename-template: '{date:%Y-%m}.bean'
  snapshot:
    accrual-offset-prefixes: [Assets:Prepaid, Liabilities:Accrued]
```

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| ledger.file | 未指定 | 主账本文件；相对 YAML 目录 |
| policy.required-currencies | 空列表 | 必须声明为 operating_currency 的币种 |
| policy.required-metadata | 空映射 | 指定账户前缀的 open 指令需要的 metadata 键 |
| policy.disallowed-segments | 空列表 | 禁止账户冒号分段中出现的名称，忽略大小写 |
| policy.allowed-accounts | 空列表 | 对指定账户豁免禁止段名检查；不豁免其他校验 |
| assertions.output-dir | 未指定 | --write 的默认输出目录；相对主账本目录 |
| assertions.index | 未指定 | --write 的默认 include 索引；相对主账本目录 |
| assertions.ignored-prefixes | 空列表 | 余额断言默认排除的账户前缀 |
| assertions.precision | 2 | 输出小数位，非负整数 |
| assertions.filename-template | `{date:%Y-%m}.bean` | 根据断言日生成文件名 |
| snapshot.accrual-offset-prefixes | 空列表 | 快照计算中使用的应计抵销账户前缀 |

账本验证本身还有固定检查：未 include 的本地 .bean、未使用 open、首次使用早于 open、配置账户未 open、使用币种未声明等。policy 为空不会关闭这些检查。

## 6. 外币信用卡还款

```yaml
foreign-credit-card-repayments:
  - trigger-minus-account: Assets:Bank:Checking
    trigger-plus-account: Assets:Transfer:Repayment
    liability-account: Liabilities:CreditCard:Foreign
    ledger-file: /path/to/Bills/main.bean
    currency: USD
    peer: 外币信用卡还款
    item: 美元账单结清
```

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| trigger-minus-account | 未指定 | 匹配已分类交易的负方账户 |
| trigger-plus-account | 未指定 | 匹配已分类交易的正方账户 |
| liability-account | 必填 | 目标外币负债账户 |
| ledger-file | 必填 | 查询余额的账本；相对 YAML 目录 |
| currency | USD | 查询及清偿的外币 |
| peer / item | 沿用原交易 | 生成补充分录的商户/说明 |

至少提供一个 trigger；两个都给时同时匹配。当前仅接入支付宝后处理；每次转换每条还款规则最多补充一笔，金额按账本外币余额的绝对值生成，总成本使用原始 CNY 金额。它不是任意外币换汇功能；使用前应确认该规则确实表示全额还款。

## 7. 月度订阅 JSON

用 `fa subscriptions init` 创建暂停示例。JSON 顶层是数组，每项一笔固定计划：

```json
[
  {
    "id": "music",
    "status": "active",
    "type": "expense",
    "interval": "monthly",
    "payee": "音乐服务",
    "narration": "月度订阅",
    "debit_account": "Expenses:Subscriptions",
    "credit_account": "Assets:Cash",
    "amount": "10.00",
    "currency": "CNY",
    "billing_day": 5,
    "start_date": "2026-01-01",
    "end_date": null
  }
]
```

| 字段 | 必填/默认 | 说明 |
| --- | --- | --- |
| id | 必填 | 文件内唯一非空字符串，用于月度去重；不要随意改 ID |
| status | active | active / paused / cancelled，后两种不生成 |
| type | expense | expense / transfer；expense 借方必须 Expenses，transfer 借方不能 Expenses |
| interval | monthly | 当前仅支持 monthly |
| payee | 必填 | 商户名称 |
| narration | 必填 | 分录说明 |
| debit_account | 必填 | 正数 posting 账户，兼容 expense_account |
| credit_account | 必填 | 负数 posting 账户，兼容 asset_account |
| amount | 必填 | 正的有限十进制数，推荐字符串避免浮点误差 |
| currency | 必填 | 已声明的 operating_currency |
| billing_day | 1 | 整数 1..31，短月份调整为月底；兼容 day_of_month |
| start_date | 必填 | YYYY-MM-DD，含边界 |
| end_date | null | 可选 YYYY-MM-DD，含边界且不早于 start_date |

所有计划（包括暂停的）都检查账户与币种。账户需要 open；写入时 Beancount 还会检查实际记账日期是否落在有效期间。

需要以下 include 链：

```text
Bills/main.bean                  include "journal/index.bean"
Bills/journal/index.bean         include "2026/index.bean"
Bills/journal/2026/index.bean     include "2026-10.bean"
Bills/journal/2026/2026-10.bean    实际分录
```

主账本与账户由你维护；生成器创建/更新最后三层。实际分录含 subscription_id、subscription_type、generated_by、period 元数据；period 为 YYYY-MM。

## 8. 分类决策 JSON

完整 Schema 用 `fa classify schema --output /tmp/decision.schema.json` 导出，安装资源位置是 `fane/application/ai-fixme-decision.schema.json`。不要手工维护另一个格式版本。

| 顶层/决策字段 | 说明 |
| --- | --- |
| schema_version | 当前必须 1 |
| decisions | 数组，每个 placeholder posting 一条 |
| posting_id | extract 给出的真实 64 位 ID，交易变化后失效 |
| action | apply 或 defer |
| reason | 非空理由，两种 action 都需要 |
| replacement_account | apply 的目标账户，不能仍为占位符 |
| confidence | apply 的 0..1 数字，默认应用阈值 0.92 |
| new_account | 已有账户用 null；新账户对象包含 comment_zh，费用还需 flux_label |
| rule.provider | alipay / wechat，必须与原交易一致 |
| rule.account_field | Assets 占位使用 method-account，其他占位使用 target-account |
| rule.match | 至少两个当前来源字段，必须有 peer 或 item；字段值必须与原交易一致 |

自动规则可用字段：支付宝 peer/item/category/type/method；微信 peer/item/category/tx_type/method；值不能为空、最长 200 字，不能有逗号、竖线或换行。自动分类不允许把不参与运行时匹配的 status、微信 type 写成规则。自动规则使用来源的完整原值，但未来匹配仍遵循现有子串规则语义。

新增账户仅 Expenses / Income；中文说明 1..80 字且无换行/分号，费用标签 1..40 字且无换行/双引号。账户文件是 `accounts/data/expenses.bean` 或 `income.bean`，需已存在且被主账本引用。扫描目录固定为 journal/ 与 accounts/data/，不扫描任意 include 树。`--root` 可以改变扫描根，但账本仍由 --ledger/配置决定，应保证两者对应。

Schema 描述外部工具的输出格式；apply 还检查账户存在、ID 是否当前有效、置信度、规则字段取值与覆盖情况等业务约束。默认任一缺失/defer 导致整批拒绝，--allow-partial 才应用已通过的部分。

## 9. 环境变量

| 环境变量 | 作用 |
| --- | --- |
| FANE_CONFIG | YAML 路径，被 --config 覆盖 |
| FANE_LEDGER | Beancount 主账本路径，被 --ledger 覆盖 |
| BILLS_LEDGER | 历史账本路径变量，优先级低于 FANE_LEDGER |
| BILLS_ROOT | classify 的扫描根，与 --root 对应 |
| FANE_STATE_HOME | 运行状态根目录 |
| XDG_STATE_HOME | 未设 FANE_STATE_HOME 时，使用此目录下 fane/ |
| FANE_STATE_NAMESPACE | 状态子目录名，默认 journal 绝对路径哈希 |
| FAVA_EXECUTABLE | ledger serve 的外部 Fava 程序 |
| GITHUB_SHA | ledger export 的默认 version，未设置为 local |
| FANE_R2_ENDPOINT | ledger publish 的 S3 API endpoint |
| FANE_R2_BUCKET | ledger publish 的存储桶 |
| FANE_R2_KEY | ledger publish 的对象 key，默认 current.json |
| AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN | 云 SDK 使用的凭据环境变量，不属于 YAML |

## 10. 当前行为边界

- `kind=income` 的历史路由判定仅针对商品说明包含“收益发放”的订单，其余进入 expense/月度文件。这是文件分组约定，不能把 inspect 中 expense/income 数量理解为完整的财务收支统计；实际收支看 posting 账户。
- 普通账单 reader 输出 CNY；外币还款属于专门扩展，default-currency 不负责货币转换。
- 单文件导入不更新 include；同步任务是否后置校验由 validators 配置决定。
- 默认状态不在账本仓库，换目录或机器时需保留并迁移指纹索引。
- Fane 不执行 AI 请求、订阅付款或后台调度；这些由外部工具发起。
