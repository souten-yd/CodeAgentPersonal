"""PIR-14 scale and concurrency evidence runner.

Builds a temporary repository-shaped workspace, runs the source-derived inventory against
it, and repeats the scan concurrently. Metrics are measured from actual execution, not
manually supplied outcomes.
"""

from __future__ import annotations

import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.project_intelligence.inspection.consumer_inventory import build_inventory


@dataclass(frozen=True)
class ScaleConcurrencyEvidence:
    generated_file_count: int
    concurrency: int
    inventory_duration_seconds: float
    concurrent_duration_seconds: float
    parse_error_count: int
    concurrent_parse_error_count: int
    result: str


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_large_fixture(root: Path, *, file_count: int) -> None:
    agent_pkg = root / "agent" / "synthetic_large"
    app_api = root / "app" / "api"
    agent_pkg.mkdir(parents=True)
    app_api.mkdir(parents=True)
    (root / "agent" / "__init__.py").write_text("", encoding="utf-8")
    (agent_pkg / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (app_api / "__init__.py").write_text("", encoding="utf-8")
    for index in range(file_count):
        target = agent_pkg / f"module_{index:04d}.py"
        target.write_text(
            f"def function_{index:04d}():\n    return {index}\n",
            encoding="utf-8",
        )
    for index in range(max(1, file_count // 100)):
        (app_api / f"route_{index:03d}.py").write_text(
            "from agent.synthetic_large.module_0000 import function_0000\n\n"
            f"def route_{index:03d}():\n    return function_0000()\n",
            encoding="utf-8",
        )


def build_scale_concurrency_evidence(
    *,
    file_count: int = 1200,
    concurrency: int = 4,
    generated_at: str | None = None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pir14_scale_workspace_") as temp:
        root = Path(temp)
        _write_large_fixture(root, file_count=file_count)

        started = time.perf_counter()
        inventory = build_inventory(root)
        inventory_duration = time.perf_counter() - started

        def _scan() -> int:
            return len(build_inventory(root).get("parse_errors", []))

        concurrent_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            concurrent_errors = list(executor.map(lambda _: _scan(), range(concurrency)))
        concurrent_duration = time.perf_counter() - concurrent_started

        parse_error_count = len(inventory.get("parse_errors", []))
        concurrent_parse_error_count = sum(concurrent_errors)
        passed = parse_error_count == 0 and concurrent_parse_error_count == 0
        evidence = ScaleConcurrencyEvidence(
            generated_file_count=file_count,
            concurrency=concurrency,
            inventory_duration_seconds=round(inventory_duration, 4),
            concurrent_duration_seconds=round(concurrent_duration, 4),
            parse_error_count=parse_error_count,
            concurrent_parse_error_count=concurrent_parse_error_count,
            result="passed" if passed else "failed",
        )
        return {
            "schema_version": 1,
            "generated_at": generated_at or _utcnow_iso(),
            "source": "project_intelligence_generated_large_workspace_inventory",
            "evidence": asdict(evidence),
            "inventory_summary": inventory.get("summary", {}),
            "safety": {
                "temporary_workspace": True,
                "source_mutation": False,
                "rollout_transition": False,
                "legacy_retirement": False,
                "manual_metrics": False,
            },
        }


def write_scale_concurrency_evidence(output: str | Path, **kwargs: Any) -> dict[str, Any]:
    evidence = build_scale_concurrency_evidence(**kwargs)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence
