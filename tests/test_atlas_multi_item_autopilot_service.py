from pathlib import Path
from types import SimpleNamespace

from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest
from agent.atlas_multi_item_autopilot_service import AtlasMultiItemAutopilotService
from agent.atlas_multi_item_autopilot_policies import list_multi_item_policies
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def test_policies_present():
    ids = {p.policy_id for p in list_multi_item_policies()}
    assert 'guarded_multi_item_v1' in ids
    assert 'dry_run_multi_item_v1' in ids


def test_no_forbidden_strings():
    t = Path('agent/atlas_multi_item_autopilot_service.py').read_text(encoding='utf-8')
    assert 'shell=True' not in t
    assert 'git push' not in t


def test_multi_item_autopilot_metadata_includes_queue_only_summary():
    t = Path('agent/atlas_multi_item_autopilot_service.py').read_text(encoding='utf-8')
    assert '"queue_only": True' in t
    assert '"next_action_executed": False' in t


def test_full_auto_multi_item_passes_full_auto_preset(tmp_path):
    pool = AtlasPlanPool(
        pool_id='p1',
        root_goal='g',
        project_path=str(tmp_path),
        items=[
            AtlasPlanItem(
                item_id='i1',
                pool_id='p1',
                title='t',
                goal='g',
                item_type='implementation',
                risk_level='medium',
                status='ready',
                target_files=['a.txt'],
                metadata={'action_type': 'create', 'approval': {'decision': 'approved'}, 'proposed_content': 'a\n'},
            )
        ],
    )
    captured = {}

    class Storage:
        def load_pool(self, pool_id):
            return pool
        def save_pool(self, p):
            pass

    class Journal:
        def append_event(self, *args, **kwargs):
            pass

    class AutoSafe:
        def execute_one(self, request):
            captured['preset_id'] = request.preset_id
            return SimpleNamespace(
                status='applied',
                changed_files=['a.txt'],
                model_dump=lambda: {'status': 'applied', 'changed_files': ['a.txt'], 'actual_file_changed': True, 'file_results': [{'path': 'a.txt', 'status': 'applied'}]},
            )

    class Verification:
        def run_after_auto_safe_apply(self, request):
            return SimpleNamespace(status='skipped', warnings=['verification_command_missing'], model_dump=lambda: {'status': 'skipped', 'warnings': ['verification_command_missing']})

    svc = AtlasMultiItemAutopilotService(
        storage=Storage(),
        journal=Journal(),
        automation_gate=AtlasAutomationGateService(),
        auto_safe_apply_service=AutoSafe(),
        auto_verification_service=Verification(),
        context_refresh_service=SimpleNamespace(refresh=lambda request: SimpleNamespace(status='available', bundle_id='ctx1')),
        evaluator_service=SimpleNamespace(evaluate=lambda request: SimpleNamespace(metadata={'eval_id': 'ev1'}, decision=SimpleNamespace(model_dump=lambda: {'decision': 'continue'}))),
    )
    out = svc.run(AtlasMultiItemAutopilotRequest(pool_id='p1', project_path=str(tmp_path), policy_id='full_auto_multi_item_v1', require_approval=False, include_context_refresh=False, include_evaluator=False))
    assert captured['preset_id'] == 'full_auto'
    assert out.item_results[0].changed_files == ['a.txt']
    phases = out.item_results[0].sub_phases
    assert [p["name"] for p in phases] == ["safe_apply", "verify", "done"]
    assert phases[0]["detail"]["changed_files"] == ["a.txt"]
    assert phases[1]["detail"]["output_summary"] == ""


