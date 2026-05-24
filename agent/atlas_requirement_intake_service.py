from __future__ import annotations

from agent.atlas_requirement_intake_schema import AtlasRequirementIntakePreview, AtlasRequirementIntakeRequest


_VALID_SOURCES = {"atlas_workbench", "vue_next", "legacy_ui", "api"}
_MAX_INPUT_CHARS = 20000


class AtlasRequirementIntakeService:
    """Builds a read-only preview for Atlas Requirement input."""

    def preview(self, request: AtlasRequirementIntakeRequest) -> AtlasRequirementIntakePreview:
        normalized_input = (request.input or "").strip()
        source = str(request.source or "atlas_workbench").strip() or "atlas_workbench"
        warnings: list[str] = []
        blocked_reasons: list[str] = []

        if source not in _VALID_SOURCES:
            warnings.append("unknown_requirement_source_normalized_to_api")
            source = "api"

        if not normalized_input:
            blocked_reasons.append("requirement_input_empty")

        if len(normalized_input) > _MAX_INPUT_CHARS:
            blocked_reasons.append("requirement_input_too_large")
            warnings.append("requirement_input_exceeds_preview_limit")

        return AtlasRequirementIntakePreview(
            status="ready_for_planning" if not blocked_reasons else "blocked",
            source=source,
            normalized_input=normalized_input,
            input_length=len(normalized_input),
            can_start_planning=not blocked_reasons,
            blocked_reasons=blocked_reasons,
            warnings=warnings,
            project_path=(request.project_path or "").strip(),
            project_name=(request.project_name or "CodeAgentPersonal").strip() or "CodeAgentPersonal",
            workspace_id=(request.workspace_id or "default").strip() or "default",
            planning_depth=(request.planning_depth or "standard").strip() or "standard",
        )
