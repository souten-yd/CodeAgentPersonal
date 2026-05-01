from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestStartSearxngWindowsDocker(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = importlib.import_module("scripts.start_searxng_windows")

    @patch("scripts.start_searxng_windows._probe", return_value=False)
    @patch("scripts.start_searxng_windows.try_install_docker", return_value=True)
    @patch("scripts.start_searxng_windows._run")
    @patch("scripts.start_searxng_windows._is_windows", return_value=True)
    def test_docker_missing_tries_install(self, m_run: MagicMock, *_):
        m_run.side_effect = [MagicMock(returncode=1)]
        self.assertEqual(self.mod.main(), 0)

    @patch("scripts.start_searxng_windows._probe", return_value=False)
    @patch("scripts.start_searxng_windows._run")
    @patch("scripts.start_searxng_windows._is_windows", return_value=True)
    def test_engine_unavailable_exit_zero(self, _is_win, m_run: MagicMock, _probe):
        m_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=1)] + [MagicMock(returncode=1)] * 40
        self.assertEqual(self.mod.main(), 0)

    @patch("scripts.start_searxng_windows.ensure_docker_engine", return_value=True)
    @patch("scripts.start_searxng_windows._probe", side_effect=[False, True])
    @patch("scripts.start_searxng_windows._run")
    @patch("scripts.start_searxng_windows._is_windows", return_value=True)
    def test_running_container_no_docker_run(self, _is_win, m_run: MagicMock, *_):
        mount = str((Path.cwd() / "ca_data" / "searxng").resolve())
        inspect = f'[{{"State":{{"Status":"running"}},"HostConfig":{{"PortBindings":{{"8080/tcp":[{{"HostIp":"127.0.0.1","HostPort":"8088"}}]}},"Binds":["{mount}:/etc/searxng"]}}}}]'
        m_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=0, stdout=inspect)]
        self.assertEqual(self.mod.main(), 0)
        calls = [c.args[0] for c in m_run.call_args_list if c.args]
        self.assertFalse(any(cmd[:3] == ["docker", "run", "-d"] for cmd in calls))



class TestSettings(unittest.TestCase):
    def test_settings_generated(self):
        mod = importlib.import_module("scripts.start_searxng_windows")
        with tempfile.TemporaryDirectory() as td:
            path = mod.ensure_settings(Path(td))
            text = path.read_text(encoding="utf-8")
            self.assertIn("secret_key:", text)
            self.assertIn('bind_address: "0.0.0.0"', text)
            self.assertIn("port: 8080", text)


if __name__ == "__main__":
    unittest.main()
