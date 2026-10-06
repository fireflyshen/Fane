# 命令参考

`fa --config PATH <命令> [参数]`；配置选项放在命令之前。所有命令支持 `--help`。账本写入默认预览，显式 `--write` 才写入；`flow` 按自动化操作执行。

## 全局参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--config, -c` | /Users/enmu/.flow/config.yaml | YAML 配置；放在命令之前；环境变量 FANE_CONFIG |
| `--version, -v` | False |  |
| `--install-completion` | None | Install completion for the current shell. |
| `--show-completion` | None | Show completion for the current shell, to copy it or customize the installation. |

## fa check

只读校验账本，失败返回非零退出码。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |

## fa convert

只转换、不导入；默认输出 Beancount 文本。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--provider, -p` | 必填 | 账单来源；用 fa providers list 查看 |
| `--source, -s` | 必填 | 账单 CSV/XLSX 文件 |
| `--format, -f` | beancount | 输出格式 |
| `--output, -o` | - | 输出文件；- 表示 stdout |
| `--template` | None | 本次转换使用的自定义 Jinja2 模板 |

## fa ingest

读取 convert --format jsonl 的结果，保持指纹去重和分录文本。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `journal` | 必填 | 目标 journal 目录 |
| `--input, -i` | - | JSONL 文件；- 读取 stdin |
| `--write` | False | 正式写入；默认预览 |
| `--dedupe-index` |  |  |

## fa query

输出含收支、转账及交易明细的 JSON；支持管道输入。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `start` | None | 起始日期 YYYY-MM-DD |
| `end` | None | 结束日期 YYYY-MM-DD |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--limit, -n` | 500 |  |
| `--input, -i` | None | JSON 请求文件；- 读取 stdin |
| `--output, -o` | - |  |

## fa serve

GET /health、POST /query；读取账本，接口与 ledger-query 兼容。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--host` | 127.0.0.1 |  |
| `--port` | 8080 |  |

## fa config init

创建一份可直接修改的最小配置。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--force` | False | 覆盖已经存在的配置文件 |

## fa config check

检查配置、规则和关联路径；不修改文件。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--strict` | False | 兼容性警告也视为失败 |
| `--json` | False | JSON 诊断报告 |

## fa template list



| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--json` | False | JSON 内置模板名称列表 |

## fa template show

显示模板原文，或用 --output 导出后修改。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--name` | normal.j2 | 内置模板名称 |
| `--file` | None | 改为读取外部模板文件 |
| `--output, -o` | - | 输出文件；默认 stdout，可用于导出模板 |

## fa template check

检查模板存在且 Jinja2 语法可编译；不修改文件。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--name` | normal.j2 | 内置模板名称 |
| `--file` | None | 检查外部模板文件 |
| `--json` | False | JSON 检查报告 |

## fa template fields

列出可以在模板中使用的变量和类型。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--json` | False | JSON 模板变量列表 |

## fa bill convert

只转换、不导入；默认输出 Beancount 文本。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--provider, -p` | 必填 | 账单来源；用 fa providers list 查看 |
| `--source, -s` | 必填 | 账单 CSV/XLSX 文件 |
| `--format, -f` | beancount | 输出格式 |
| `--output, -o` | - | 输出文件；- 表示 stdout |
| `--template` | None | 本次转换使用的自定义 Jinja2 模板 |

## fa bill inspect

只读检查条数、月份和待分类交易。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--provider, -p` | 必填 | 账单来源；用 fa providers list 查看 |
| `--source, -s` | 必填 | 账单 CSV/XLSX 文件 |
| `--json` | False | JSON 检查摘要 |
| `--template` | None | 本次转换使用的自定义 Jinja2 模板 |

## fa bill import

预览导入计划；加 --write 才写入账本与去重索引。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--provider, -p` | 必填 | 账单来源；用 fa providers list 查看 |
| `--source, -s` | 必填 | 账单 CSV/XLSX 文件 |
| `--journal-dir` | 必填 | 账本的 journal 目录 |
| `--write` | False | 正式写入；默认仅预览 JSONL |
| `--dedupe-index` |  | 覆盖指纹索引位置 |
| `--force` | False | 绕过去重；可能写入重复交易 |
| `--require-classified` | False | 存在待分类交易时拒绝导入 |
| `--summary` | False | 向 stderr 打印检查摘要 |
| `--template` | None | 本次转换使用的自定义 Jinja2 模板 |

## fa bill sync

