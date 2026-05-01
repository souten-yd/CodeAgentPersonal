from __future__ import annotations

import sys
from pathlib import Path
import importlib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestStartCodeAgentWindowsEnv(unittest.TestCase):
    def test_windows_defaults_removed_from_source(self):
        text = Path("scripts/start_codeagent.py").read_text(encoding="utf-8")
        self.assertNotIn("CODEAGENT_SEARXNG_REPO_DIR", text)
        self.assertNotIn("CODEAGENT_SEARXNG_VENV_DIR", text)
        self.assertIn("start_searxng_windows.py", text)


class TestRouterWindowsHint(unittest.TestCase):
    def test_windows_hint_uses_docker_message(self):
        mod = importlib.import_module("app.nexus.router")
        with patch("app.nexus.router.os.name", "nt"):
            _, msg = mod._resolve_searxng_state("failed_probe", False)
            self.assertIn("Docker", msg)
            self.assertNotIn("setup_searxng_windows.py", msg)


if __name__ == "__main__":
    unittest.main()
