import ast
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from fane.bootstrap import PROVIDER_SPECS, ProviderSpec, build_converter
from fane.config import Config
from fane.core.compiler import Compiler
from fane.core.models import IR, Order
from fane.entrypoints.cli import app

ROOT = Path(__file__).resolve().parents[1]


def fixture_order():
    return Order(
        pay_time=datetime(2026, 8, 2, 12),
        peer="Fixture",
        item="Fixture transaction",
        money=Decimal("12.34"),
        order_id="fixture-order",
    )


class FixtureProvider:
    def translate(self, filename):
        return IR(orders=[fixture_order()])


class FixtureAnalyser:
    def get_account_and_tags(self, order, config):
        return False, config.default_minus_account, config.default_plus_account, {}, []


class ArchitectureTest(unittest.TestCase):
    def test_dependencies_follow_layer_boundaries(self):
        allowed = {
            "core": {"core"},
            "config": {"config", "core"},
            "providers": {"providers", "core"},
            "application": {"application", "core", "config", "infrastructure"},
            "infrastructure": {"infrastructure", "core", "config"},
        }
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
                        if layer == "core":
                            self.assertNotIn(
                                name.split(".")[0],
                                {"typer", "pandas", "yaml", "jinja2", "beancount"},
                            )

    def test_core_import_does_not_load_concrete_adapters(self):
        code = (
            "import sys; from fane.core.conversion import ConversionService; "
            "assert not any(name in sys.modules for name in "
            "('pandas', 'yaml', 'jinja2', 'typer', 'fane.bootstrap'))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_custom_renderer_and_post_processor_need_no_core_changes(self):
        processed = []

        def post_process(ir):
            processed.append(True)
            ir.orders.append(fixture_order())
            return ir

        class Renderer:
            def render_order(self, order):
                return "expense", '2026-08-02 * "Fixture"\n'

        compiler = Compiler(
            "fixture",
            IR(orders=[fixture_order()]),
            Renderer(),
            lambda order: (False, "Assets:Cash", "Expenses:Test", {}, []),
            post_process,
        )
        output = io.StringIO()
        with redirect_stdout(output):
            first = compiler.build_result()
            second = compiler.build_result()
            entries = compiler.build_entries("virtual-source")
        self.assertEqual(first, second)
        self.assertEqual(len(entries), 2)
        self.assertEqual(len(processed), 1)
        self.assertEqual(output.getvalue(), "")

    def test_services_with_different_configs_are_isolated(self):
        specs = {"fixture": ProviderSpec(FixtureProvider, FixtureAnalyser)}
        first = build_converter(
            Config.model_validate({"default-minus-account": "Assets:First"}),
            specs=specs,
        )
        second = build_converter(
            Config.model_validate({"default-minus-account": "Assets:Second"}),
            specs=specs,
        )
        first_result = first.convert("fixture", "virtual")
        second_result = second.convert("fixture", "virtual")
        self.assertIn("Assets:First", first_result.entries[0].content)
        self.assertIn("Assets:Second", second_result.entries[0].content)
        self.assertNotIn(
            "Assets:Second", first.convert("fixture", "virtual").entries[0].content
        )
        self.assertEqual(first_result.summary()["unmatched"], 1)
        self.assertEqual(
            first_result.grouped()["expense"]["08"], [first_result.entries[0].content]
        )

    def test_cli_invocations_do_not_reuse_config_and_help_needs_no_config(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "bill"
            source.touch()
            with patch.dict(
                PROVIDER_SPECS,
                {"fixture": ProviderSpec(FixtureProvider, FixtureAnalyser)},
            ):
                for account in ("First", "Second"):
                    config = base / f"{account}.yaml"
                    config.write_text(f"default-minus-account: Assets:{account}\n")
                    result = runner.invoke(
                        app,
                        [
                            "--config",
                            str(config),
                            "trans",
                            "--provider",
                            "fixture",
                            "--source",
                            str(source),
                        ],
                    )
                    self.assertEqual(result.exit_code, 0, result.output)
                    entry = json.loads(result.stdout)["expense"]["08"][0]
                    self.assertIn(f"Assets:{account}", entry)
                missing = str(base / "missing.yaml")
                failed = runner.invoke(
                    app, ["--config", missing, "trans", "--source", str(source)]
                )
                self.assertNotEqual(failed.exit_code, 0)
                self.assertIn("找不到配置文件", failed.output)
                for command in ("trans", "sync", "inspect", "import", "ledger"):
                    help_result = runner.invoke(
                        app, ["--config", missing, command, "--help"]
                    )
                    self.assertEqual(help_result.exit_code, 0, help_result.output)

    def test_legacy_models_and_modules_share_identity(self):
        from fane.infrastructure.ledger import assertions
        from ir.ir import Order as LegacyOrder
        from package.ledger import assertions as legacy_assertions

        self.assertIs(LegacyOrder, Order)
        self.assertIs(legacy_assertions, assertions)


if __name__ == "__main__":
    unittest.main()
