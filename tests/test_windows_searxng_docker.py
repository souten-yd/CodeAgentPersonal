from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestSettings(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = importlib.import_module("scripts.start_searxng_windows")

    def test_settings_generated_and_random_secret(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.mod.ensure_settings(Path(td))
            text = path.read_text(encoding="utf-8")
            self.assertIn('bind_address: "0.0.0.0"', text)
            self.assertIn("port: 8080", text)
            self.assertIn("- html", text)
            self.assertIn("- json", text)
            self.assertNotIn("ultrasecretkey", text)

    def test_ultrasecretkey_is_regenerated(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "secret_key").write_text("ultrasecretkey\n", encoding="utf-8")
            self.mod.ensure_settings(d)
            key = (d / "secret_key").read_text(encoding="utf-8").strip()
            self.assertNotEqual(key, "ultrasecretkey")

    def test_general_secret_key_is_migrated(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "settings.yml").write_text("general:\n  secret_key: keepme\n", encoding="utf-8")
            self.mod.ensure_settings(d)
            text = (d / "settings.yml").read_text(encoding="utf-8")
            self.assertIn('secret_key: "keepme"', text)
            self.assertIn("server:", text)


class TestDockerStartup(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = importlib.import_module("scripts.start_searxng_windows")

    @patch("scripts.start_searxng_windows._is_windows", return_value=True)
    @patch("scripts.start_searxng_windows._health_probe", return_value=(False, None, ""))
    @patch("scripts.start_searxng_windows.try_install_docker", return_value=True)
    @patch("scripts.start_searxng_windows._run")
    def test_docker_missing_tries_install(self, m_run: MagicMock, *_):
        m_run.side_effect = [MagicMock(returncode=1), MagicMock(returncode=0), MagicMock(returncode=0), MagicMock(returncode=1), MagicMock(returncode=0)] + [MagicMock(returncode=0)]*70
        self.assertEqual(self.mod.main(), 0)

    @patch("scripts.start_searxng_windows._is_windows", return_value=True)
    @patch("scripts.start_searxng_windows.ensure_docker_engine", return_value=False)
    @patch("scripts.start_searxng_windows._health_probe", return_value=(False, None, ""))
    @patch("scripts.start_searxng_windows._run", return_value=MagicMock(returncode=0))
    def test_engine_unavailable_exit_zero(self, *_):
        self.assertEqual(self.mod.main(), 0)

    @patch("scripts.start_searxng_windows._is_windows", return_value=True)
    @patch("scripts.start_searxng_windows.ensure_docker_engine", return_value=True)
    @patch("scripts.start_searxng_windows._run")
    @patch("scripts.start_searxng_windows._health_probe", side_effect=[(False, None, ""), (True, 200, "{}")])
    def test_running_container_no_docker_run(self, _probe, m_run: MagicMock, *_):
        m_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout="running\n"),
            MagicMock(returncode=0, stdout="")
        ]
        self.assertEqual(self.mod.main(), 0)
        calls = [c.args[0] for c in m_run.call_args_list if c.args]
        self.assertFalse(any(cmd[:3] == ["docker", "run", "-d"] for cmd in calls))


if __name__ == "__main__":
    unittest.main()
