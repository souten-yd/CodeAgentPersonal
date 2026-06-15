from __future__ import annotations

from agent.twin_control_plane.schema_guardian import (
    SchemaCompatibility,
    SchemaField,
    SchemaSnapshot,
    SchemaSurface,
    compare_schema_snapshots,
)


def _snapshot(schema_id: str, surface: SchemaSurface, fields: list[SchemaField]) -> SchemaSnapshot:
    return SchemaSnapshot(schema_id=schema_id, surface=surface, version="1", fields=fields)


def test_compatible_additive_schema_change_is_allowed_with_proof() -> None:
    before = _snapshot(
        "api://proposal.response",
        SchemaSurface.API_RESPONSE,
        [SchemaField(name="proposal_id", field_type="str", required=True)],
    )
    after = _snapshot(
        "api://proposal.response",
        SchemaSurface.API_RESPONSE,
        [
            SchemaField(name="proposal_id", field_type="str", required=True),
            SchemaField(name="warnings", field_type="list[str]", required=False),
        ],
    )

    report = compare_schema_snapshots(before, after, tests=["tests/test_proposal_api.py"])

    assert report.accepted is True
    assert report.blocked is False
    assert report.unit_tests_alone_sufficient is False
    assert report.findings[0].compatibility == SchemaCompatibility.COMPATIBLE
    assert report.findings[0].status == "allowed_with_proof"
    assert "warnings" in report.findings[0].changed_fields
    assert "Verify old consumers tolerate missing optional fields." in report.proof_requirements
    assert "Relevant test evidence: tests/test_proposal_api.py" in report.proof_requirements


def test_breaking_response_schema_change_requires_migration_or_blocks() -> None:
    before = _snapshot(
        "api://runtime.status",
        SchemaSurface.API_RESPONSE,
        [
            SchemaField(name="can_execute", field_type="bool", required=True),
            SchemaField(name="status", field_type="str", required=True),
        ],
    )
    after = _snapshot(
        "api://runtime.status",
        SchemaSurface.API_RESPONSE,
        [
            SchemaField(name="can_execute", field_type="str", required=True),
            SchemaField(name="blocked_reason", field_type="str", required=True),
        ],
    )

    report = compare_schema_snapshots(before, after)

    assert report.accepted is False
    assert report.blocked is True
    assert report.findings[0].compatibility == SchemaCompatibility.BREAKING
    assert {"can_execute", "status", "blocked_reason"} <= set(report.findings[0].changed_fields)
    assert "Unit tests alone are insufficient for schema-affecting changes." in report.proof_requirements


def test_breaking_schema_with_migration_notes_is_migration_required_not_unit_test_pass() -> None:
    before = _snapshot(
        "persistence://proposal_store",
        SchemaSurface.PERSISTENCE,
        [SchemaField(name="proposal_id", field_type="str", required=True)],
    )
    after = _snapshot(
        "persistence://proposal_store",
        SchemaSurface.PERSISTENCE,
        [
            SchemaField(name="proposal_id", field_type="str", required=True),
            SchemaField(name="revision", field_type="int", required=True),
        ],
    )

    report = compare_schema_snapshots(before, after, migration_notes=["backfill revision=1 for existing rows"])

    assert report.accepted is True
    assert report.blocked is False
    assert report.migration_required is True
    assert report.unit_tests_alone_sufficient is False
    assert report.findings[0].compatibility == SchemaCompatibility.MIGRATION_REQUIRED
    assert "backfill revision=1 for existing rows" in report.proof_requirements


def test_artifact_schema_drift_is_reported_even_when_unit_tests_pass() -> None:
    before = _snapshot(
        "artifact://capsule.manifest",
        SchemaSurface.ARTIFACT,
        [SchemaField(name="package_id", field_type="str", required=True)],
    )
    after = _snapshot(
        "artifact://capsule.manifest",
        SchemaSurface.ARTIFACT,
        [
            SchemaField(name="package_id", field_type="str", required=True),
            SchemaField(name="launch_profiles", field_type="list", required=False),
        ],
    )

    report = compare_schema_snapshots(before, after, tests=["tests/test_capsule_manifest.py"])

    assert report.findings
    assert report.findings[0].surface == SchemaSurface.ARTIFACT
    assert report.unit_tests_alone_sufficient is False
    assert "launch_profiles" in report.findings[0].changed_fields


def test_unknown_schema_confidence_remains_advisory_but_visible() -> None:
    report = compare_schema_snapshots(None, None)

    assert report.accepted is False
    assert report.blocked is False
    assert report.findings[0].compatibility == SchemaCompatibility.UNKNOWN
    assert report.findings[0].status == "advisory"
    assert "No schema snapshots were provided" in report.findings[0].message
