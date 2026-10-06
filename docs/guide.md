# Fane 使用手册

这篇文档按一次实际记账流程解释 Fane。逐项参数见 [完整命令参考](cli.md)，文件字段见 [配置参考](config.md)，源码目录见 [项目目录与架构](modules.md)。

## 1. 命令设计：功能 → 命令组 → 动作

统一格式：

```text
fa [全局参数] <命令组> <动作> [动作参数]
```

| 功能 | 命令 | 输出/写入行为 |
| --- | --- | --- |
| 初始化 Fane YAML | `fa config init` | 创建配置；覆盖必须 `--force` |
| 配置诊断 | `fa config check` | 只读；`--strict` 将警告也视为失败 |
| 查看账单来源 | `fa providers list` | 当前支持 alipay、wechat |
| 转换账单 | `fa bill convert` | Beancount / JSON / JSONL / 旧分组 JSON |
| 检查账单 | `fa bill inspect` | 条数、月份、未分类数量 |
| 单文件导入 | `fa bill import` | 默认去重后的 JSONL 预览；`--write` 写入 |
| 列出同步任务 | `fa bill jobs` | YAML 中配置的任务名 |
| 增量同步多个文件 | `fa bill sync JOB` | 默认预览；`--write` 更新账本及同步状态 |
| 分类决策格式 | `fa classify schema` | JSON Schema |
| 导出未分类分录 | `fa classify extract` | JSON，包含账户目录、交易和分录 ID |
| 应用外部分类结果 | `fa classify apply` | 默认 JSON 计划；`--write` 修改分录及规则 |
| 创建订阅计划 | `fa subscriptions init` | 创建暂停状态的 JSON 示例 |
| 检查订阅计划 | `fa subscriptions check` | 校验字段、账户、币种和 Beancount |
| 生成订阅分录 | `fa subscriptions generate` | 默认预览；`--write` 追加缺失月份并更新 include |
| 列出内置模板 | `fa template list` | 当前 normal.j2 |
| 查看/导出模板 | `fa template show` | 原文；`--output` 保存文件 |
| 查看模板变量 | `fa template fields` | 变量名与类型 |
| 检查模板 | `fa template check` | Jinja2 存在及语法检查 |
| 校验账本 | `fa ledger validate` | 只读业务校验及 Beancount 校验 |
| 余额断言 | `fa ledger assertions` | 默认预览；`--write` 写文件及 include |
| 本地快照 | `fa ledger export` | JSON；`--output` 保存文件 |
| 查看账本网页 | `fa ledger serve` | 启动 Fava 服务，前台运行 |
| 发布 R2 快照 | `fa ledger publish` | 执行远程发布，成功后替换当前快照对象 |

来源和输入文件没有隐含默认值：新 `bill convert/inspect/import` 都要求 `--provider` 和 `--source`。多文件工作流通过 YAML 的 `jobs` 表达，不再拼很多命令行参数。

## 2. 安装、配置位置与帮助

在仓库根目录安装：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
fa --version
fa --help
fa bill convert --help
```

网页和云发布分别安装可选依赖：

```sh
python -m pip install -e '.[web]'
python -m pip install -e '.[cloud]'
```

创建自己的配置：

```sh
fa --config config/bill.local.yaml config init
fa --config config/bill.local.yaml config check --json
```

然后设置环境变量，后续命令可以省略 `--config`：

```sh
export FANE_CONFIG="$PWD/config/bill.local.yaml"
```

优先级：`--config` > `FANE_CONFIG` > `~/.flow/config.yaml`。配置没有自动搜索仓库 `config/bill.yaml`。这份已有文件包含个人规则，应按自己的账户修改，不能假定直接可用。

账本入口优先级：动作 `--ledger` > `FANE_LEDGER` > 兼容 `BILLS_LEDGER` > YAML `ledger.file`。例如：

```sh
export FANE_LEDGER="/path/to/Bills/main.bean"
fa ledger validate
```

帮助、版本、来源列表、模板命令、分类 Schema、初始化命令不要求已有有效 YAML。账单转换及同步要求有效 YAML；账本命令要求可定位的 Beancount 入口。显式指定不存在的配置文件时，账本命令会拒绝继续。

## 3. 从账单到账本

### 3.1 输入文件

支付宝使用官方导出的 CSV，自动查找包含“交易时间”的表头，支持 UTF-8、GBK、GB18030 等编码。必需列：交易时间、交易分类、交易订单号、商家订单号、交易对方、商品说明、对方账号、金额、收/支、交易状态、收/付款方式、备注。

微信使用 XLSX，在前 20 行搜索表头。必需列：交易时间、交易单号、商户单号、收/支、交易对方、商品、金额(元)、当前状态、支付方式、交易类型。微信 CSV 当前没有实现，不能只把后缀改成 XLSX。缺少列、未知枚举或无法解析的金额/日期会报错。

### 3.2 先检查，再转换

```sh
fa bill inspect --provider wechat --source /path/to/wechat.xlsx --json
fa bill convert --provider wechat --source /path/to/wechat.xlsx
fa bill convert --provider alipay --source /path/to/alipay.csv --output /tmp/alipay.bean
fa bill convert --provider wechat --source /path/to/wechat.xlsx --format json --output /tmp/entries.json
fa bill convert --provider wechat --source /path/to/wechat.xlsx --format jsonl
```

- `beancount`：默认，输出完整分录文本。
- `json`：数组；每项包含 `source_provider`、`source_file`、`order_id`、`date`、`month`、`kind`、`fingerprint`、`content`。
- `jsonl`：每行一项，同上，便于流式处理。
- `legacy-json`：历史 `expense` / `income` 按月份分组格式，仅用于旧消费者迁移。

JSON/JSONL 也包含渲染后的 `content`，因此依然需要可用模板。未匹配账户通常进入 `Assets:FIXME` / `Expenses:FIXME`，不是自动推断分类。`inspect` 的 unmatched 指使用默认账户的交易数量，expense/income 是上述文件分组数量；完整分类规则见配置参考。

### 3.3 单文件导入

```sh
# 预览：读取去重索引，不写账本、不写去重索引。
fa bill import --provider wechat --source /path/to/wechat.xlsx --journal-dir /path/to/Bills/journal --summary

