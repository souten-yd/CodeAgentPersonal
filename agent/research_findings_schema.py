from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchFindings(BaseModel):
    relevant_files: list[str] = Field(default_factory=list)
    existing_patterns: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    recommended_approach: str = ""
    warnings: list[str] = Field(default_factory=list)

    def to_prompt_text(self) -> str:
        """Compact text block injected into the planner prompt as a Research Evidence section."""
        if not (self.relevant_files or self.existing_patterns or self.key_findings or self.risks or self.recommended_approach):
            return ""
        lines: list[str] = []
        if self.recommended_approach:
            lines.append(f"Recommended approach: {self.recommended_approach}")
        for label, items in (
            ("Relevant files", self.relevant_files),
            ("Existing patterns to reuse", self.existing_patterns),
            ("Key findings", self.key_findings),
            ("Risks", self.risks),
            ("Open questions", self.open_questions),
        ):
            if items:
                lines.append(f"{label}:")
                lines.extend(f"- {str(x)}" for x in items[:8])
        return "\n".join(lines)[:6000]
