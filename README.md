# Fane

Fane 是一个本地运行的账单转换器：读取支付宝 CSV、微信 XLSX，按照 YAML
规则映射 Beancount 账户，并输出或直接写入月度账本。

它不会替代 Beancount，也不会联网同步账单。它解决的是“第三方账单到规范分录”
这一步。

## 兼容性

现有命令和默认行为保持不变：

```bash
fa --config ~/.flow/config.yaml trans --provider alipay --source bill.csv
fa --config ~/.flow/config.yaml import --provider wechat --source bill.xlsx \
  --journal-dir ~/.flow/account/journal
```

- `trans` 默认仍输出原有的按支出/收入和月份分组的 JSON。
- `import` 默认仍将支出写入 `YEAR/YEAR-MM.bean`，收入写入
  `YEAR/income.bean`。
- 默认配置仍是 `~/.flow/config.yaml`。
- 原有 YAML 字段继续接受；`doctor` 只报告兼容性警告，不会修改配置。

## 安装

在源码目录创建虚拟环境并安装：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/fa --version
```

也可以继续直接运行源码入口：

```bash
.venv/bin/python main.py --help
```

## 五分钟开始

创建最小配置：

```bash
fa init
fa doctor
```

只读检查账单，不写文件：

```bash
fa inspect --provider alipay --source bill.csv
```

预览 Beancount：

```bash
fa trans --provider alipay --source bill.csv --format beancount
```

先 dry-run，再正式导入：

```bash
fa import --provider alipay --source bill.csv \
  --journal-dir ~/.flow/account/journal --dry-run

fa import --provider alipay --source bill.csv \
  --journal-dir ~/.flow/account/journal --summary --require-classified
```

已经有每日账单脚本时，可在配置中增加 `jobs`，让 Fane 自己完成多来源增量导入：

```bash
fa --config ~/.flow/bill.yaml sync daily --dry-run
fa --config ~/.flow/bill.yaml sync daily
```

`sync` 提供文件变化检测、交易指纹去重、按交易日期路由、并发锁、失败回滚和账本校验；
完整配置及从现有 Bash 脚本迁移的方法见功能使用手册第 9 节。

完整命令、规则字段、输出格式、去重与兼容说明见
[功能使用手册](docs/USER_GUIDE.md)。项目内部架构见
[项目导览](docs/PROJECT_GUIDE.md)。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q ir package provider tests
```

`example/` 是本地账单目录，不进入 Git；测试在它存在时执行额外冒烟验证，不存在时
自动跳过，版本化单元测试仍会正常运行。
