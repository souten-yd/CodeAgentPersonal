import os
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class CtxSizeDeadlockRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmpdir.name, "model_db.db")
        self._db_patch = patch.object(main, "MODEL_DB_PATH", self._db_path)
        self._db_patch.start()
        conn = main._get_model_db()
        conn.close()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self._db_patch.stop()
        self._tmpdir.cleanup()

    def test_resolve_default_ctx_size_does_not_call_settings_get(self) -> None:
        with patch.object(main, "settings_get", side_effect=AssertionError("settings_get must not be called")):
            value = main._resolve_default_ctx_size()
        self.assertEqual(value, 16384)

    def test_critical_endpoints_respond_within_five_seconds(self) -> None:
        for path in ("/settings", "/models/db", "/system/summary", "/ensemble/vram"):
            started = time.perf_counter()
            response = self.client.get(path)
            elapsed = time.perf_counter() - started
            self.assertEqual(response.status_code, 200, path)
            self.assertLess(elapsed, 5.0, f"{path} took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
