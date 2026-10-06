import base64
import hashlib
import hmac
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fane.flow import sync


class WebhookTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = {
            "secret": "fixture",
            "branch": "main",
            "repository": str(self.root),
        }

    def request(self, body=b"{}", event="push", secret="fixture"):
        meta = {
            "body": base64.b64encode(body).decode(),
            "event": event,
            "signature": "sha256="
            + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
        }
        return sync.handle(meta, self.config, root=self.root)

    def test_invalid_signature_and_other_events_never_sync(self):
        with patch.object(sync.subprocess, "run") as run:
            self.assertEqual(self.request(secret="wrong")[0], 401)
            self.assertEqual(self.request(event="ping")[0], 200)
            self.assertEqual(self.request(b'{"ref":"refs/heads/dev"}')[0], 200)
        run.assert_not_called()

    def test_raw_body_is_verified_before_json_parse(self):
        with patch.object(sync.subprocess, "run") as run:
            self.assertEqual(self.request(b"broken")[0], 400)
            self.assertEqual(self.request(b"[]")[0], 400)
        run.assert_not_called()

    def test_concurrent_write_cannot_sync(self):
        lock = self.root / "state/locks/n8n-finance.lock"
        lock.parent.mkdir(parents=True)
        with lock.open("a") as handle, patch.object(sync.subprocess, "run") as run:
            sync.fcntl.flock(handle, sync.fcntl.LOCK_EX)
            self.assertEqual(self.request(b'{"ref":"refs/heads/main"}')[0], 409)
        run.assert_not_called()

    def test_failed_fetch_does_not_reset_or_trigger_report(self):
        with patch.object(
            sync.subprocess,
            "run",
            side_effect=[
                sync.subprocess.CompletedProcess([], 1),
                sync.subprocess.CompletedProcess([], 1),
            ],
        ) as run:
            self.assertEqual(
                self.request(b'{"ref":"refs/heads/main"}'), (500, "Deploy failed")
            )
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
