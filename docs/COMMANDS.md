# 完整命令与参数参考

本页从当前 CLI 注册结构生成，包含全部公开命令、参数、默认值和环境变量。使用流程见 [使用手册](USER_GUIDE.md)，YAML 与订阅字段见 [配置参考](CONFIG_REFERENCE.md)。

`fa --config PATH <命令组> <动作> [参数]`。`--config` 是全局参数，必须放在命令组前。所有命令都支持 `--help`。布尔开关默认不启用；显式写入由相应命令的 `--write` 控制。

## 全局参数

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--config, -c` | path | ~/.flow/config.yaml | Fane YAML 配置；全局选项，放在命令组之前 | FANE_CONFIG |
| `--version, -v` | boolean | 关闭 | version | — |
| `--install-completion` | boolean | 未指定 | Install completion for the current shell. | — |
| `--show-completion` | boolean | 未指定 | Show completion for the current shell, to copy it or customize the installation. | — |

## fa bill convert

只转换、不导入；默认输出 Beancount 文本。

```text
fa bill convert [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--provider, -p` | str | 必填 | 账单来源；用 fa providers list 查看 | — |
| `--source, -s` | path | 必填 | 账单 CSV/XLSX 文件 | — |
| `--format, -f` | beancount, json, jsonl, legacy-json | beancount | 输出格式 | — |
| `--output, -o` | str | - | 输出文件；- 表示 stdout | — |
| `--template` | path | 未指定 | 本次转换使用的自定义 Jinja2 模板 | — |

## fa bill import

预览导入计划；加 --write 才写入账本与去重索引。

```text
fa bill import [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--provider, -p` | str | 必填 | 账单来源；用 fa providers list 查看 | — |
| `--source, -s` | path | 必填 | 账单 CSV/XLSX 文件 | — |
| `--journal-dir` | path | 必填 | 账本的 journal 目录 | — |
| `--write` | boolean | 关闭 | 正式写入；默认仅预览 JSONL | — |
| `--dedupe-index` | str |  | 覆盖指纹索引位置 | — |
| `--force` | boolean | 关闭 | 绕过去重；可能写入重复交易 | — |
| `--require-classified` | boolean | 关闭 | 存在待分类交易时拒绝导入 | — |
| `--summary` | boolean | 关闭 | 向 stderr 打印检查摘要 | — |
| `--template` | path | 未指定 | 本次转换使用的自定义 Jinja2 模板 | — |

## fa bill inspect

只读检查条数、月份和待分类交易。

```text
fa bill inspect [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--provider, -p` | str | 必填 | 账单来源；用 fa providers list 查看 | — |
| `--source, -s` | path | 必填 | 账单 CSV/XLSX 文件 | — |
| `--json` | boolean | 关闭 | JSON 检查摘要 | — |
| `--template` | path | 未指定 | 本次转换使用的自定义 Jinja2 模板 | — |

## fa bill jobs

列出可传给 bill sync 的任务。

```text
fa bill jobs [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--json` | boolean | 关闭 | JSON 任务名称列表 | — |

## fa bill sync

按任务配置预览或增量同步多个来源。

```text
fa bill sync JOB [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `job` | str | 必填 | YAML 中 jobs 下的任务名称 | — |
| `--write` | boolean | 关闭 | 正式同步；默认仅预览 | — |
| `--date` | str |  | YYYY-MM-DD；默认任务时区的今天 | — |
| `--json` | boolean | 关闭 | JSON 同步报告 | — |
| `--rescan` | boolean | 关闭 | 忽略文件缓存，保留交易去重 | — |
| `--require-classified` | boolean | 关闭 | 存在待分类交易时拒绝写入 | — |
| `--template` | path | 未指定 | 本次转换使用的自定义 Jinja2 模板 | — |

## fa classify apply

检查决策；加 --write 后修改账本/配置，校验失败回滚。

```text
fa classify apply [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--ledger` | path | 未指定 | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file | — |
| `--root` | path | 未指定 | 扫描 journal/ 与 accounts/data/ 的账本根目录 | BILLS_ROOT |
| `--input, -i` | str | - | 决策 JSON 文件；默认 - 从 stdin 读取 | — |
| `--input-base64` | str | 未指定 | UTF-8 决策 JSON 的 Base64，与文件输入互斥 | — |
| `--write` | boolean | 关闭 | 正式修改账户并追加规则；默认仅预览 | — |
| `--min-confidence` | float range | 0.92 | 最低应用置信度 | — |
| `--allow-partial` | boolean | 关闭 | 允许保留缺失/暂缓的决策 | — |
| `--validator` | str（可重复） | 未指定 | 额外指定的校验命令，可重复；替代默认账本校验 | — |
| `--skip-config-check` | boolean | 关闭 | 跳过落盘后的配置诊断 | — |

## fa classify extract

只读导出占位账户分录、账户目录和来源字段。

```text
fa classify extract [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--ledger` | path | 未指定 | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file | — |
| `--root` | path | 未指定 | 扫描 journal/ 与 accounts/data/ 的账本根目录 | BILLS_ROOT |
| `--output, -o` | str | - | JSON 文件；- 表示 stdout | — |

## fa classify schema

输出外部 AI/人工决策所需的 JSON Schema；不调用模型。

```text
fa classify schema [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--output, -o` | str | - | 输出文件；- 表示 stdout | — |

## fa config check

检查配置、规则和关联路径；不修改文件。

```text
fa config check [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--strict` | boolean | 关闭 | 兼容性警告也视为失败 | — |
| `--json` | boolean | 关闭 | JSON 诊断报告 | — |

## fa config init

创建一份可直接修改的最小配置。

```text
fa config init [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--force` | boolean | 关闭 | 覆盖已经存在的配置文件 | — |

## fa ledger assertions

预览资产/负债账户的日初余额断言；--write 才写文件及 include。

```text
fa ledger assertions [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--ledger` | path | 未指定 | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file | — |
| `--date` | str | 未指定 | 断言日初余额，YYYY-MM-DD；默认明天 | — |
| `--write` | boolean | 关闭 | 写入输出文件并更新 include；默认仅预览 | — |
| `--output` | path | 未指定 | 断言文件；相对主账本目录 | — |
| `--index` | path | 未指定 | 写入 include 的索引文件；相对主账本目录 | — |
| `--include-internal` | boolean | 关闭 | 包含 ignored-prefixes 排除的账户 | — |
| `--precision` | int range | 未指定 | 小数位数；默认配置值，未配置时为 2 | — |

## fa ledger export

导出 JSON；默认所有年份。交易明细移除账本文件名和行号。

```text
fa ledger export [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--ledger` | path | 未指定 | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file | — |
| `--year` | int range | 未指定 | 仅导出指定年份；与 --meta/--all 互斥 | — |
| `--meta` | boolean | 关闭 | 只导出元信息；与 --year/--all 互斥 | — |
| `--all` | boolean | 关闭 | 显式导出所有年份（也是默认行为） | — |
| `--version` | str | local | 快照的源账本版本标识 | GITHUB_SHA |
| `--include-transactions` | boolean | 关闭 | 附加交易明细，移除文件名和行号 | — |
| `--output` | path | 未指定 | JSON 文件；默认 stdout，相对路径按当前目录 | — |

## fa ledger publish

校验并原子发布 R2 快照；相同账本及工具版本自动跳过。凭据用 AWS 环境变量。

```text
fa ledger publish [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--version` | str | 必填 | 源账本提交 SHA | — |
| `--endpoint` | str | 必填 | R2 的 S3 API 地址 | FANE_R2_ENDPOINT |
| `--bucket` | str | 必填 | 目标存储桶名称 | FANE_R2_BUCKET |
| `--ledger` | path | 未指定 | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file | — |
| `--key` | str | current.json | 当前快照指针的对象名 | FANE_R2_KEY |
| `--force` | boolean | 关闭 | 相同版本也重新发布 | — |
| `--generator-version` | str | 未指定 | 覆盖生成器版本；默认 Fane 版本 | — |

## fa ledger serve

使用已安装的 Fava 打开账本。

```text
fa ledger serve [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--ledger` | path | 未指定 | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file | — |
| `--executable` | str | 未指定 | 外部 Fava 可执行文件路径 | FAVA_EXECUTABLE |
| `--host` | str | 127.0.0.1 | 监听地址 | — |
| `--port` | int range | 5000 | 监听端口 | — |

## fa ledger validate

只读校验；失败返回非零退出码。

```text
fa ledger validate [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--ledger` | path | 未指定 | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file | — |
| `--allow-ambiguous-account` | str（可重复） | 未指定 | 允许指定账户含策略禁止的段名；可重复 | — |

## fa providers list

执行此功能。

```text
fa providers list [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--json` | boolean | 关闭 | JSON 来源名称列表 | — |

## fa subscriptions check

只读检查计划、账本、账户和币种。

```text
fa subscriptions check [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--ledger` | path | 未指定 | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file | — |
| `--subscriptions` | path | 未指定 | 订阅 JSON；默认 Fane YAML 同目录的 subscriptions.json | — |
| `--json` | boolean | 关闭 | JSON 检查结果 | — |

## fa subscriptions generate

生成缺少的月度分录；正式写入后检查账本，失败回滚。

```text
fa subscriptions generate [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--ledger` | path | 未指定 | 账本入口；也可用 FANE_LEDGER 或配置 ledger.file | — |
| `--subscriptions` | path | 未指定 | 订阅 JSON；默认 Fane YAML 同目录的 subscriptions.json | — |
| `--month` | str | 未指定 | 仅生成 YYYY-MM 指定月份 | — |
| `--until` | str | 未指定 | 从订阅起始日生成到 YYYY-MM-DD；默认本机今天 | — |
| `--write` | boolean | 关闭 | 正式追加分录并更新 include；默认仅预览 | — |
| `--json` | boolean | 关闭 | JSON 结果，包含每笔分录文本 | — |
| `--template` | path | 未指定 | 覆盖共享 Jinja2 模板；否则读取 YAML 的 template-file 或内置 normal.j2 | — |

## fa subscriptions init

创建暂停状态的示例订阅；修改账户并启用后使用。

```text
fa subscriptions init [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--output, -o` | path | 未指定 | 订阅 JSON 的创建位置 | — |
| `--force` | boolean | 关闭 | 覆盖已有计划文件 | — |

## fa template check

检查模板存在且 Jinja2 语法可编译；不修改文件。

```text
fa template check [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--name` | str | normal.j2 | 内置模板名称 | — |
| `--file` | path | 未指定 | 检查外部模板文件 | — |
| `--json` | boolean | 关闭 | JSON 检查报告 | — |

## fa template fields

列出可以在模板中使用的变量和类型。

```text
fa template fields [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--json` | boolean | 关闭 | JSON 模板变量列表 | — |

## fa template list

执行此功能。

```text
fa template list [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--json` | boolean | 关闭 | JSON 内置模板名称列表 | — |

## fa template show

显示模板原文，或用 --output 导出后修改。

```text
fa template show [OPTIONS]
```

| 参数 | 类型/取值 | 默认 | 作用 | 环境变量 |
| --- | --- | --- | --- | --- |
| `--name` | str | normal.j2 | 内置模板名称 | — |
| `--file` | path | 未指定 | 改为读取外部模板文件 | — |
| `--output, -o` | str | - | 输出文件；默认 stdout，可用于导出模板 | — |

## 输出与退出码

- 成功返回 `0`；无新增分录也属于成功。
- 参数缺失、无效枚举等由 CLI 返回 `2`。一般业务校验/文件错误返回 `1`。`classify apply` 拒绝决策或落盘后校验失败返回 `2`，JSON 错误写入 stderr。
- `bill convert --format json/jsonl`、`bill inspect --json`、`bill jobs --json`、`bill sync --json`、`config check --json`、`providers list --json`、`template list/fields/check --json`、`subscriptions check/generate --json` 可供程序解析。
- `classify extract/schema/apply` 本身输出 JSON。`bill import` 预览输出去重后的 JSONL，空计划无输出；正式写入输出 `{"written": n, "skipped": n}`。`ledger export` 输出 JSON。
- 预览不会运行写入后的校验命令；需要正式写入成功后才能确认最终账本有效。stdout 保存结果，stderr 保存错误；脚本应先检查退出码。

## 旧入口迁移

| 原入口 | 新入口 | 行为差别 |
| --- | --- | --- |
| `fa init` / `fa doctor` | `fa config init` / `fa config check` | 新检查支持 `--json` |
| `fa trans` | `fa bill convert` | 新默认 Beancount；旧默认分组 JSON。旧 JSON 用新 `--format legacy-json` |
| `fa inspect` | `fa bill inspect` | 新入口要求显式来源与文件 |
| `fa import` | `fa bill import` | 旧默认写入；新默认预览，正式使用 `--write`；新要求 `--journal-dir` |
| `fa sync JOB` | `fa bill sync JOB` | 旧默认写入；新默认预览，正式使用 `--write` |
| `python tools/ai_fixme.py extract/apply` | `fa classify extract/apply` | 新 apply 默认预览；决策格式用 `fa classify schema` |
| `python tools/generate_subscriptions.py` | `fa subscriptions generate` | 新默认读 YAML 同目录 subscriptions.json；原个人计划请显式传 `--subscriptions tools/auto_subscriptions.json` |

旧 CLI 命令仍保留原默认值并隐藏在一级帮助中。旧 `--toggle/-t` 是保留的无效果参数，不属于新设计。旧 `tools` 脚本仅供迁移，不建议新自动化继续使用。
