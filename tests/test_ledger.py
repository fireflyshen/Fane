import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from fane.ledger.assertions import calculate_balances, write_assertions
from fane.ledger.snapshot import export_snapshot
from fane.shared.check import validate_ledger
from fane.shared.config.ledger import Policy, resolve_context

LEDGER = """option "operating_currency" "EUR"
2000-01-01 open Assets:Wallet EUR
2000-01-01 open Expenses:Food EUR
2000-01-02 * "Fixture" "Dinner"
  Expenses:Food  12.34 EUR
  Assets:Wallet -12.34 EUR
"""


class LedgerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.ledger = self.root / "data" / "custom.bean"
        self.ledger.parent.mkdir()
        self.ledger.write_text(LEDGER)

    def cli(self, *args, env=None):
        return subprocess.run(
            [sys.executable, "-m", "fane", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **(env or {})},
        )

    def test_config_relative_location_survives_different_cwd_and_explicit_override(
        self,
    ):
        config = self.root / "settings.yaml"
        config.write_text("ledger:\n  file: data/custom.bean\n")
        ctx = resolve_context(config=config)
        self.assertEqual(ctx.ledger, self.ledger)
        result = self.cli("--config", str(config), "ledger", "export", "--meta")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["currencies"], ["EUR"])
        via_environment = self.cli(
            "ledger", "export", "--meta", env={"FANE_CONFIG": str(config)}
        )
        self.assertEqual(via_environment.returncode, 0, via_environment.stderr)
        self.assertEqual(json.loads(via_environment.stdout)["currencies"], ["EUR"])
        override = self.root / "other.bean"
        override.write_text(LEDGER.replace("EUR", "JPY"))
        self.assertEqual(resolve_context(override, config).ledger, override)

    def test_missing_config_help_and_explicit_ledger(self):
        self.assertEqual(self.cli("ledger", "--help").returncode, 0)
        result = self.cli("ledger", "validate", "--ledger", str(self.ledger))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli(
            "ledger", "export", "--ledger", str(self.ledger), "--all", "--year", "2000"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_no_ledger_location_is_not_guessed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Specify --ledger"):
                resolve_context()

    def test_policy_is_configurable_and_all_bean_includes_are_checked(self):
        policy = Policy(required_currencies={"JPY"})
        self.assertTrue(any("JPY" in x for x in validate_ledger(self.ledger, policy)))
        self.assertEqual(validate_ledger(self.ledger, Policy()), [])
        self.assertTrue(
            any(
                "Food" in x
                for x in validate_ledger(
                    self.ledger, Policy(disallowed_segments={"food"})
                )
            )
        )
        orphan = self.ledger.parent / "new-layer" / "orphan.bean"
        orphan.parent.mkdir()
        orphan.write_text("; not included\n")
        self.assertTrue(
            any("orphan.bean" in x for x in validate_ledger(self.ledger, Policy()))
        )

    def test_assertions_preview_does_not_write_and_write_uses_configured_destinations(
        self,
    ):
        config = self.root / "settings.yaml"
        config.write_text(
            "ledger:\n  file: data/custom.bean\n  assertions:\n    output-dir: checks\n    index: checks/includes.bean\n"
        )
        preview = self.cli(
            "--config", str(config), "ledger", "assertions", "--date", "2000-01-03"
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("-12.34 EUR", preview.stdout)
        self.assertFalse((self.ledger.parent / "checks").exists())
        written = self.cli(
            "--config",
            str(config),
            "ledger",
            "assertions",
            "--date",
            "2000-01-03",
            "--write",
        )
        self.assertEqual(written.returncode, 0, written.stderr)
        index = self.ledger.parent / "checks/includes.bean"
        self.assertEqual(index.read_text(), 'include "2000-01.bean"\n')

    def test_invalid_ledger_is_rejected_before_assertion_or_snapshot(self):
        self.ledger.write_text("not a ledger")
        with self.assertRaises(ValueError):
            calculate_balances(self.ledger, date(2000, 1, 3))
        with self.assertRaises(ValueError):
            export_snapshot(self.ledger)

    def test_assertion_write_rolls_back_if_index_update_fails(self):
        output, index = self.root / "balances.bean", self.root / "includes.bean"
        output.write_text("original output")
        index.write_text("original index")
        with patch(
            "fane.ledger.assertions.update_index", side_effect=OSError("failure")
        ):
            with self.assertRaises(OSError):
                write_assertions(output, index, "replacement")
        self.assertEqual(output.read_text(), "original output")
        self.assertEqual(index.read_text(), "original index")

    def test_import_runtime_state_stays_outside_ledger_and_legacy_is_not_ignored(self):
        from fane.shared.runtime import ensure_state_migrated, state_directory

        external = self.root / "external-state"
        with patch.dict(os.environ, {"FANE_STATE_HOME": str(external)}):
            location = (
                state_directory(self.ledger.parent / "journal") / "imported.jsonl"
            )
            self.assertTrue(location.is_relative_to(external))
            legacy = self.ledger.parent / ".fane/imported.jsonl"
            legacy.parent.mkdir()
            legacy.write_text("existing deduplication data")
            with self.assertRaises(Exception):
                ensure_state_migrated(self.ledger.parent / "journal", location)

    def test_serve_uses_fava_from_same_environment_without_path_dependency(self):
        from typer.testing import CliRunner

        from fane.cli import app

        entry = Mock()
        with patch("importlib.metadata.entry_points", return_value=[entry]):
            result = CliRunner().invoke(
                app, ["ledger", "serve", "--ledger", str(self.ledger), "--port", "8765"]
            )
        self.assertEqual(result.exit_code, 0, result.output)
        entry.load.return_value.assert_called_once_with(
            args=["--host", "127.0.0.1", "--port", "8765", str(self.ledger)],
            standalone_mode=False,
        )

    def test_snapshot_redacts_source_information(self):
        payload = export_snapshot(
            self.ledger, version="fixture", include_transactions=True
        )
        self.assertEqual(payload["version"], "fixture")
        transaction = payload["years"]["2000"]["days"][0]["transactions"][0]
        self.assertNotIn("source", transaction)
        self.assertNotIn("custom.bean", json.dumps(payload))

    def test_r2_publish_skips_unchanged_and_rejects_invalid_before_put(self):
        try:
            from botocore.exceptions import ClientError
        except ImportError:
            self.skipTest("cloud extra not installed")
        from fane.ledger.publishing import publish_snapshot

        client = Mock()
        kwargs = dict(
            ledger=self.ledger,
            policy=Policy(),
            config=None,
            bucket="fixture",
            key="snapshot.json",
            version="sha",
            generator_version="tool-sha",
        )
        client.head_object.return_value = {
            "Metadata": {
                "bills-version": "sha",
                "generator-version": "tool-sha",
                "as-of": date.today().isoformat(),
            }
        }
        self.assertFalse(publish_snapshot(client, **kwargs))
        client.put_object.assert_not_called()
        client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404"}}, "HeadObject"
        )
        self.assertTrue(publish_snapshot(client, **kwargs))
        self.assertEqual(
            json.loads(client.put_object.call_args.kwargs["Body"])["version"], "sha"
        )
        client.reset_mock()
        self.ledger.write_text("invalid ledger")
        with self.assertRaises(ValueError):
            publish_snapshot(client, force=True, **kwargs)
        client.put_object.assert_not_called()


if __name__ == "__main__":
    unittest.main()