按任务配置预览或增量同步多个来源。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `job` | 必填 | YAML 中 jobs 下的任务名称 |
| `--write` | False | 正式同步；默认仅预览 |
| `--date` |  | YYYY-MM-DD；默认任务时区的今天 |
| `--json` | False | JSON 同步报告 |
| `--rescan` | False | 忽略文件缓存，保留交易去重 |
| `--require-classified` | False | 存在待分类交易时拒绝写入 |
| `--template` | None | 本次转换使用的自定义 Jinja2 模板 |

## fa bill jobs

列出可传给 bill sync 的任务。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--json` | False | JSON 任务名称列表 |

## fa bill ingest

读取 convert --format jsonl 的结果，保持指纹去重和分录文本。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `journal` | 必填 | 目标 journal 目录 |
| `--input, -i` | - | JSONL 文件；- 读取 stdin |
| `--write` | False | 正式写入；默认预览 |
| `--dedupe-index` |  |  |

## fa providers list



| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--json` | False |  |

## fa classify schema

输出外部 AI/人工决策所需的 JSON Schema；不调用模型。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--output, -o` | - | 输出文件；- 表示 stdout |

## fa classify extract

只读导出占位账户分录、账户目录和来源字段。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--root` | None | 扫描 journal/ 与 accounts/data/ 的账本根目录；环境变量 BILLS_ROOT |
| `--output, -o` | - | JSON 文件；- 表示 stdout |

## fa classify apply

检查决策；加 --write 后修改账本/配置，校验失败回滚。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--root` | None | 扫描 journal/ 与 accounts/data/ 的账本根目录；环境变量 BILLS_ROOT |
| `--input, -i` | - | 决策 JSON 文件；默认 - 从 stdin 读取 |
| `--input-base64` | None | UTF-8 决策 JSON 的 Base64，与文件输入互斥 |
| `--write` | False | 正式修改账户并追加规则；默认仅预览 |
| `--min-confidence` | 0.92 | 最低应用置信度 |
| `--allow-partial` | False | 允许保留缺失/暂缓的决策 |
| `--validator` | None | 额外指定的校验命令，可重复；替代默认账本校验 |
| `--skip-config-check` | False | 跳过落盘后的配置诊断 |

## fa subscriptions init

创建暂停状态的示例订阅；修改账户并启用后使用。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--output, -o` | None | 订阅 JSON 的创建位置 |
| `--force` | False | 覆盖已有计划文件 |

## fa subscriptions check

只读检查计划、账本、账户和币种。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--subscriptions` | None | 订阅 JSON；默认 Fane YAML 同目录的 subscriptions.json |
| `--json` | False | JSON 检查结果 |

## fa subscriptions generate

生成缺少的月度分录；正式写入后检查账本，失败回滚。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--subscriptions` | None | 订阅 JSON；默认 Fane YAML 同目录的 subscriptions.json |
| `--month` | None | 仅生成 YYYY-MM 指定月份 |
| `--until` | None | 从订阅起始日生成到 YYYY-MM-DD；默认本机今天 |
| `--write` | False | 正式追加分录并更新 include；默认仅预览 |
| `--json` | False | JSON 结果，包含每笔分录文本 |
| `--template` | None | 本次使用的自定义 Jinja2 模板 |

## fa sub init

创建暂停状态的示例订阅；修改账户并启用后使用。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--output, -o` | None | 订阅 JSON 的创建位置 |
| `--force` | False | 覆盖已有计划文件 |

## fa sub check

只读检查计划、账本、账户和币种。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--subscriptions` | None | 订阅 JSON；默认 Fane YAML 同目录的 subscriptions.json |
| `--json` | False | JSON 检查结果 |

## fa sub generate

生成缺少的月度分录；正式写入后检查账本，失败回滚。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--subscriptions` | None | 订阅 JSON；默认 Fane YAML 同目录的 subscriptions.json |
| `--month` | None | 仅生成 YYYY-MM 指定月份 |
| `--until` | None | 从订阅起始日生成到 YYYY-MM-DD；默认本机今天 |
| `--write` | False | 正式追加分录并更新 include；默认仅预览 |
| `--json` | False | JSON 结果，包含每笔分录文本 |
| `--template` | None | 本次使用的自定义 Jinja2 模板 |

## fa ledger validate

只读校验；失败返回非零退出码。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--allow-ambiguous-account` | None | 允许指定账户含策略禁止的段名；可重复 |

## fa ledger assertions

