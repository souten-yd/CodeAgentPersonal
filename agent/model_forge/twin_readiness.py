from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.model_forge.twin_readiness_contracts import TwinReadinessReport, TwinReadinessRequest, TwinReadinessSignal


class TwinReadinessEvaluator:
    def evaluate(self, request: TwinReadinessRequest) -> TwinReadinessReport:
        meta = request.metadata
        root = Path(request.project_path)
        snapshot = Path(str(meta.get("snapshot_path") or ""))
        snapshot_exists = bool(str(meta.get("snapshot_path") or "")) and snapshot.is_file()
        signals = [TwinReadinessSignal(name="twin_snapshot_availability", status="passed" if snapshot_exists else "unavailable", score=1.0 if snapshot_exists else None, detail=str(snapshot) if snapshot_exists else "snapshot_missing")]
        if snapshot_exists:
            source_paths = [root / value for value in meta.get("source_files", [])]
            newest_source = max((path.stat().st_mtime for path in source_paths if path.is_file()), default=0.0)
            fresh = snapshot.stat().st_mtime >= newest_source
            signals.append(TwinReadinessSignal(name="twin_snapshot_freshness", status="passed" if fresh else "warning", score=1.0 if fresh else 0.0, detail="fresh" if fresh else "snapshot_stale"))
        else:
            signals.append(TwinReadinessSignal(name="twin_snapshot_freshness", status="unavailable", detail="snapshot_missing"))
        resolved = set(meta.get("resolved_refs", []))
        denominator = len(request.changed_refs)
        symbol_score = len(resolved.intersection(request.changed_refs)) / denominator if denominator else None
        signals.append(TwinReadinessSignal(name="symbol_resolution_rate", status=("passed" if symbol_score == 1 else "warning") if symbol_score is not None else "unavailable", score=symbol_score, detail=f"{len(resolved.intersection(request.changed_refs))}/{denominator}" if denominator else "no_changed_refs"))
        impacted = set(meta.get("impacted_refs", [])); expected = set(meta.get("expected_dependent_refs", []))
        precision = len(impacted & expected) / len(impacted) if impacted else None
        impact_status = "warning" if len(impacted) > request.budget else ("passed" if precision is not None else "unavailable")
        signals.append(TwinReadinessSignal(name="impact_precision", status=impact_status, score=precision, detail=f"impacted={len(impacted)},expected_hits={len(impacted & expected)}"))
        signals.append(TwinReadinessSignal(name="impact_budget_fit", status="passed" if len(impacted) <= request.budget else "warning", score=1.0 if len(impacted) <= request.budget else 0.0, detail=f"{len(impacted)}/{request.budget}"))
        briefing = meta.get("safe_edit_briefing")
        signals.append(TwinReadinessSignal(name="safe_edit_briefing_availability", status="passed" if briefing else "unavailable", score=1.0 if briefing else None, detail="available" if briefing else "briefing_missing"))
        delivery = meta.get("prompt_delivery") or {}
        required = {"instruction_id", "brief_id", "policy_id", "prompt_section_hash"}
        delivered = required.issubset(delivery) and all(delivery.get(key) for key in required)
        signals.append(TwinReadinessSignal(name="twin_instruction_delivery", status="passed" if delivered else "unavailable", score=1.0 if delivered else None, detail="audited" if delivered else "delivery_evidence_missing"))
        harm_rate = meta.get("harm_rate")
        signals.append(TwinReadinessSignal(name="twin_harm_rate", status="passed" if harm_rate is not None and float(harm_rate) <= 0.1 else ("warning" if harm_rate is not None else "unavailable"), score=(max(0.0, 1.0 - float(harm_rate)) if harm_rate is not None else None), detail=str(harm_rate) if harm_rate is not None else "harm_evidence_missing"))
        scored = [signal.score for signal in signals if signal.score is not None]
        overall = round(sum(scored) / len(scored), 4) if snapshot_exists and scored else None
        warnings = [signal.detail for signal in signals if signal.status == "warning"]
        if overall is None: level = "unavailable"
        elif overall < 0.4: level = "low"
        elif overall < 0.7: level = "medium"
        elif overall < 0.9: level = "high"
        else: level = "trusted" if not warnings else "high"
        mode, cap = (("constraints_and_refs", 2) if level in {"unavailable", "low"} else (("strict_twin_brief", 4) if level == "medium" else ("twin_deterministic_anchor", 4)))
        return TwinReadinessReport(report_id="twin_readiness_" + uuid4().hex[:12], project_id=request.project_id, project_path=request.project_path, overall_score=overall, readiness_level=level, signals=signals, recommended_max_assist_mode=mode, recommended_injection_cap=cap, blocked_reasons=(["twin_snapshot_unavailable"] if not snapshot_exists else []), warnings=warnings, evidence_refs=[str(snapshot)] if snapshot_exists else [], created_at=datetime.now(timezone.utc).isoformat())
