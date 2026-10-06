"""Dependency boundaries and isolated invocations, using disposable bills."""

import ast
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from fane.bill.conversion import Converter
from fane.cli import app
from fane.shared.config import Config

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTest(unittest.TestCase):
    def test_features_do_not_import_siblings_or_the_cli_root(self):
        features = {"bill", "classify", "subscriptions", "ledger", "query", "flow"}
        allowed = {"shared": {"shared"}}
        allowed.update({name: {name, "shared", "version"} for name in features})
        allowed["flow"] |= features
        for path in (ROOT / "fane").rglob("*.py"):
            relative = path.relative_to(ROOT).with_suffix("")
            module = ".".join(relative.parts)
            layer = relative.parts[1] if len(relative.parts) > 2 else None
            for node in ast.walk(ast.parse(path.read_text())):
                imports = []
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    name = node.module or ""
                    if node.level:
                        package = (
                            module
                            if path.name == "__init__.py"
                            else module.rpartition(".")[0]
                        )
                        name = importlib.util.resolve_name(
                            "." * node.level + name, package
                        )
                    imports = [name]
                for name in imports:
                    with self.subTest(file=str(relative), dependency=name):
                        self.assertNotIn(
                            name.split(".")[0], {"package", "provider", "ir"}
                        )
                        if layer in allowed and name.startswith("fane."):
                            self.assertIn(name.split(".")[1], allowed[layer])

    def fixture(self, directory):
        source = directory / "bill.csv"
        source.write_text(
            "交易时间,交易分类,交易订单号,商家订单号,交易对方,商品说明,对方账号,金额,收/支,交易状态,收/付款方式,备注\n2026-08-02 12:00:00,餐饮,id,merchant,店,午餐,账号,12.34,支出,支付成功,余额,\n"
        )
        return source

    def test_converters_with_different_configs_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.fixture(Path(directory))
            first = Converter(
                Config.model_validate({"default-minus-account": "Assets:First"})
            )
            second = Converter(
                Config.model_validate({"default-minus-account": "Assets:Second"})
            )
            before = first.convert("alipay", str(source))
            self.assertIn(
                "Assets:Second",
                second.convert("alipay", str(source)).entries[0].content,
            )
            self.assertEqual(before, first.convert("alipay", str(source)))
            self.assertIn("Assets:First", before.entries[0].content)
            self.assertEqual(before.unmatched, 1)

    def test_cli_invocations_do_not_reuse_config(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = self.fixture(base)
            for account in ("First", "Second"):
                config = base / f"{account}.yaml"
                config.write_text(f"default-minus-account: Assets:{account}\n")
                result = runner.invoke(
                    app,
                    [
                        "-c",
                        str(config),
                        "convert",
                        "-p",
                        "alipay",
                        "-s",
                        str(source),
                        "-f",
                        "json",
                    ],
                )
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn(
                    f"Assets:{account}", json.loads(result.stdout)[0]["content"]
                )
            failed = runner.invoke(
                app,
                [
                    "-c",
                    str(base / "missing.yaml"),
                    "convert",
                    "-p",
                    "alipay",
                    "-s",
                    str(source),
                ],
            )
            self.assertNotEqual(failed.exit_code, 0)
            self.assertIn("找不到配置文件", failed.output)


if __name__ == "__main__":
    unittest.main()
