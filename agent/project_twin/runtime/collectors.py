"""Runtime observation collectors v2 (PI-8).

Normalize real verification/runtime outputs into ``RuntimeObservationRecord`` with results
``passed | failed | observed | unavailable``, mapping stack frames and coverage to actual
static symbol refs and preserving source revision. Collectors never gain execution
authority and a collector failure produces an explicit ``unavailable`` observation — never a
fabricated ``passed`` (ADR-PI-013).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent.project_intelligence.contracts import RuntimeObservationRecord
_PYTEST_OUTCOME = {"passed": "passed", "failed": "failed", "error": "failed", "skipped": "observed"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _oid(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:12]}"


def map_symbol_ref(relpath: str, qualname: str) -> str:
    """Map a (file, qualname) to the PI-6 canonical symbol ref."""
    return f"py://{Path(relpath).as_posix()}#{qualname}"


def _legacy_module_symbol_ref(relpath: str, qualname: str) -> str | None:
    path = Path(relpath).as_posix()
    if not path.endswith(".py"):
        return None
    return f"py://{path[:-3].replace('/', '.')}#{qualname}"


def map_test_ref(nodeid: str) -> str:
    return f"test://{nodeid}"


def map_stack_frames(frames: list[dict[str, str]]) -> list[str]:
    """Map stack frames ({file, function}) to symbol refs where resolvable."""
    refs: list[str] = []
    for fr in frames:
        rel = fr.get("file")
        func = fr.get("function")
        if rel and func and rel.endswith(".py"):
            refs.append(map_symbol_ref(rel, func))
    return refs


def normalize_pytest(
    report: dict[str, Any],
    *,
    project_id: str,
    workspace_id: str,
    source_revision: str | None,
    run_id: str | None = None,
    coverage: dict[str, list[str]] | None = None,
) -> list[RuntimeObservationRecord]:
    """Normalize a pytest report ``{"tests": [{"nodeid","outcome",...}]}``.

    Per-test coverage can be supplied on each test row as ``{"coverage": {relpath:
    [qualnames]}}``. The legacy function-level ``coverage`` argument is retained as a
    fallback only; it is not applied when a test row carries its own coverage map.
    """
    out: list[RuntimeObservationRecord] = []
    for t in report.get("tests", []):
        outcome = _PYTEST_OUTCOME.get(str(t.get("outcome", "")).lower(), "observed")
        row_coverage = t.get("coverage")
        coverage_map = row_coverage if isinstance(row_coverage, dict) else (coverage or {})
        cov_refs: list[str] = []
        for rel, quals in coverage_map.items():
            for qual in quals:
                cov_refs.append(map_symbol_ref(rel, qual))
                legacy_ref = _legacy_module_symbol_ref(rel, qual)
                if legacy_ref and legacy_ref not in cov_refs:
                    cov_refs.append(legacy_ref)
        subjects = [map_test_ref(t.get("nodeid", "?"))] + cov_refs
        out.append(RuntimeObservationRecord(
            observation_id=_oid("pytest"), project_id=project_id, workspace_id=workspace_id,
            run_id=run_id, collector="pytest", collector_version="2",
            observation_type="test_execution", subject_refs=subjects,
            source_revision=source_revision, timestamp=_now(), result=outcome,
            summary=str(t.get("nodeid", "")), evidence_refs=[e for e in [t.get("longrepr")] if e],
        ))
    return out


def normalize_playwright(
    trace: dict[str, Any], *, project_id: str, workspace_id: str, source_revision: str | None,
    run_id: str | None = None,
) -> list[RuntimeObservationRecord]:
    status = str(trace.get("status", "observed")).lower()
    result = "passed" if status in ("passed", "ok") else "failed" if status in ("failed", "error") else "observed"
    subjects = [f"route://{r}" for r in trace.get("routes", [])] + [f"ui://{s}" for s in trace.get("selectors", [])]
    return [RuntimeObservationRecord(
        observation_id=_oid("playwright"), project_id=project_id, workspace_id=workspace_id,
        run_id=run_id, collector="playwright", collector_version="2",
        observation_type="browser_trace", subject_refs=subjects, source_revision=source_revision,
        timestamp=_now(), result=result, summary=str(trace.get("name", "playwright")),
        evidence_refs=trace.get("evidence_refs", []),
    )]


def normalize_api(
    obs: dict[str, Any], *, project_id: str, workspace_id: str, source_revision: str | None,
    run_id: str | None = None,
) -> RuntimeObservationRecord:
    code = int(obs.get("status_code", 0))
    result = "passed" if 200 <= code < 400 else "failed" if code >= 400 else "observed"
    return RuntimeObservationRecord(
        observation_id=_oid("api"), project_id=project_id, workspace_id=workspace_id, run_id=run_id,
        collector="api", collector_version="2", observation_type="api_observation",
        subject_refs=[f"route://{obs.get('method','GET')} {obs.get('path','/')}"],
        source_revision=source_revision, timestamp=_now(), result=result,
        summary=f"{obs.get('method','GET')} {obs.get('path','/')} -> {code}",
    )


def unavailable_observation(
    collector: str, reason: str, *, project_id: str, workspace_id: str,
    source_revision: str | None = None, subject_refs: list[str] | None = None,
) -> RuntimeObservationRecord:
    """An explicit unavailable observation. Never convertible to passed."""
    return RuntimeObservationRecord(
        observation_id=_oid(f"{collector}-unavail"), project_id=project_id, workspace_id=workspace_id,
        collector=collector, collector_version="2", observation_type="unavailable",
        subject_refs=subject_refs or [], source_revision=source_revision, timestamp=_now(),
        result="unavailable", summary=reason,
    )


def safe_collect(
    collector: str,
    fn: Callable[[], list[RuntimeObservationRecord]],
    *,
    project_id: str,
    workspace_id: str,
    source_revision: str | None = None,
) -> list[RuntimeObservationRecord]:
    """Run a collector; if it raises, yield a single unavailable observation, never passed."""
    try:
        return fn()
    except Exception as exc:
        return [unavailable_observation(collector, f"collector failed: {exc}",
                                        project_id=project_id, workspace_id=workspace_id,
                                        source_revision=source_revision)]
