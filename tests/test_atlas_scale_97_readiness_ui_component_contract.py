from pathlib import Path


def test_scale_97_readiness_component_exists_and_display_fields() -> None:
    t = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    for field in [
        'enabled', 'runtime_level', 'level1_execution_enabled', 'callable_execution_endpoint_enabled',
        'vue_execution_controls_enabled', 'advisory_only', 'mutation_performed', 'execution_performed',
        'required_gate_count', 'missing_evidence_count', 'satisfied_gate_count', 'unsatisfied_gate_count',
        'gate_id', 'label', 'owner', 'source', 'evidence_required', 'evidence_available', 'current_status',
        'blocker_reason', 'test_requirement', 'mutable'
    ]:
        assert field in t
    for banned in ['execute', 'apply', 'approve', 'verify', 'rollback', 'retry', 'continue']:
        assert banned not in t.lower()
