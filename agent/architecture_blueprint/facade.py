"""Atlas Architecture Blueprint Module — disabled facade stub (PI-1).

Ships only a safe disabled implementation: it never fabricates an activated Blueprint
revision and never reports actual implementation status (ADR-PI-001). Real generation,
review, validation and persistence arrive in PI-10..PI-12.
"""

from __future__ import annotations

from agent.architecture_blueprint.contracts import (
    BlueprintActivationRequest,
    BlueprintCreateRequest,
    BlueprintGetRequest,
    BlueprintGetRevisionRequest,
    BlueprintResult,
    BlueprintReviewRequest,
    BlueprintReviewResult,
    BlueprintRevision,
    BlueprintRevisionRequest,
)
from agent.project_intelligence.contracts import (
    IntelligenceDiagnostic,
    IntelligenceError,
    IntelligenceErrorCode,
)


def _diag(message: str) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(
        code=IntelligenceErrorCode.BLUEPRINT_INVALID,
        message=message,
        severity="info",
    )


class DisabledArchitectureBlueprintModule:
    """Disabled-by-default Blueprint facade holding no store reference."""

    rollout_mode = "off"

    def create(self, request: BlueprintCreateRequest) -> BlueprintResult:
        return BlueprintResult(
            blueprint_id="disabled",
            status="unavailable",
            diagnostics=[_diag("architecture blueprint disabled (rollout off)")],
        )

    def revise(self, request: BlueprintRevisionRequest) -> BlueprintResult:
        return BlueprintResult(
            blueprint_id=request.blueprint_id,
            status="unavailable",
            diagnostics=[_diag("architecture blueprint disabled (rollout off)")],
        )

    def review(self, request: BlueprintReviewRequest) -> BlueprintReviewResult:
        return BlueprintReviewResult(
            blueprint_id=request.blueprint_id,
            revision_id=request.revision_id,
            valid=False,
            diagnostics=[_diag("architecture blueprint disabled (rollout off)")],
        )

    def activate(self, request: BlueprintActivationRequest) -> BlueprintRevision:
        # Never fabricate an activated revision when disabled.
        raise IntelligenceError(
            IntelligenceErrorCode.BLUEPRINT_INVALID,
            "architecture blueprint disabled (rollout off)",
        )

    def get_active(self, request: BlueprintGetRequest) -> BlueprintRevision | None:
        return None

    def get_revision(self, request: BlueprintGetRevisionRequest) -> BlueprintRevision:
        raise IntelligenceError(
            IntelligenceErrorCode.REVISION_NOT_FOUND,
            "architecture blueprint disabled (rollout off)",
        )
