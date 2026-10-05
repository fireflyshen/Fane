# n8n 财务流程

服务器：`ssh rn`。n8n：<https://flow.caten.top>。Fane 可执行文件：`/root/.local/bin/fa`。

当前检查：账单 12 节点版本和月报 13 节点版本均已发布。订阅计划仍须确认；部署状态不能证明订阅步骤能成功完成。

## 各工作流负责什么

| 工作流 | 作用 | 节点数（原 → 新） |
| --- | --- | --- |
| Bill flow | IMAP 接收支付宝、微信账单邮件，调用账单子流程 | 2 → 2 |
| Sub Bill Flow | 下载、解压、入账、按需分类、订阅记账和原有提交 | 22 → 12 |
| Bill analyze | 每月 8 日 9 点启动月报 | 2 → 2 |
| Sub Bill Analyze For Mail | 两个月对比分析、邮件、下月行动保存、上月行动评分 | 18 → 13 |
| 总结近期账单 | Telegram 提问，经原 Gemini 模型调用账本查询并回复 | 5 → 5 |
| 获取账单 | 校验查询参数并访问现有账本查询服务 | 3 → 3 |

未启用的实验流程没有删除。月报原模型、完整提示词、邮件收件人和数据表没有更换。

## 为什么还需要一个服务器脚本

服务器适配器现归属独立项目 Flova，由 `uv tool install 'flova[download]'` 安装，入口为 `flova finance`。
它只连接三个已有命令：下载工具 `dflow`、解压工具 `oub`、账本工具 `fa`。
它不包含密码、不调用 AI，也不包含账单转换器、Jinja2 模板或分类算法。
这些能力仍属于 Fane。n8n 不再每次解码 Base64 并覆盖安装整份分类脚本。

Flova 主体使用 Python 标准库，通过 uv 管理的独立环境运行。Fane 同样使用 uv tool 的独立环境。

## 账单链路

```text
账单邮件
  → 准备账单（SSH）
  → 检查结果 → 失败时按下载/解压/解析阶段发送原有 Telegram 告警
  → 有待分类交易？
       有 → 原 Gemini 分类 → 校验决策 JSON
       无 → 直接进入写入阶段
  → 应用分类、生成订阅（SSH）
  → 检查退出码及 JSON 成功标志
  → 原有账本提交节点
```

准备命令：

```bash
/root/.flow/runtime/bin/flova finance prepare
```

它读取 `/root/.flow/config/download.json` 的提供者配置，仍检查支付宝和微信。
下载成功同时要求进程退出码为零、JSON `status` 为 `success`。
解压先进入临时目录，确认产生非空目标文件，再替换当天 CSV/XLSX。
旧文件不会被误认为本次解压成功的结果。单个来源失败仍告警，另一个成功来源继续处理。

实际 Fane 入账命令：

```bash
/root/.local/bin/fa --config /root/.flow/config/fane.yaml bill sync daily --write --json
/root/.local/bin/fa --config /root/.flow/config/fane.yaml classify extract --root /root/.flow/data/account
```

`daily` 配置在服务器 `/root/.flow/config/fane.yaml`，来源为
`/root/.flow/data/bills/alipay/{date}.csv` 和 `/root/.flow/data/bills/wechat/{date}.xlsx`，
时区为 `Asia/Shanghai`，不存在的文件跳过，目标为 `/root/.flow/data/account/journal`。
按交易日期分年度、月份，收入仍进年度 `income.bean`。
“income”的识别沿用 Fane 的既有转换规则，不能据此推断所有收入都会进入该文件。

同步结束使用原先的 `docker exec fava bean-check /bean/main.bean` 校验。
同步失败回滚本次写入与状态。分类仍采用原来 0.92 门槛和完整批次校验，
低置信度或不完整决策不会静默应用。

写入阶段的入口：

```bash
/root/.flow/runtime/bin/flova finance finish \
  --subscriptions /root/.flow/config/subscriptions.json \
  --write --decisions-base64 'BASE64_JSON'
```

没有待分类交易时，传空字符串。分类使用：

```bash
/root/.local/bin/fa --config /root/.flow/config/fane.yaml classify apply \
  --root /root/.flow/data/account --input-base64 'BASE64_JSON' --write \
  --validator 'docker exec fava bean-check /bean/main.bean'
```

脚本退出码非零或返回 `ok: false` 时，n8n 停止后续提交。
已成功完成的入账不会因后续 AI 或订阅失败撤销；重试依靠交易去重和分类 posting ID 校验。
两次同时准备或同时写入会被锁拒绝，AI 等待期间的变化由 Fane 检测。

## 订阅配置与自动记账

2026-10-05 起，rn 的正式订阅计划统一位于 `/root/.flow/config/subscriptions.json`，
包含用户确认的三个每月计划：Google One Pro、Codex 和 Apple 礼品卡充值。
它属于服务配置，不放在账本数据仓库中。`Sub Bill Flow` 的
“应用分类并生成订阅”节点通过 `--subscriptions` 读取这一个文件，替代旧 `make subscriptions`。

