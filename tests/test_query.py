import json
import threading
import unittest
from datetime import date
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from beancount import loader

from fane.query.engine import query_entries
from fane.query.http import create_server
from fane.query.service import LedgerService


class QueryTests(unittest.TestCase):
    def test_economic_totals_refunds_and_truncation(self):
        entries, errors, _ = loader.load_string("""2026-01-01 open Assets:Bank CNY
2026-01-01 open Income:Salary CNY
2026-01-01 open Expenses:Food CNY
2026-01-02 * "Salary"
  Assets:Bank 1000.00 CNY
  Income:Salary -1000.00 CNY
2026-01-03 * "Meal"
  Expenses:Food 25.50 CNY
  Assets:Bank -25.50 CNY
2026-01-04 * "Refund"
  Expenses:Food -5.50 CNY
  Assets:Bank 5.50 CNY
""")
        self.assertEqual(errors, [])
        result = query_entries(
            entries, date(2026, 1, 1), date(2026, 1, 31), max_transactions=1
        )
        self.assertEqual(result["totals"]["income"]["net"], {"CNY": "1000.00"})
        self.assertEqual(result["totals"]["expenses"]["net"], {"CNY": "20.00"})
        self.assertEqual(result["statistics"]["transaction_count"], 3)
        self.assertTrue(result["statistics"]["truncated"])

    def test_invalid_ranges_never_load_ledger(self):
        gateway = Mock()
        service = LedgerService(gateway)
        for payload in [
            {"start_date": "2026-01-02", "end_date": "2026-01-01"},
            {"start_date": "2025-01-01", "end_date": "2026-01-03"},
            {
                "start_date": "2026-01-01",
                "end_date": "2026-01-01",
                "max_transactions": True,
            },
        ]:
            with self.assertRaises(ValueError):
                service.execute(payload)
        gateway.query.assert_not_called()


class HttpTests(unittest.TestCase):
    def setUp(self):
        query = Mock()
        query.execute.return_value = {"schema_version": 1}
        self.query = query
        self.server = create_server("127.0.0.1", 0, query=query)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_health_and_query(self):
        with urlopen(self.url + "/health") as r:
            self.assertEqual(json.load(r), {"status": "ok"})
        with urlopen(
            Request(
                self.url + "/query",
                data=b"{}",
                headers={"Content-Type": "application/json"},
            )
        ) as r:
            self.assertEqual(json.load(r), {"schema_version": 1})

    def test_bad_body_returns_400(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url + "/query", data=b"not-json"))
        self.assertEqual(error.exception.code, 400)
        self.query.execute.assert_not_called()

    def test_failure_response_never_contains_exception_secret(self):
        self.query.execute.side_effect = RuntimeError("private-server-token")
        with self.assertLogs(level="ERROR"), self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url + "/query", data=b"{}"))
        self.assertEqual(error.exception.code, 500)
        self.assertNotIn(b"private-server-token", error.exception.read())