# 严格导入：未分类交易会使本次失败。
fa bill import --provider wechat --source /path/to/wechat.xlsx --journal-dir /path/to/Bills/journal --require-classified --write
```

`kind=expense` 的分录写入 `journal/YYYY/YYYY-MM.bean`，`kind=income` 写入 `journal/YYYY/income.bean`，年份来自交易日期。当前历史分组仅把商品说明含“收益发放”的订单归入 income，其余归入 expense；它不等于完整财务收支判定。正式导入返回 `{"written": 1, "skipped": 0}`。重复导入依据来源订单号等生成的指纹跳过；再次预览已导入交易时，空计划没有 stdout 输出。`--force` 绕过去重，可能产生重复交易。

单文件导入不会自动更新 Beancount include，也不运行账本后置校验。应在账本年度 `index.bean` 中引用生成文件，再由主账本引用年度索引。需要多文件锁定、后置校验与回滚时用同步任务。

默认去重索引在账本外部的状态目录，见第 9 节。保留索引才能保持跨次导入的幂等性。

### 3.4 多来源增量同步

在 YAML 中追加：

```yaml
jobs:
  daily:
    timezone: Asia/Shanghai
    journal-dir: /path/to/Bills/journal
    require-classified: true
    sources:
      - id: alipay
        provider: alipay
        glob: /path/to/imports/alipay/*.csv
      - id: wechat
        provider: wechat
        glob: /path/to/imports/wechat/*.xlsx
    validators:
      - command: [fa, ledger, validate, --ledger, /path/to/Bills/main.bean]
```

```sh
fa bill jobs --json
fa bill sync daily --json
fa bill sync daily --date 2026-10-04 --json --write
fa bill sync daily --rescan --json --write
```

同步按文件 SHA-256 跳过未变文件，再按交易指纹去重；`--rescan` 跳过文件缓存，仍保留交易去重。报告中 `planned` 是拟写入数，`written` 是实际写入数；预览的 written 为 0。正式写入会持有任务锁，validator 失败时恢复本次交易文件、索引和状态。

`--date` 用于任务文件路径占位符 `{date}`、`{year}`、`{month}`、`{day}`，不是账单交易日期过滤。任务路径和路由写法详见配置参考。同步同样不创建账本 include；确保目标月份与 income 文件可被主账本加载。

## 4. tools 是什么，外部工具怎么调用

`tools/` 原本是源码目录中的独立终端脚本。现在功能在安装包内，统一通过以下命令调用：

```sh
fa classify schema
fa classify extract --ledger /path/to/Bills/main.bean --output /tmp/unclassified.json
fa classify apply --ledger /path/to/Bills/main.bean --input /tmp/decisions.json
fa classify apply --ledger /path/to/Bills/main.bean --input /tmp/decisions.json --write

fa subscriptions init
fa subscriptions check --ledger /path/to/Bills/main.bean
fa subscriptions generate --ledger /path/to/Bills/main.bean --month 2026-10 --json
fa subscriptions generate --ledger /path/to/Bills/main.bean --month 2026-10 --json --write
```

外部工具可以启动这些进程、传参数、读写 JSON；Shell、任务调度器和 AI 助手都可这样接入。Fane 没有 HTTP API 或 MCP 服务。分类功能没有 API key、模型选择或联网参数，因为它不负责请求模型。

### 4.1 分类输入输出流程

1. `extract` 扫描账本根目录 `journal/**/*.bean`，找出 FIXME/FixMe/Fix 占位分录，并读取 `accounts/data/*.bean` 的账户目录。
2. 人工或外部 AI 阅读导出 JSON 和 `schema`，生成 decisions JSON。必须保留导出的 posting_id；不要自己编造 ID。
3. `apply` 默认只检查和展示修改计划。加 `--write` 后替换账户、必要时新增费用/收入账户，并向 Fane YAML 追加来源分类规则。
4. 正式写入默认执行 `config check` 与 `ledger validate`，失败恢复本次修改的文件。

外部 AI 可以使用下面的任务说明：

```text
根据提供的 Fane extract JSON 与 decision JSON Schema，为每个 placeholder_postings
生成一条决策。优先已有账户，不修改日期、金额、支付方向和交易事实。
置信度不足或经济归属不明确时 action=defer 并说明原因。
apply 的 rule.match 至少包含两个当前交易的来源字段，其中必须有 peer 或 item；
只使用 allowed_rule_fields 中对应 provider 的字段和值，不使用分隔符或范围。
输出一个纯 JSON object：schema_version=1，decisions 数组；不要输出 Markdown。
```

既有费用账户的决策示意（posting_id 必须替换为导出结果中真实的 64 位值，匹配字段必须来自该交易）：

```json
{
  "schema_version": 1,
  "decisions": [
    {
      "posting_id": "<从 extract 复制真实 posting_id>",
      "action": "apply",
      "replacement_account": "Expenses:Food",
      "confidence": 0.99,
      "reason": "该笔为午餐费用",
      "new_account": null,
      "rule": {
        "provider": "wechat",
        "account_field": "target-account",
        "match": {"peer": "咖啡店", "item": "午餐"}
      }
    }
  ]
}
```

也可以通过 stdin 或 Base64 传输：

```sh
cat /tmp/decisions.json | fa classify apply --ledger /path/to/Bills/main.bean
fa classify apply --ledger /path/to/Bills/main.bean --input-base64 '<UTF-8 JSON 的 Base64>'
```

默认阈值 0.92；缺失/暂缓决策会拒绝整批应用，`--allow-partial` 才允许保留。交易变化后 posting_id 变化，旧结果会被拒绝。新增账户只允许 Expenses/Income；费用账户额外需要 `new_account.comment_zh`、`new_account.flux_label`，收入需要 comment_zh。文件结构及字段限制见配置参考和 `fa classify schema`。

注意：追加规则要求 YAML 有单独成行的 `alipay:` / `wechat:` 段与缩进列表；初始化生成的 `rules: []` 会自动展开。`wechat: {rules: [...]}` 等行内结构需先展开。

`--validator '命令 参数'` 可重复，替代默认账本校验；默认配置诊断仍保留，`--skip-config-check` 才跳过它。校验命令通过参数数组执行，不支持 Shell 管道/重定向。预览不运行后置校验。`ledger validate` 对未使用的 open 账户也会报错；应清理不用的账户，或在明确只需要 Beancount 检查时指定 `--validator 'bean-check /path/to/Bills/main.bean'`。

## 5. 订阅生成：固定计划，不是付款工具

订阅功能每月生成账本分录，不会支付费用，也不是后台定时服务。默认计划文件是当前 Fane YAML 同目录的 `subscriptions.json`，可用 `--subscriptions` 指定任意 JSON。

```sh
fa subscriptions init
# 编辑 JSON：账户必须已 open，币种必须是 operating_currency，status 改为 active。
fa subscriptions check --json
fa subscriptions generate --month 2026-10 --json
fa subscriptions generate --month 2026-10 --json --write
fa subscriptions generate --until 2026-10-04 --json
```

`--month` 只处理指定月份；`--until` 从每项 start_date 生成到指定日期（包含边界）；不指定二者则生成到本机今天。二者互斥。账单日超出当月天数会调整为月底，例如 31 日在 2 月变为 28/29 日。paused/cancelled 不生成。

重复运行按 `(subscription_id, period)` 跳过已生成分录，也识别同月同商户、说明、借方账户、金额和币种的旧分录。正式生成写入月度 journal，并更新年度及 journal 索引。主账本必须 include `journal/index.bean`；生成后加载检查失败或分录未被主账本引用，会恢复文件。

旧个人计划不会自动迁移，可显式指定：

```sh
fa subscriptions generate --subscriptions tools/auto_subscriptions.json --month 2026-10 --json
```

历史 `generated_by: "tools/generate_subscriptions.py"` 标记保留用于识别既有数据，并不意味着新入口依赖该脚本。当前分类应用、单文件导入与订阅生成没有跨进程写入锁，避免同时运行多个写入操作；同步任务有任务锁。

## 6. j2 在哪里，缺失时怎么办

`.j2` 是 Jinja2 模板文件的常用后缀。模板描述 Beancount 文本格式，Python 提供交易变量并渲染它。它不负责读取账单、分类或导入。

账单和订阅共用一个内置模板：`fane/shared/render/normal.j2`，并共用渲染入口。之前的 `package/template/normal.j2` 已移到这里。打包配置会将 `.j2` 放进 wheel；运行时通过包资源加载，因此从其他工作目录执行 `fa` 也能找到。

```sh
fa template list
fa template show
fa template fields --json
fa template show --output /tmp/my-normal.j2
fa template check --file /tmp/my-normal.j2
fa bill convert --provider wechat --source /path/to/wechat.xlsx --template /tmp/my-normal.j2
fa subscriptions generate --month 2026-10 --template /tmp/my-normal.j2 --json
```

长期开启可在 YAML 写 `template-file: templates/my-normal.j2`，账单和订阅同时读取这个配置，相对路径以 YAML 所在目录解析。本次 `--template` 优先于 YAML，YAML 优先于内置模板。账单 convert/inspect/import/sync 和 subscriptions generate 都支持覆盖模板。

常见变量：`pay_time` 日期时间、`peer` 商户、`item` 商品说明、`money` 金额、`currency` 币种、`plus_account`/`minus_account` 账户、`metadata` 字典、`tags` 列表；全量变量用 `template fields` 查看。内置模板还处理佣金及自定义记账字符串。`amount_precision` 默认 2，订阅为 null，保留配置的全部金额精度。`bean_quote` 过滤器按 Beancount 字符串规则转义引号、反斜杠和换行，`amount` 过滤器按指定精度输出数字。

订阅通过同一组变量传入商户、说明和账户，去重信息放在 `metadata` 中。自定义模板必须保留 `subscription_id`、`period` 等元数据；如果正式写入后无法识别订阅身份，Fane 会回滚这次写入。

```jinja2
{{ pay_time.strftime('%Y-%m-%d') }} * "{{ peer }}" "{{ item }}"
    {{ plus_account }} {{ money }} {{ currency }}
    {{ minus_account }} -{{ money }} {{ currency }}
```

上例仅用于理解变量；完整逻辑请从内置模板导出后修改。`template check` 检查 Jinja2 语法，不能证明实际渲染结果是合法 Beancount；修改后应转换真实示例并加载账本校验。未定义变量会在实际渲染时明确报错，可以用 template fields 核对变量名。

如果把内置 `.j2` 真正删掉，Fane 不会凭空生成模板。下一次加载会报缺失，需重新安装完整包、恢复模板，或指定可用的外部模板。源码目录中的 editable 安装直接读取源码模板；普通 wheel 安装读取安装位置的模板。

## 7. 账本工具

### 7.1 校验

```sh
fa ledger validate --ledger /path/to/Bills/main.bean
fa ledger validate --allow-ambiguous-account Assets:Internal:Transit
```

除了 Beancount 本身的错误，还检查主账本目录下未被 include 的 `.bean`、未使用的 open 账户、未 open 或晚于首次使用的账户、Fane 配置引用的未 open 账户、币种声明，以及 YAML 配置的账户段名和元数据策略。未使用账户检查默认就开启，因此“只有 open 的空账本”可能校验失败。

### 7.2 余额断言

```sh
fa ledger assertions --date 2026-10-01
fa ledger assertions --date 2026-10-01 --write --output assertions/2026-10.bean --index assertions/index.bean
```

断言为指定日期**日初**的资产/负债余额，不包含当天交易；默认明天。`--output` 和 `--index` 相对主账本目录解析，也可配置到 YAML。写入更新索引，但主账本仍需要引用 assertions 索引。`--include-internal` 允许包含配置 ignored-prefixes 原本排除的账户，`--precision` 覆盖小数位数。

### 7.3 快照和网页

```sh
fa ledger export --year 2026 --output /tmp/ledger-2026.json
fa ledger export --meta
fa ledger export --all --include-transactions --version local
fa ledger serve --host 127.0.0.1 --port 5000
```

export 默认所有年份；`--year`、`--meta`、`--all` 互斥。交易明细移除账本文件名/行号，仍包含实际财务内容。Fava 需要 web extra 或 `--executable /path/to/fava`。服务前台运行，按 Ctrl+C 结束。

### 7.4 云发布

```sh
# 按部署环境配置 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY，或 SDK 支持的凭据来源。
fa ledger publish --version '<源账本提交 SHA>' --endpoint 'https://<account>.r2.cloudflarestorage.com' --bucket '<bucket>'
```

需要 cloud extra。可用 `FANE_R2_ENDPOINT`、`FANE_R2_BUCKET`、`FANE_R2_KEY` 代替相应参数；默认快照对象 key 为 current.json。发布把完整快照写入单个对象（默认 current.json），对象替换成功后即成为当前快照；不会单独上传版本目录或指针文件。同一日期、相同账本版本和生成器版本自动跳过，否则先校验再发布；`--force` 强制重新发布。它没有预览开关，执行该命令即表示发布。

## 8. 外部脚本如何判断成功

```python
import json
import subprocess

result = subprocess.run(
    ["fa", "--config", "/path/to/bill.yaml", "bill", "inspect",
     "--provider", "wechat", "--source", "/path/to/wechat.xlsx", "--json"],
    capture_output=True, text=True, check=True,
)
summary = json.loads(result.stdout)
print(summary["total"], summary["unmatched"])
```

退出码 0 才解析成功结果；一般业务错误 1，CLI 参数错误 2；`classify apply` 拒绝或写入失败为 2，并将 JSON 错误写入 stderr。完整输出约定在命令参考末尾。

如果使用调度器，调度的命令应包含绝对配置路径、绝对输入路径或明确的 cwd，并使用已安装 `fa` 的虚拟环境路径。定时执行是外部任务调度器的职责，Fane 自己没有常驻调度器。

## 9. 路径和状态：避免混淆

| 路径 | 解析规则 |
| --- | --- |
| 全局 `--config`、账单 `--source`、CLI `--template`、单文件 `--journal-dir`、`--dedupe-index` | 相对当前工作目录 |
| CLI `--ledger` 或账本环境变量 | 相对当前工作目录 |
| YAML `ledger.file`、`template-file`、还款 `ledger-file` | 相对 YAML 目录 |
| YAML 同步任务中的 journal-dir/source/state/lock/dedupe/validator cwd | 相对当前工作目录；调度时建议绝对路径 |
| assertions 的 output/index | 相对主账本目录 |
| `--subscriptions`、分类 `--root`、分类 `--input`、普通 `--output` | 相对当前工作目录 |
| 默认订阅 JSON | YAML 同目录 subscriptions.json |
| 分类 root / 订阅 journal | 默认主账本所在目录 / 其 journal 子目录 |

导入/同步默认状态根目录：`FANE_STATE_HOME`，否则 `XDG_STATE_HOME/fane`，否则 `~/.local/state/fane`。下面按 journal 绝对路径的哈希区分账本；`FANE_STATE_NAMESPACE` 可指定固定子目录名。包含导入指纹、任务状态和锁。

旧账本 `.fane` 状态存在但新目录未迁移时，工具会拒绝导入并告知迁移目标；应迁移文件或显式设置路径，不要直接删除旧指纹后重导。账本搬家后路径哈希变化，也需要迁移原状态或使用固定 namespace。

## 10. 常见问题与迁移

| 现象 | 检查方法 |
| --- | --- |
| 找不到 fa | 激活安装它的虚拟环境，或执行该环境里的 `python -m fane` |
| 找不到配置 | `fa --config /绝对路径/bill.yaml config check`；默认不是仓库 YAML |
| 没有写入 | 新命令默认预览，正式操作加 `--write`；也可能全部已去重 |
| 账本校验失败但 Beancount 能打开 | 还有项目业务检查：未引用文件、未使用账户、币种/元数据/配置引用 |
| 分类 apply 拒绝 | posting_id 可能已过期、置信度不足、存在 defer/缺失，或自动规则过宽 |
| 订阅生成失败并恢复 | 账户/币种不匹配、主账本未 include journal 索引或新分录不合法 |
| 模板不存在 | `fa template list`；恢复安装资源或指定 `--template` |
| 改规则后同步没有变化 | `--rescan` 才重读未变文件；已导入交易仍会去重，不会重新分类历史分录 |

旧 `fa trans/import/sync/init/doctor/inspect` 仍可用，但保留历史默认值：尤其旧 import/sync 默认直接写入。新自动化应迁移到分组命令。旧脚本与新命令逐项映射见 [命令参考](cli.md#旧入口迁移)。
