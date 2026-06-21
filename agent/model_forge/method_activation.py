"""PR20: Gated activation of Forge method policy as active pre-execution guidance.

PR15 records Forge method recommendations in *shadow* only (production routing
unchanged). This gate lets an operator promote a stage so the MethodRouter decision
may be used as **active pre-execution policy** — but only after enough stable shadow
evidence has accumulated and only with an explicit acknowledgement.

Hard guarantees, always:
- Automation stays OFF (``active_auto_enabled`` is never True).
- Proposal / Safe Apply / Verification remain required; activation never bypasses them.
- Deactivation needs no acknowledgement, so reverting to shadow is always one call away.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel
from agent.model_forge.stage_taxonomy import ForgeStage

_UNAVAILABLE_PROFILE = "model_evaluation_profile:unavailable"
_STABILITY_RATIO = 0.6

_PROOF_REQUIREMENTS = [
    "Activation only selects the pre-execution method policy; it never applies a change.",
    "Proposal, Safe Apply, Verification, and existing Atlas authority remain required.",
    "Automation is off; each active run is still operator-driven.",
    "RouteMatrix authority is unchanged; method selection never overrides the route.",
]


class MethodActivationReadiness(ForgeModel):
    stage: ForgeStage
    ready: bool = False
    sample_count: int = 0
    min_samples: int = 3
    stable_method: str = ""
    stable: bool = False
    evidence_present: bool = False
    shadow_only: bool = True
    reasons: list[str] = []


class MethodActivationRecord(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    stage: ForgeStage
    status: str = "shadow"  # "active" | "shadow"
    active_method_enabled: bool = False
    active_auto_enabled: bool = False  # invariant: never True
    stable_method: str = ""
    sample_count: int = 0
    acknowledged_at: str = ""
    deactivated_at: str = ""
    proof_requirements: list[str] = []


class MethodActivationGate:
    def __init__(
        self,
        shadow_dir: str | Path,
        store_dir: str | Path,
        *,
        min_samples: int = 3,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._shadow_dir = Path(shadow_dir)
        self._dir = Path(store_dir)
        self._min_samples = min_samples
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # ----- evidence -----

    def _load_shadow_records(self, stage: ForgeStage) -> list[dict]:
        stage_dir = self._shadow_dir / ForgeStage(stage).value
        if not stage_dir.exists():
            return []
        records: list[dict] = []
        for path in sorted(stage_dir.glob("*.json")):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return records

    def evaluate_readiness(self, stage: ForgeStage | str) -> MethodActivationReadiness:
        stage = ForgeStage(stage)
        records = self._load_shadow_records(stage)
        reasons: list[str] = []

        sample_count = len(records)
        if sample_count < self._min_samples:
            reasons.append(f"insufficient_shadow_samples:{sample_count}<{self._min_samples}")

        methods = [str(rec.get("method_variant") or "") for rec in records]
        non_empty = [m for m in methods if m]
        stable_method = ""
        stable = False
        if non_empty:
            stable_method, count = Counter(non_empty).most_common(1)[0]
            needed = math.ceil(sample_count * _STABILITY_RATIO)
            stable = count >= needed
        if not stable:
            reasons.append("method_recommendation_not_stable")

        evidence_present = any(
            _UNAVAILABLE_PROFILE not in (rec.get("unavailable_reasons") or [])
            for rec in records
        )
        if not evidence_present:
            reasons.append("no_model_evaluation_evidence")

        shadow_only = all(not rec.get("changes_production_routing", False) for rec in records)
        if not shadow_only:
            reasons.append("non_shadow_record_present")

        ready = sample_count >= self._min_samples and stable and evidence_present and shadow_only
        return MethodActivationReadiness(
            stage=stage,
            ready=ready,
            sample_count=sample_count,
            min_samples=self._min_samples,
            stable_method=stable_method,
            stable=stable,
            evidence_present=evidence_present,
            shadow_only=shadow_only,
            reasons=reasons,
        )

    # ----- activation -----

    def activate(self, stage: ForgeStage | str, *, acknowledge: bool = False) -> MethodActivationRecord:
        stage = ForgeStage(stage)
        if not acknowledge:
            raise PermissionError(
                f"activating Forge method policy for {stage.value} changes how Atlas selects "
                "the pre-execution method; pass acknowledge=True to confirm "
                "(Proposal/Safe Apply/Verification stay required; automation stays off)"
            )
        readiness = self.evaluate_readiness(stage)
        if not readiness.ready:
            raise ValueError(f"method_activation_not_ready:{','.join(readiness.reasons)}")
        record = MethodActivationRecord(
            stage=stage,
            status="active",
            active_method_enabled=True,
            active_auto_enabled=False,
            stable_method=readiness.stable_method,
            sample_count=readiness.sample_count,
            acknowledged_at=self._clock().isoformat(),
            proof_requirements=list(_PROOF_REQUIREMENTS),
        )
        self._save(record)
        return record

    def deactivate(self, stage: ForgeStage | str) -> MethodActivationRecord:
        stage = ForgeStage(stage)
        existing = self.load(stage)
        record = MethodActivationRecord(
            stage=stage,
            status="shadow",
            active_method_enabled=False,
            active_auto_enabled=False,
            stable_method=existing.stable_method if existing else "",
            sample_count=existing.sample_count if existing else 0,
            acknowledged_at=existing.acknowledged_at if existing else "",
            deactivated_at=self._clock().isoformat(),
            proof_requirements=list(_PROOF_REQUIREMENTS),
        )
        self._save(record)
        return record

    def is_active(self, stage: ForgeStage | str) -> bool:
        record = self.load(stage)
        return bool(record and record.status == "active" and record.active_method_enabled)

    def load(self, stage: ForgeStage | str) -> MethodActivationRecord | None:
        path = self._path(ForgeStage(stage))
        if not path.exists():
            return None
        return MethodActivationRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_activations(self) -> list[MethodActivationRecord]:
        if not self._dir.exists():
            return []
        return [
            MethodActivationRecord.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(self._dir.glob("*.activation.json"))
        ]

    def _path(self, stage: ForgeStage) -> Path:
        return self._dir / f"{ForgeStage(stage).value}.activation.json"

    def _save(self, record: MethodActivationRecord) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(record.stage).write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


__all__ = ["MethodActivationReadiness", "MethodActivationRecord", "MethodActivationGate"]
