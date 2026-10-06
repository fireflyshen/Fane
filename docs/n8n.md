# n8n

服务器使用 `ssh rn`，界面为 <https://flow.caten.top>。
Fane 2.2.0 负责账本处理和查询，n8n 负责邮件、文件获取、流程与回调，Flova 0.4.1 负责迁移。

| 工作流 | 作用 |
| --- | --- |
| 账单入账 | 收件、下载、解密、导入、必要的 AI 分类、订阅与提交 |
| 账本更新 | GitHub 验签同步、月报调度、分析与邮件投递 |
| 账单问答 | Telegram 提问，原生 HTTP 工具直接查询 Fane |
| 屏幕时间周报 | 保留原有生活周报，当前未启用 |
| 执行告警 | 财务与生活流程共用的失败通知 |

## 分类与画布

2026-10-06 最终保留 5 个流程，财务从 8 个入口收敛为 3 个。
账单收件、账单文件并入账单入账；月报调度、财务月报并入账本更新；账本查询并入账单问答。
使用原生财务、生活、运维标签分类，另标注账单、月报、查询等用途。未启用周报保留未启用标签。
执行告警为发布的错误处理流程，没有定时或收件触发器。

主线从左到右，分支分行，模型与工具位于所属节点下方，异常处理单独放置。
章节便笺说明输入、处理和输出；泛化节点增加简短说明。
保留原收件、模型、邮件与 SSH 凭据；合并移除子流程转发，草稿与发布版本分别处理。
唯一工作流生成入口是 `workflows.py`，处理私有导出并可重复执行：

```bash
python integrations/n8n/workflows.py workflows-before.json workflows-new.json
```

已删除用户点名的 `Sub Bill analyze For Telegram` 和本次补发用的两个临时流程。
后续按用户授权删除 25 个冗余流程：5 个已合并旧入口、10 个空白占位、6 个测试、3 个未完成资讯模板及未启用生活助手模板。
生活助手模板没有执行记录，与现有屏幕时间周报无调用关系。
删除前数据库、导出、具体名单及部署校验保存在 `/var/backups/flow/n8n-simplify-20261006/`。
上一轮整理备份 `/var/backups/flow/n8n-organize-20261006/` 继续保留。

## 文件获取

没有独立下载和解压服务，也不再使用 `dflow`、Emlex、Oubliette 或 `flova finance`。
账单入账中的原生 IMAP 节点接收支付宝和微信账单，保留原凭据和邮件规则，并获取完整附件。
支付宝读取 ZIP；微信读取“点击下载”的 HTTPS 链接，用原生 HTTP 节点取得 ZIP。
下载和上传自动重试；失败沿用原 Telegram 告警。

压缩包先上传到私有 `state/bills/incoming/`，Python 标准库验证唯一 CSV/XLSX、大小和 CRC。
已知密码直接解密，缺少密码时由 Ubuntu 的 `fcrackzip` 和 `unzip` 恢复原有六位数字密码。
支付宝流式 ZIP 的头部适配只修改临时副本，账单原 ZIP 保持原字节。
解密完成并验证后，原子替换 `data/bills/{provider}/{date}.{csv,xlsx}`，再由 Fane 导入。

```bash
fa --config /root/.flow/config/fane.yaml bill sync daily --write --json
fa --config /root/.flow/config/fane.yaml classify extract --root /root/.flow/data/account
fa sub generate --ledger /root/.flow/data/account/main.bean --subscriptions /root/.flow/config/subscriptions.json --write --json
```

来源、模板、去重和分类仍由 Fane 决定。账单与回调共享文件锁，避免同步仓库时覆盖正在写入的账单。
日期使用 Asia/Shanghai。历史压缩包和去重状态保留；从失败执行重试或重新发送原邮件可以补处理。

SSH 节点只调用安装后的 `fa flow bill`、`fa flow sync`、`fa flow report`、`fa flow commit`。
解压代码属于 `fane/bill/archive.py`，编排与报告状态属于可拆卸的 `fane/flow/`，均随 Fane 安装包发布；不再单独复制 Python 脚本。
工具安装在 `/opt/flow`，系统入口在 `/usr/local/bin`；`.flow` 只保留配置、数据和状态。运维备份在 `/var/backups/flow`，缓存在 `/var/cache/flow`。启动和检查使用 `flova service start/check`。

```bash
fa flow report plan
printf '%s' '{"analysisMonth":"2026-09"}' | fa flow report prepare
```

导出中的草稿和发布版本分别修改，保留既有业务节点，不把草稿自动发布为生产版本。

## GitHub 回调

原地址仍为端口 `58129` 的 `/bills-webhook`，Caddy 转发到 n8n `/webhook/bills-sync`。
验签针对原始请求字节，密钥位于私有 `config/n8n-sync.json`；签名错误返回 401，JSON 错误返回 400，其他事件与分支返回 200 并忽略。
同步成功后在同一流程记录财务变化，立即回应 GitHub，不等待模型分析。
旧 `/webhook/bill-monthly-report` 验证回调仍保留，仅记录变化；`dryRun` 不写观察记录或发送邮件。
Fava 继续读取同一账本目录。当前同步由 GitHub push 回调承担，未发现启用的本地或服务器 Git 提交钩子。
原 `bill-webhook.service` 不再运行。