执行流程会生成从各订阅 `start_date` 到服务器当天已经到期的分录；
尚未到扣款日的月份不会提前生成。没有待分类交易时，仍会检查订阅。
手动检查和预览：

```bash
fa --config /root/.flow/config/fane.yaml subscriptions check \
  --ledger /root/.flow/data/account/main.bean \
  --subscriptions /root/.flow/config/subscriptions.json --json

fa --config /root/.flow/config/fane.yaml subscriptions generate \
  --ledger /root/.flow/data/account/main.bean \
  --subscriptions /root/.flow/config/subscriptions.json \
  --until "$(date +%F)" --json
```

Fane 2.0.2 的账单和订阅共用 `normal.j2` 和渲染入口，统一使用 4 空格缩进、账户左对齐、金额右对齐和币种同列；
现有订阅只调整空白，不改变金额、日期或去重标记。
修改同一个 YAML `template-file` 会同时影响账单和订阅；`fa subscriptions generate --template` 可作单次覆盖，n8n 无需新增节点。

只生成账本分录，不执行支付或扣款。正式手动写入应使用上面的
`flova finance finish --write`，与 n8n 共用财务锁；不要并发运行直接的 `fa --write`。

同一 `subscription_id` 和 `period` 已经存在时跳过；配置中重复的 `id` 会被拒绝。
旧记录只有在月份、商户、说明、借方账户、金额和币种匹配时才自动识别。
金额不同的历史记录须先确认，不能假定已去重。此次按用户确认给七月、八月的
Apple 礼品卡充值补了订阅 ID 和月份，保留原日期和金额；九月已有标记。
修改金额或扣款日只影响尚未生成的月份，不会自动修改已有分录，订阅 ID 应保持稳定。
支付宝、微信导入的同一费用也不能保证被订阅识别，避免为同一扣费设置两个记账来源。

验证：账本副本首次生成 2 笔，第二次执行为 `noop`、新增 0 笔；真实 n8n SSH
预览和结果检查节点通过。演练未执行生产账本新增写入、通知或提交。

新增或暂停订阅只编辑这个 JSON 文件，`status` 支持 `active`、`paused`、`cancelled`。
字段定义见 [订阅配置](CONFIG_REFERENCE.md#7-月度订阅-json)。

## 去重和回滚兼容

状态位于 `/root/.flow/state/fane/n8n/`：

| 文件 | 内容 |
| --- | --- |
| imported.jsonl | 已入账交易指纹，不包含原始账单全文 |
| sync-state.json | 已处理来源文件的 SHA256 |
| sync.lock | Fane 同步锁 |

迁移从现有 Beancount 账本中的 `source` 和 `order_id` 建立 607 个唯一交易指纹。
不会把旧 `.md5` 标记直接视为所有交易均成功写入的证据。
最近两份账单共 12 笔的预览结果为新增 0 笔、跳过 12 笔。
新流程在同步及校验成功后继续更新旧 `.md5` 标记，方便回退旧流程而不立即重复入账。
不要删除去重索引；同一订单再次导入不会自动覆盖旧金额。

## 无副作用验证

```bash
/root/.flow/runtime/bin/flova finance prepare --offline --date 2026-10-03
```

这会读取现有文件、预览同步并提取待分类交易，不下载、不解压、不写入交易、
不调用 AI、不发送通知，也不提交推送。返回 JSON 可能含个人交易信息，不要公开粘贴全文。

`finish` 不加 `--write` 为预览；如果没有 `--subscriptions`，明确返回
`plan-path-required`，不会假装订阅配置已经存在。

真实 n8n 演练副本也应关闭 Telegram、AI 和提交节点，只运行这些预览命令。
本次没有对外发送邮件或 Telegram，也没有手动执行原有 Git 推送。

验证结果：67 个本地测试中，65 个通过、2 个既有测试跳过；账单演练在 n8n 中完成
真实 SSH、结果检查和无待分类分支；月报演练成功流转 5 项行动与 1 项历史评分。
演练替换了 AI、邮件和数据表写入节点，因此不代表已实测模型响应或邮件投递。
两份临时演练工作流已清理。

## 备份与恢复

历史材料已完整合并为 `/root/.flow/backups/recovery-history.tar.gz`，原目录已删除。包内 `n8n/fane-redesign-20261004/` 保存改造前的草稿、发布版和账本；`canonical-paths/` 保存本次统一路径前的数据库和配置文件。

恢复时只导入需要恢复的工作流。n8n CLI `import:workflow` 会停用导入的流程，随后需执行 `publish:workflow --id=工作流ID` 并重启 n8n。保留新的交易去重索引；不能盲目覆盖有新交易的账本。

账单工作流 ID：`3Wb33DhS6o6c2un7V-1z0`。月报工作流 ID：`-woXn2NFfexoVljeyJCQ-`。

目录说明、启动和整机迁移见 `/root/.flow/README.md`。
