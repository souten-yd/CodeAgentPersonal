"""Schema Guardian for API/artifact/persistence/event/UI contract drift.

This module classifies schema changes and required proof. It does not inspect
Git itself and never accepts a schema-affecting patch from unit tests alone.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from pydantic import Field

from agent.twin_control_plane.contracts import TwinControlPlaneModel


class SchemaSurface(StrEnum):
    API_RESPONSE = "api_response"
    ARTIFACT = "artifact"
    PERSISTENCE = "persistence"
    EVENT_PAYLOAD = "event_payload"
    UI_PROJECTION = "ui_projection"


class SchemaCompatibility(StrEnum):
    COMPATIBLE = "compatible"
    MIGRATION_REQUIRED = "migration_required"
    BREAKING = "breaking"
    UNKNOWN = "unknown"


class SchemaField(TwinControlPlaneModel):
    name: str = Field(min_length=1)
    field_type: str = Field(min_length=1)
    required: bool = False


class SchemaSnapshot(TwinControlPlaneModel):
    schema_id: str = Field(min_length=1)
    surface: SchemaSurface
    version: str = ""
    fields: list[SchemaField] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class SchemaFinding(TwinControlPlaneModel):
    finding_id: str = Field(min_length=1)
    schema_id: str = Field(min_length=1)
    surface: SchemaSurface
    compatibility: SchemaCompatibility
    status: str = "needs_proof"  # allowed_with_proof | needs_migration | blocked | advisory
    message: str = Field(min_length=1)
    changed_fields: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)


class SchemaGuardianReport(TwinControlPlaneModel):
    report_id: str = Field(min_length=1)
    accepted: bool = False
    blocked: bool = False
    findings: list[SchemaFinding] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)
    migration_required: bool = False
    unit_tests_alone_sufficient: bool = False


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _field_map(snapshot: SchemaSnapshot) -> dict[str, SchemaField]:
    return {field.name: field for field in snapshot.fields}


def _finding(
    *,
    schema: SchemaSnapshot,
    compatibility: SchemaCompatibility,
    status: str,
    message: str,
    changed_fields: Iterable[str],
    proof_requirements: Iterable[str],
) -> SchemaFinding:
    fields = _unique(changed_fields)
    return SchemaFinding(
        finding_id=f"schema_guardian:{schema.schema_id}:{compatibility.value}",
        schema_id=schema.schema_id,
        surface=schema.surface,
        compatibility=compatibility,
        status=status,
        message=message,
        changed_fields=fields,
        proof_requirements=_unique(proof_requirements),
    )


def compare_schema_snapshots(
    before: SchemaSnapshot | None,
    after: SchemaSnapshot | None,
    *,
    migration_notes: Iterable[str] = (),
    tests: Iterable[str] = (),
) -> SchemaGuardianReport:
    """Compare before/after schema snapshots and require migration/proof."""
    notes = _unique(migration_notes)
    test_refs = _unique(tests)
    findings: list[SchemaFinding] = []

    if before is None and after is None:
        findings.append(SchemaFinding(
            finding_id="schema_guardian:unknown:no_snapshot",
            schema_id="unknown",
            surface=SchemaSurface.ARTIFACT,
            compatibility=SchemaCompatibility.UNKNOWN,
            status="advisory",
            message="No schema snapshots were provided; compatibility is unknown.",
            proof_requirements=["Provide schema snapshot evidence or mark schema impact unavailable."],
        ))
    elif before is None:
        assert after is not None
        findings.append(_finding(
            schema=after,
            compatibility=SchemaCompatibility.MIGRATION_REQUIRED,
            status="needs_migration",
            message="New schema surface requires version, compatibility, and bootstrap proof.",
            changed_fields=[field.name for field in after.fields],
            proof_requirements=[
                f"Record initial {after.surface.value} schema contract for {after.schema_id}.",
                "Provide create/read/reload or producer/consumer proof.",
            ],
        ))
    elif after is None:
        findings.append(_finding(
            schema=before,
            compatibility=SchemaCompatibility.BREAKING,
            status="blocked",
            message="Schema surface was removed.",
            changed_fields=[field.name for field in before.fields],
            proof_requirements=[f"Provide migration/removal proof for {before.schema_id}."],
        ))
    else:
        before_fields = _field_map(before)
        after_fields = _field_map(after)
        removed = sorted(set(before_fields) - set(after_fields))
        added = sorted(set(after_fields) - set(before_fields))
        type_changed = sorted(name for name in set(before_fields) & set(after_fields) if before_fields[name].field_type != after_fields[name].field_type)
        required_changed = sorted(
            name for name in set(before_fields) & set(after_fields)
            if before_fields[name].required is False and after_fields[name].required is True
        )
        required_added = sorted(name for name in added if after_fields[name].required)
        optional_added = sorted(name for name in added if not after_fields[name].required)
        incompatible = _unique([*removed, *type_changed, *required_changed, *required_added])

        if incompatible and notes:
            findings.append(_finding(
                schema=after,
                compatibility=SchemaCompatibility.MIGRATION_REQUIRED,
                status="needs_migration",
                message="Schema change requires migration notes and compatibility proof.",
                changed_fields=incompatible,
                proof_requirements=[
                    f"Run migration/compatibility proof for {after.schema_id}.",
                    "Record producer and consumer behavior across old and new schema.",
                    *notes,
                ],
            ))
        elif incompatible:
            findings.append(_finding(
                schema=after,
                compatibility=SchemaCompatibility.BREAKING,
                status="blocked",
                message="Breaking schema drift lacks migration notes/proof.",
                changed_fields=incompatible,
                proof_requirements=[
                    f"Add migration notes and compatibility tests for {after.schema_id}.",
                    "Unit tests alone are insufficient for schema-affecting changes.",
                ],
            ))
        elif optional_added:
            findings.append(_finding(
                schema=after,
                compatibility=SchemaCompatibility.COMPATIBLE,
                status="allowed_with_proof",
                message="Additive optional schema change is compatible with proof.",
                changed_fields=optional_added,
                proof_requirements=[
                    f"Record compatibility proof for additive {after.surface.value} fields.",
                    "Verify old consumers tolerate missing optional fields.",
                ],
            ))
        else:
            findings.append(_finding(
                schema=after,
                compatibility=SchemaCompatibility.COMPATIBLE,
                status="allowed_with_proof",
                message="No schema drift detected; retain contract evidence.",
                changed_fields=[],
                proof_requirements=[f"Record schema evidence for {after.schema_id}."],
            ))

    proof_requirements = _unique(proof for finding in findings for proof in finding.proof_requirements)
    proof_requirements.extend(f"Relevant test evidence: {test}" for test in test_refs)
    proof_requirements = _unique(proof_requirements)
    blocked = any(finding.status == "blocked" for finding in findings)
    migration_required = any(finding.compatibility == SchemaCompatibility.MIGRATION_REQUIRED for finding in findings)
    accepted = bool(findings) and not blocked and all(finding.compatibility != SchemaCompatibility.UNKNOWN for finding in findings)
    return SchemaGuardianReport(
        report_id=f"schema_guardian:{(after or before).schema_id if (after or before) else 'unknown'}",
        accepted=accepted,
        blocked=blocked,
        findings=findings,
        proof_requirements=proof_requirements,
        migration_required=migration_required,
        unit_tests_alone_sufficient=False,
    )


__all__ = [
    "SchemaCompatibility",
    "SchemaField",
    "SchemaFinding",
    "SchemaGuardianReport",
    "SchemaSnapshot",
    "SchemaSurface",
    "compare_schema_snapshots",
]
