# Fane

把支付宝、微信账单变成 Beancount，管理分类、订阅、账本与查询。入口是 `fa`。

```sh
uv tool install .
fa -c config/bill.local.yaml config init
fa -c config/bill.local.yaml config check
```

Python 3.11+，macOS/Linux。开发安装用 `uv pip install -e .`。
配置可以用 `fa -c PATH`，也可以一次设置：

```sh
export FANE_CONFIG=/path/to/fane.yaml
export FANE_LEDGER=/path/to/main.bean
```

常用命令：

```sh
fa convert -p wechat -s bill.xlsx
fa bill sync daily --write --json
fa classify extract | your-classifier | fa classify apply --write
fa sub generate --write
fa check
fa query 2026-09-01 2026-09-30
fa serve --host 127.0.0.1 --port 8080
```

命令可以通过 JSON/JSONL 组合。启用 shell 的 `pipefail` 可以传播前一步失败：

```sh
set -o pipefail
fa convert -p wechat -s bill.xlsx -f jsonl | fa ingest journal --write
```

新增的写入命令默认预览，`--write` 才修改账本；旧入口保持原行为。
`fa modules` 查看独立模块，`FANE_MODULES=query` 可以只启用查询。删除一个功能目录不会阻止其他功能。
查询兼容原 ledger-query 的 `/health` 和 `/query`，不调用 Flova。

| 需要什么 | 文档 |
| --- | --- |
| 安装与工作流 | [使用](docs/guide.md) |
| 全部参数与兼容命令 | [命令](docs/cli.md) |
| YAML、规则与订阅 | [配置](docs/config.md) |
| 目录和拆卸 | [模块](docs/modules.md) |
| rn 部署与 n8n | [自动化](docs/n8n.md) |
