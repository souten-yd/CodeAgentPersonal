from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.verification_runner import VerificationRunner


class Phase7VerificationTests(unittest.TestCase):
    def test_python_ast_parse_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.py"
            p.write_text("print('ok')\n# CodeAgent Phase 7 patch note\n", encoding="utf-8")
            vr = VerificationRunner().run("run1", "plan1", "patch1", Path(td), p)
            self.assertEqual(vr.status, "passed")

    def test_python_ast_parse_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.py"
            p.write_text("def x(:\n# CodeAgent Phase 7 patch note\n", encoding="utf-8")
            vr = VerificationRunner().run("run1", "plan1", "patch1", Path(td), p)
            self.assertIn(vr.status, {"failed", "warning"})