## 查询

`fane:2.1.0` 与 n8n 同属 `caddy_net`，账本只读挂载到 `/bills`，提供 `/health` 和 `/query`。

```bash
fa query 2026-09-01 2026-09-30 --ledger /root/.flow/data/account/main.bean
fa serve --ledger main.bean --host 127.0.0.1 --port 8080
```

旧 ledger-query 已停止，重启策略为 `no`，仅保留回退。
原查询草稿与发布版分别改为 `http://fane:8080/query`，响应与错误状态兼容。

私有备份：`/var/backups/flow/fane-20261005/` 保存查询切换前版本；`/var/backups/flow/services-20261005/` 保存本次工作流、配置、旧工具和验证结果。
回退应恢复对应工具、配置、工作流及发布版本，保持已有账本和去重状态，避免重放财务写入。

## 月度财务邮件

月报复用 Fane 查询引擎核算，模型只返回简短分析与结构化行动，HTML 和纯文本由固定模板生成。
栏目固定为收支概览、环比、全部支出分类、重点交易、关键洞察、上月复盘、下月计划和数据口径。
支出为退款后的净额；多币种分别列示，缺少上月数据不按零计算，结余不代表现金流或净资产。
复盘覆盖每条历史行动，资料不足项不计零分，同时展示已评估部分得分和权重覆盖率。
下月保留五条行动，金额或次数基线必须与完整账本科目核算结果一致。

每周导入和本地手工补账提交共用一条变化记录；银行卡、现金等已经记入主账本的交易同样参与核算。
首次月报需要月末之后收到有效账本更新；单纯日历翻月不会抢先发报告。
每 5 分钟检查一次，财务变化稳定 10 分钟后按月串行生成，一般在最后一次财务修改后 10–15 分钟发送。
比较规范化的交易日期、商户、科目、金额、币种、成本与权责口径；空格、注释、排版和备注修改不触发修订。
补账改变已发月份或其上月对比数据时，生成带版本号的修订邮件，并保留之前版本。
修订重算复盘，但保留原行动目标、权重及制定时基线，不重新创建已执行计划。
模型输出最多校验重试 3 次；始终不合格则停止并告警。
生成及发送前重新检查账本快照，保留月份原子领取与 FIXME 拦截。
发送前先持久化 `sending`，SMTP 接收回执确认后记录完成、行动与复盘；已开始发送但回执不明的任务不能自动重发。
邮件采用固定的 Notion 风格：暖灰页眉、摘要强调块、两列指标卡、支出占比条、行动标签和统一的章节图标。
使用表格布局、内联基础样式和窄屏增强，另附纯文本版本；即使邮件客户端移除样式块也可阅读。
媒体查询采用 [Gmail 官方支持的 CSS](https://developers.google.com/workspace/gmail/design/css)。

状态与核算位于 `fane/flow/report.py` 和 `snapshot.py`；提示词、邮件模板和工作流生成器位于 `integrations/n8n/`。代码以本地项目为唯一维护源，不新增服务。

```bash
python integrations/n8n/workflows.py workflows-before.json workflows-new.json
node integrations/n8n/test_report.js --preview
python -m unittest discover -s integrations/n8n -p test_monthly.py
```

生产调用 `fa flow report`，核算直接复用同一安装包中的账本查询函数。
工作流导出含私有配置，应仅保存到私有目录；草稿与发布版分别更新。
示例预览全部使用虚构数据。发布前验证首期/历史复盘、现有模型 JSON 输出及 320–1280 像素布局，不向真实收件人发送测试邮件。
流程优化回退材料保存在 `/var/backups/flow/report-20261006/`；样式调整前的草稿、发布版和数据库另存于 `/var/backups/flow/report-style-20261006/`。
配置 `monthly-report.json` 使用 `start_month` 和 `settle_seconds`（当前 600 秒）。
发送状态、规范化财务观察和修订历史保存在原有 `state/monthly-reports/reports.sqlite`，无需维护额外队列服务。
已开始投递但未确认的报告保留发送状态，应核实邮箱送达情况后人工恢复，避免重复邮件。

## 历史补发

2026-10-06 已补发 12 封邮件：2025-11 至 2026-09 的 11 份完整月报，以及截至 2026-10-06 的本月进度。
所有邮件均取得 SMTP 接收回执；回执代表邮件服务器接受，不代表收件箱分类。
账本中未来日期的预记条目不进入本次报告。本月进度与上月同期比较，行动尚不结算评分。
历史建议明确标为回顾建议，不冒充当时已有计划；既有行动表未改写。

历史补发已经完成，一次性工具仅保留在本地 `integrations/n8n/backfill.py`；服务器执行入口已移除。
私有批次保存在 `state/monthly-reports/backfill/20261006/`，包含冻结快照、报告和发送回执。
发送前先将状态写为 `sending`，收到回执后写为 `sent`；已发送或送达不确定的月份不能自动重发。
完整历史月份已记入正常月报完成记录；10 月进度不会占用完整 10 月月报，11 月仍可正常发送。
月报起始月份已扩展到 2025-11，后续调度依据完成记录去重。
