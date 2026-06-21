from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from agent.model_forge.schema import ForgeModel
from agent.model_forge.twin_edit_slots import TwinEditSlot


class TwinSlotQualityReport(ForgeModel):
    report_id: str
    slot_id: str
    file: str
    symbol_ref: str = ""
    accepted: bool
    score: float | None = Field(default=None, ge=0, le=1)
    findings: list[dict] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class TwinSlotQualityRequest(ForgeModel):
    project_root: str
    slot: TwinEditSlot
    forbidden_refs: list[str] = Field(default_factory=list)


class TwinSlotQualityGate:
    def __init__(self, *, confidence_threshold: float = 0.7, max_range_lines: int = 120) -> None:
        self.confidence_threshold = confidence_threshold; self.max_range_lines = max_range_lines

    def evaluate(self, *, slot: TwinEditSlot, project_root: str | Path, forbidden_refs: list[str] | None = None) -> TwinSlotQualityReport:
        root = Path(project_root).resolve(); path = (root / slot.file).resolve(); blocked = []; warnings = []; findings = []
        if root not in path.parents or not path.is_file():
            blocked.append("target_file_missing")
            lines = []
        else:
            lines = path.read_text(encoding="utf-8").splitlines()
        if slot.anchor_occurrences != 1 or not slot.anchor_text:
            blocked.append("anchor_not_unique")
        elif lines and "\n".join(lines).count(slot.anchor_text) != 1:
            blocked.append("anchor_evidence_mismatch")
        if slot.start_line is None or slot.end_line is None or slot.start_line > slot.end_line or (lines and slot.end_line > len(lines)):
            blocked.append("slot_range_out_of_bounds")
        elif slot.end_line - slot.start_line + 1 > self.max_range_lines:
            blocked.append("slot_range_too_broad")
        elif slot.end_line - slot.start_line + 1 > slot.max_new_lines:
            warnings.append("slot_larger_than_output_budget")
        forbidden = set(forbidden_refs or [])
        if slot.file in forbidden or slot.symbol_ref in forbidden or any(ref.endswith(":" + slot.symbol_ref) for ref in forbidden if slot.symbol_ref):
            blocked.append("forbidden_ref_overlap")
        if slot.confidence < self.confidence_threshold:
            blocked.append("slot_confidence_below_threshold")
        if lines and path.suffix == ".py" and slot.start_line and slot.end_line:
            try:
                tree = ast.parse("\n".join(lines))
                top = [(node.lineno, int(node.end_lineno or node.lineno)) for node in tree.body if hasattr(node, "lineno")]
                overlaps = [bounds for bounds in top if not (slot.end_line < bounds[0] or slot.start_line > bounds[1])]
                if len(overlaps) > 1:
                    blocked.append("slot_crosses_top_level_boundary")
            except SyntaxError:
                warnings.append("python_ast_unavailable")
        checks = 6
        score = round(max(0.0, (checks - len(set(blocked))) / checks), 4)
        findings.append({"anchor_occurrences": slot.anchor_occurrences, "range_lines": ((slot.end_line - slot.start_line + 1) if slot.start_line and slot.end_line else None), "confidence": slot.confidence})
        return TwinSlotQualityReport(report_id="slot_quality_" + uuid4().hex[:12], slot_id=slot.slot_id, file=slot.file, symbol_ref=slot.symbol_ref, accepted=not blocked, score=score, findings=findings, blocked_reasons=list(dict.fromkeys(blocked)), warnings=warnings, evidence_refs=slot.evidence_refs)
