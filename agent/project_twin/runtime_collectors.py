"""Runtime observation collectors and ingestor (PDT-9).

Normalizes safe runtime evidence (pytest, Playwright/browser, API observation, Atlas Play
console/failed-request) into `RuntimeObservation` records and ingests them into the twin.

Truthfulness rules:
- `passed`/`failed`/`observed`/`unavailable` are distinct and preserved;
- when an instrumentation source is unavailable, the collector emits a single
  `unavailable` observation and NEVER fabricates `passed`;
- observations link to test/symbol/route refs in `subject_refs` where possible.

`RuntimeObservationIngestor` implements `RuntimeObservationPort.ingest`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from agent.project_twin.contracts import (
    ObservationIngestResult,
    RuntimeObservation,
    TwinDelta,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _oid() -> str:
    return uuid.uuid4().hex


def _test_ref(nodeid: str) -> str:
    # "tests/test_x.py::test_a" -> "test://tests/test_x.py::test_a"
    return nodeid if nodeid.startswith("test://") else f"test://{nodeid}"


_PYTEST_RESULT = {"passed": "passed", "failed": "failed", "error": "failed", "skipped": "observed", "xfailed": "observed", "xpassed": "observed"}


class PytestCollector:
    collector = "pytest"

    def collect(self, report: dict) -> list[RuntimeObservation]:
        version = str(report.get("collector_version", "unknown"))
        if not report.get("available", True):
            return [self._unavailable(version, report.get("reason", "pytest_unavailable"))]
        out: list[RuntimeObservation] = []
        for t in report.get("tests", []) or []:
            nodeid = t.get("nodeid")
            if not nodeid:
                continue
            result = _PYTEST_RESULT.get(str(t.get("outcome", "")).lower(), "observed")
            out.append(RuntimeObservation(
                observation_id=_oid(), project_id=report["project_id"], run_id=report.get("run_id"),
                collector=self.collector, collector_version=version, observation_type="test",
                subject_refs=[_test_ref(nodeid)], timestamp=_now(), result=result,
                summary=f"{nodeid} -> {t.get('outcome')}",
            ))
        return out

    def _unavailable(self, version: str, reason: str) -> RuntimeObservation:
        return RuntimeObservation(
            observation_id=_oid(), project_id="", collector=self.collector, collector_version=version,
            observation_type="test", subject_refs=[], timestamp=_now(), result="unavailable", summary=reason,
        )


class PlaywrightCollector:
    collector = "playwright"

    def collect(self, trace: dict) -> list[RuntimeObservation]:
        version = str(trace.get("collector_version", "unknown"))
        project_id = trace.get("project_id", "")
        if not trace.get("available", True):
            return [RuntimeObservation(
                observation_id=_oid(), project_id=project_id, collector=self.collector,
                collector_version=version, observation_type="browser", subject_refs=[],
                timestamp=_now(), result="unavailable",
                summary=trace.get("reason", "browser_not_installed"),
            )]
        result = "failed" if trace.get("errors") else "observed"
        return [RuntimeObservation(
            observation_id=_oid(), project_id=project_id, run_id=trace.get("run_id"),
            collector=self.collector, collector_version=version, observation_type="browser",
            subject_refs=trace.get("subject_refs", []), timestamp=_now(), result=result,
            summary=trace.get("summary", "browser trace"),
        )]


class ApiObservationCollector:
    collector = "api"

    def collect(self, obs: dict) -> list[RuntimeObservation]:
        version = str(obs.get("collector_version", "unknown"))
        method = str(obs.get("method", "GET")).upper()
        path = obs.get("path", "/")
        status = int(obs.get("status", 0) or 0)
        result = "failed" if status >= 500 else "observed"
        return [RuntimeObservation(
            observation_id=_oid(), project_id=obs["project_id"], run_id=obs.get("run_id"),
            collector=self.collector, collector_version=version, observation_type="api",
            subject_refs=[f"route://{method} {path}"], timestamp=_now(), result=result,
            summary=f"{method} {path} -> {status}",
        )]


class PlayConsoleCollector:
    """Atlas Play console / failed-request adapter."""

    collector = "atlas_play"

    def collect(self, logs: dict) -> list[RuntimeObservation]:
        version = str(logs.get("collector_version", "unknown"))
        project_id = logs.get("project_id", "")
        if not logs.get("available", True):
            return [RuntimeObservation(
                observation_id=_oid(), project_id=project_id, collector=self.collector,
                collector_version=version, observation_type="console", subject_refs=[],
                timestamp=_now(), result="unavailable", summary=logs.get("reason", "play_session_unavailable"),
            )]
        out: list[RuntimeObservation] = []
        for msg in logs.get("console", []) or []:
            level = str(msg.get("level", "log")).lower()
            out.append(RuntimeObservation(
                observation_id=_oid(), project_id=project_id, run_id=logs.get("session_id"),
                collector=self.collector, collector_version=version, observation_type="console",
                subject_refs=[], timestamp=_now(), result="failed" if level in {"error"} else "observed",
                summary=f"[{level}] {msg.get('text', '')}",
            ))
        for req in logs.get("failed_requests", []) or []:
            out.append(RuntimeObservation(
                observation_id=_oid(), project_id=project_id, run_id=logs.get("session_id"),
                collector=self.collector, collector_version=version, observation_type="failed_request",
                subject_refs=[f"route://{str(req.get('method', 'GET')).upper()} {req.get('url', '/')}"],
                timestamp=_now(), result="failed", summary=f"{req.get('status')} {req.get('url')}",
            ))
        return out


class RuntimeObservationIngestor:
    """Implements `RuntimeObservationPort.ingest`."""

    def __init__(self, store) -> None:
        self._store = store

    def ingest(self, observation: RuntimeObservation) -> ObservationIngestResult:
        now = _now()
        # An unavailable observation with no project cannot be ingested as project truth.
        if not observation.project_id:
            return ObservationIngestResult(
                project_id="", observation_id=observation.observation_id, accepted=False,
                diagnostics=[{"code": "collector_unavailable", "detail": observation.summary}],
                generated_at=now,
            )
        revision = self._store.apply_delta(
            TwinDelta(
                project_id=observation.project_id,
                idempotency_key=f"obs:{observation.observation_id}",
                trigger_type="runtime_observation.recorded",
                observations=[observation],
            )
        )
        return ObservationIngestResult(
            project_id=observation.project_id, observation_id=observation.observation_id,
            accepted=True, twin_revision_id=revision.revision_id,
            diagnostics=[{"code": "collector_unavailable", "detail": observation.summary}] if observation.result == "unavailable" else [],
            generated_at=now,
        )
