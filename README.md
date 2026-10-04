# Fane

Fane 把支付宝 CSV、微信 XLSX 账单转换成 Beancount 分录，并提供导入、增量同步、分类决策应用、月度订阅生成和账本管理。统一终端入口是 `fa`。

## 先看哪篇文档

| 你的问题 | 文档 |
| --- | --- |
| 怎么安装、怎么完成一次记账、外部工具怎么调用？ | [使用手册](docs/USER_GUIDE.md) |
| 每个功能的命令、所有参数和默认值是什么？ | [完整命令参考](docs/COMMANDS.md) |
| YAML、分类规则、订阅 JSON 怎么写？ | [配置参考](docs/CONFIG_REFERENCE.md) |
| 每个目录是什么、为什么分层、tools 和 j2 在哪里？ | [项目目录与架构](docs/PROJECT_GUIDE.md) |
| 服务器 n8n 怎样接入、去重、验证和回滚？ | [n8n 财务流程](docs/N8N_GUIDE.md) |

## 安装与开始使用

需要 Python 3.11 或更新版本；当前同步锁使用 POSIX 接口，运行环境为 macOS/Linux。在本仓库目录执行：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
fa --version

# 创建独立的本地配置，避免覆盖仓库已有的个人规则。
fa --config config/bill.local.yaml config init
fa --config config/bill.local.yaml config check
fa providers list
fa --config config/bill.local.yaml bill inspect --provider wechat --source /path/to/wechat.xlsx
fa --config config/bill.local.yaml bill convert --provider wechat --source /path/to/wechat.xlsx
```

也可使用 `python -m fane` 或 `python main.py`，后面的命令和参数完全相同。所有动作支持 `--help`，例如 `fa bill import --help`。全局 `--config` 必须放在命令组之前，也可用环境变量 `FANE_CONFIG`。

## 功能入口

```text
fa config         init / check
fa providers      list
fa bill           convert / inspect / import / jobs / sync
fa classify       schema / extract / apply
fa subscriptions  init / check / generate
fa template       list / show / fields / check
fa ledger         validate / assertions / export / serve / publish
```

新命令的导入、同步、分类应用、订阅生成和余额断言默认预览，加 `--write` 才修改账本。`config init`、`subscriptions init`、显式输出文件会直接创建文件；`ledger publish` 会直接发布到远程。

`tools/` 中的功能已经接入 `fa classify` 和 `fa subscriptions`，不需要下载源码里的脚本才能使用。它们可以被终端、自动化任务或外部 AI 工具通过进程调用；项目没有内置 AI 模型调用或 MCP 服务。

模板没有被删除：内置文件在 [`fane/infrastructure/rendering/normal.j2`](fane/infrastructure/rendering/normal.j2)，随安装包分发。`fa template show` 可以查看，`fa template show --output custom.j2` 可以导出，再通过 `bill convert --template custom.j2` 使用。

## 开发验证

```sh
python -m unittest discover -s tests -v
python -m compileall -q fane ir package provider tools tests
```

新代码放在 `fane/`。根目录的 `package/`、`provider/`、`ir/` 以及 `tools/*.py` 是历史兼容入口，详细职责见架构文档。