def test_self_correction_receives_actual_changed_files_and_file_results(tmp_path):
    pool = AtlasPlanPool(
        pool_id='p1',
        root_goal='g',
        project_path=str(tmp_path),
        items=[
            AtlasPlanItem(
                item_id='i1',
                pool_id='p1',
                title='t',
                goal='g',
                item_type='implementation',
                risk_level='medium',
                status='ready',
                target_files=['planned.txt'],
                metadata={'action_type': 'create', 'proposed_content': 'a\n'},
            )
        ],
    )
    captured = {}
    file_results = [{'path': 'actual.txt', 'status': 'applied'}]

    class Storage:
        def load_pool(self, pool_id):
            return pool
        def save_pool(self, p):
            pass

    class Journal:
        def append_event(self, *args, **kwargs):
            pass

    class AutoSafe:
        def execute_one(self, request):
            return SimpleNamespace(
                status='applied',
                changed_files=['actual.txt'],
                model_dump=lambda: {
                    'status': 'applied',
                    'changed_files': ['actual.txt'],
                    'actual_file_changed': True,
                    'metadata': {'file_results': file_results},
                },
            )

    class Verification:
        def run_after_auto_safe_apply(self, request):
            return SimpleNamespace(status='failed', warnings=[], model_dump=lambda: {'status': 'failed', 'warnings': []})

    class SelfCorrection:
        def run(self, request):
            captured['changed_files'] = request.changed_files
            captured['file_results'] = request.file_results
            return SimpleNamespace(status='exhausted', changed_files=[], model_dump=lambda: {'status': 'exhausted'})

    svc = AtlasMultiItemAutopilotService(
        storage=Storage(),
        journal=Journal(),
        automation_gate=AtlasAutomationGateService(),
        auto_safe_apply_service=AutoSafe(),
        auto_verification_service=Verification(),
        context_refresh_service=SimpleNamespace(refresh=lambda request: SimpleNamespace(status='available', bundle_id='ctx1')),
        evaluator_service=SimpleNamespace(evaluate=lambda request: SimpleNamespace(metadata={'eval_id': 'ev1'}, decision=SimpleNamespace(model_dump=lambda: {'decision': 'continue'}))),
        self_correction_service=SelfCorrection(),
    )

    svc.run(AtlasMultiItemAutopilotRequest(pool_id='p1', project_path=str(tmp_path), policy_id='full_auto_multi_item_v1', require_approval=False, include_context_refresh=False, include_evaluator=False, include_harness_provisioning=False, include_self_correction=True))

    assert captured['changed_files'] == ['actual.txt']
    assert captured['file_results'] == file_results


def test_skipped_self_correction_risk_reason_surfaced_as_warning(tmp_path):
    """When the repair loop is skipped because the item's risk level is above the
    auto-reapply threshold, the reason must be visible on the item result and the
    configured risk levels threaded into the self-correction request."""
    pool = AtlasPlanPool(
        pool_id='p1', root_goal='g', project_path=str(tmp_path),
        items=[AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g',
                             item_type='implementation', risk_level='medium', status='ready',
                             target_files=['a.txt'],
                             metadata={'action_type': 'create', 'proposed_content': 'a\n'})],
    )
    captured = {}

    class Storage:
        def load_pool(self, pool_id):
            return pool
        def save_pool(self, p):
            pass

    class Journal:
        def append_event(self, *args, **kwargs):
            pass

    class AutoSafe:
        def execute_one(self, request):
            return SimpleNamespace(status='applied', changed_files=['a.txt'],
                                   model_dump=lambda: {'status': 'applied', 'changed_files': ['a.txt'], 'actual_file_changed': True})

    class Verification:
        def run_after_auto_safe_apply(self, request):
            return SimpleNamespace(status='failed', warnings=['visual_contract_failed'],
                                   model_dump=lambda: {'status': 'failed', 'warnings': ['visual_contract_failed']})

    class SelfCorrection:
        def run(self, request):
            captured['risk_levels'] = request.risk_levels
            return SimpleNamespace(status='skipped', reason='risk_level_not_auto_reapplyable:high',
                                   changed_files=[], model_dump=lambda: {'status': 'skipped', 'reason': 'risk_level_not_auto_reapplyable:high'})

    svc = AtlasMultiItemAutopilotService(
        storage=Storage(), journal=Journal(), automation_gate=AtlasAutomationGateService(),
        auto_safe_apply_service=AutoSafe(), auto_verification_service=Verification(),
        context_refresh_service=SimpleNamespace(refresh=lambda request: SimpleNamespace(status='available', bundle_id='ctx1')),
        evaluator_service=SimpleNamespace(evaluate=lambda request: SimpleNamespace(metadata={'eval_id': 'ev1'}, decision=SimpleNamespace(model_dump=lambda: {'decision': 'continue'}))),
        self_correction_service=SelfCorrection(),
    )

    out = svc.run(AtlasMultiItemAutopilotRequest(
        pool_id='p1', project_path=str(tmp_path), policy_id='full_auto_multi_item_v1',
        require_approval=False, include_context_refresh=False, include_evaluator=False,
        include_harness_provisioning=False, include_self_correction=True,
        self_correction_risk_levels=['low', 'medium', 'high'],
    ))

    assert captured['risk_levels'] == ['low', 'medium', 'high']
    assert 'risk_level_not_auto_reapplyable:high' in out.item_results[0].warnings
