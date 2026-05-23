from pathlib import Path

def test_execution_safety_boundary_component_exists_and_display_only() -> None:
    text = Path('web/atlas-next/src/components/ExecutionSafetyBoundary.vue').read_text(encoding='utf-8').lower()
    for marker in ['execution safety boundary (display-only)','runtime level:','backend workflow_state authoritative','vue execution enabled:','autonomous execution enabled:','readiness gate checklist','snapshot/restore readiness','patch transaction readiness','risk classification','allowlisted verification','dry-run/approval','rollback readiness','artifact capture','stop/kill switch','loop bounds','remote git restrictions','self-improvement gates','no execution endpoint is called from vue','default-enable checkpoint only; not execution-enable']:
        assert marker in text
    for banned in ['<button', '@click', 'submit', 'fetch(', 'atlasclient']:
        assert banned not in text
