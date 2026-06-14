"""CI guard for the comprehensive Digital Twin / Deep Behavioral Graph evaluation.

Runs the full scenario matrix in scripts/twin_comprehensive_eval.py (multi-package virtual project;
multi-location + multi-ref impact; config .get()/getenv()/subscript; resource direction; from-import /
relative / self-method call resolution; UI->API->route path; historical-risk gating; uncertainty
invariants) and asserts every detection check passes, so regressions in the twin's usability/detection
are caught in CI rather than only by the manual script.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_harness():
    path = Path(__file__).resolve().parents[1] / "scripts" / "twin_comprehensive_eval.py"
    spec = importlib.util.spec_from_file_location("twin_comprehensive_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_comprehensive_twin_detection_all_checks_pass(tmp_path: Path) -> None:
    harness = _load_harness()
    failures = harness._run(tmp_path)
    assert failures == 0, f"{failures} comprehensive twin detection check(s) failed"