预览资产/负债账户的日初余额断言；--write 才写文件及 include。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--date` | None | 断言日初余额，YYYY-MM-DD；默认明天 |
| `--write` | False | 写入输出文件并更新 include；默认仅预览 |
| `--output` | None | 断言文件；相对主账本目录 |
| `--index` | None | 写入 include 的索引文件；相对主账本目录 |
| `--include-internal` | False | 包含 ignored-prefixes 排除的账户 |
| `--precision` | None | 小数位数；默认配置值，未配置时为 2 |

## fa ledger export

导出 JSON；默认所有年份。交易明细移除账本文件名和行号。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--year` | None | 仅导出指定年份；与 --meta/--all 互斥 |
| `--meta` | False | 只导出元信息；与 --year/--all 互斥 |
| `--all` | False | 显式导出所有年份（也是默认行为） |
| `--version` | local | 快照的源账本版本标识；环境变量 GITHUB_SHA |
| `--include-transactions` | False | 附加交易明细，移除文件名和行号 |
| `--output` | None | JSON 文件；默认 stdout，相对路径按当前目录 |

## fa ledger serve

使用已安装的 Fava 打开账本。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--executable` | None | 外部 Fava 可执行文件路径；环境变量 FAVA_EXECUTABLE |
| `--host` | 127.0.0.1 | 监听地址 |
| `--port` | 5000 | 监听端口 |

## fa ledger publish

校验并原子发布 R2 快照；相同账本及工具版本自动跳过。凭据用 AWS 环境变量。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--version` | 必填 | 源账本提交 SHA |
| `--endpoint` | 必填 | R2 的 S3 API 地址；环境变量 FANE_R2_ENDPOINT |
| `--bucket` | 必填 | 目标存储桶名称；环境变量 FANE_R2_BUCKET |
| `--ledger` | None | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file |
| `--key` | current.json | 当前快照指针的对象名；环境变量 FANE_R2_KEY |
| `--force` | False | 相同版本也重新发布 |
| `--generator-version` | None | 覆盖生成器版本；默认 Fane 版本 |

## fa flow

账单入账、同步和报告操作共用的自动化入口。
| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--root` | /Users/enmu/.flow | 配置、数据和状态目录；环境变量 FANE_FLOW_ROOT |

## fa flow bill

prepare：解压、入账并提取分类；finish：应用分类与生成订阅。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `operation` | 必填 |  |
| `payload` |  |  |
| `--preview, --no-preview` | False |  |

## fa flow report

notice / plan / prepare / store / begin / sent / release / bootstrap。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `operation` | 必填 |  |
| `--request-base64` |  | 不提供时从 stdin 读取 JSON |
| `--dry-run, --no-dry-run` | False |  |

## fa flow sync

校验 GitHub 原始请求签名并同步账本；JSON 可从 stdin 输入。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `payload` |  |  |

## fa flow commit

提交入账结果，推送既有账本仓库，并通知月报检查。

无额外参数。

## 输出与流程契约

- `convert -f json/jsonl` 输出完整分录与去重指纹；`ingest` 原样导入这些分录。
- `bill sync --json` 输出任务、来源、计划/写入/去重计数；已处理文件不会重复写入。
- `classify extract` 输出 schema_version=1；`apply` 校验失败或回滚返回 2，JSON 错误写入 stderr。
- `query` 接受日期或 `--input` JSON；`serve` 提供 `GET /health`、`POST /query`。金额为十进制字符串，最多 366 天、500 条明细。
- `flow bill prepare` 接受 Base64 JSON 或 stdin；`finish` 接受 Base64 分类决策。返回的 ok、stage、payload、import、has_fixme 字段保持稳定。
- `flow report` 操作为 notice、plan、prepare、store、begin、sent、release、bootstrap；请求用 stdin 或 --request-base64，预览用 --dry-run。
- `flow sync` 接受 Base64 JSON 或 stdin，返回 status、message、report。
- `flow commit` 提交/推送账本并记录变化；在 n8n 的正常入账流程中使用。
- `flow --root PATH` 默认 ~/.flow，可用 FANE_FLOW_ROOT。流程的账单路径相对这个根目录，普通 bill sync 的相对路径仍按当前工作目录。
- `convert`、`ingest` 和 `sub` 是直接注册的简短入口，分别对应 bill convert、bill ingest、subscriptions。
- 成功返回 0；CLI 参数错误返回 2；一般业务错误返回 1。先检查退出码，再解析 stdout。

旧导入包、旧根命令、FANE_MODULES 和 legacy-json 已移除。现有 n8n 调用不使用它们。
