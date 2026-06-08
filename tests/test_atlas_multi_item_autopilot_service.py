from pathlib import Path
from types import SimpleNamespace

from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest
from agent.atlas_multi_item_autopilot_service import AtlasMultiItemAutopilotService, _repair_subphase_detail
from agent.atlas_multi_item_autopilot_policies import list_multi_item_policies
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_requirement_tracer import AtlasRequirementTracer
from agent.test_command_runner import TestCommandRunner


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


def test_repair_subphase_detail_accepts_self_correction_int_attempts():
    # self_correction reports ``attempts`` as an int count (bounded_retry uses a
    # list). This used to raise "'int' object is not iterable" and get mislabeled
    # as safe_apply_exception even though safe_apply had already succeeded.
    detail = _repair_subphase_detail({"status": "exhausted", "attempts": 2})
    assert detail == {"attempt_count": 2, "attempts": []}


def test_repair_subphase_detail_accepts_bounded_retry_list_attempts():
    detail = _repair_subphase_detail(
        {"attempt_count": 1, "attempts": [{"status": "retry_skipped"}]}
    )
    assert detail == {"attempt_count": 1, "attempts": [{"status": "retry_skipped"}]}


def test_repair_subphase_detail_handles_missing_and_empty_payload():
    assert _repair_subphase_detail({}) == {"attempt_count": 0, "attempts": []}
    assert _repair_subphase_detail(None) == {"attempt_count": 0, "attempts": []}


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


def test_multi_item_autopilot_continues_after_first_item_pool_coverage_partial(tmp_path):
    (tmp_path / 'tests').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'tests' / 'test_ok.py').write_text('def test_ok():\n    assert True\n', encoding='utf-8')
    shared_pool_done = [
        'Hello World text is visible',
        'Rainbow CSS animation is implemented',
    ]
    pool = AtlasPlanPool(
        pool_id='p1',
        root_goal='Create a Hello World page. Add rainbow CSS animation.',
        project_path=str(tmp_path),
        status='approved',
        items=[
            AtlasPlanItem(
                item_id='item_001',
                pool_id='p1',
                title='Create Hello World scaffold',
                goal='Create Hello World HTML page',
                item_type='implementation',
                risk_level='medium',
                status='ready',
                target_files=['index.html'],
                done_definition=shared_pool_done,
                metadata={
                    'action_type': 'create',
                    'approval': {'decision': 'approved'},
                    'proposed_content': '<!doctype html><h1>Hello World</h1>',
                    'verification': {'command_id': 'pytest_selected', 'test_path': 'tests/test_ok.py'},
                    'original_step_payload': {'title': 'Create Hello World scaffold', 'goal': 'Create Hello World HTML page'},
                },
            ),
            AtlasPlanItem(
                item_id='item_002',
                pool_id='p1',
                title='Add rainbow CSS',
                goal='Add rainbow CSS animation',
                item_type='implementation',
                risk_level='medium',
                status='ready',
                target_files=['index.html'],
                done_definition=shared_pool_done,
                metadata={
                    'action_type': 'update',
                    'approval': {'decision': 'approved'},
                    'proposed_content': '<style>.rainbow{animation:shift 2s infinite;color:hsl(120 80% 50%)}</style>',
                    'verification': {'command_id': 'pytest_selected', 'test_path': 'tests/test_ok.py'},
                    'original_step_payload': {'title': 'Add rainbow CSS', 'goal': 'Add rainbow CSS animation'},
                },
            ),
        ],
        metadata={
            'requirement_trace': AtlasRequirementTracer().extract_requirements(
                'Create a Hello World page. Add rainbow CSS animation.'
            ),
        },
    )
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

    class AutoSafe:
        def execute_one(self, request):
            reloaded = storage.load_pool(request.pool_id)
            item = reloaded.get_item(request.item_id)
            if request.item_id == 'item_001':
                content = '<!doctype html><h1>Hello World</h1>'
            else:
                content = (
                    '<!doctype html><h1>Hello World</h1>'
                    '<style>.rainbow{animation:shift 2s infinite;color:hsl(120 80% 50%)}'
                    '@keyframes shift{from{filter:hue-rotate(0deg)}to{filter:hue-rotate(360deg)}}'
                    '</style>'
                )
            (tmp_path / 'index.html').write_text(content, encoding='utf-8')
            item.metadata.setdefault('safe_apply', {})
            item.metadata['safe_apply'].update({'status': 'applied', 'changed_files': ['index.html']})
            storage.save_pool(reloaded)
            journal.save_plan_pool(reloaded)
            return SimpleNamespace(
                status='applied',
                changed_files=['index.html'],
                model_dump=lambda: {
                    'status': 'applied',
                    'changed_files': ['index.html'],
                    'actual_file_changed': True,
                    'file_results': [{'path': 'index.html', 'status': 'applied'}],
                },
            )

    runner = TestCommandRunner(allowed_commands=['python -m pytest -q', 'pytest -q'])
    svc = AtlasMultiItemAutopilotService(
        storage=storage,
        journal=journal,
        automation_gate=AtlasAutomationGateService(),
        auto_safe_apply_service=AutoSafe(),
        auto_verification_service=AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=runner),
        context_refresh_service=SimpleNamespace(refresh=lambda request: SimpleNamespace(status='available', bundle_id='ctx1')),
        evaluator_service=SimpleNamespace(evaluate=lambda request: SimpleNamespace(metadata={'eval_id': 'ev1'}, decision=SimpleNamespace(model_dump=lambda: {'decision': 'continue'}))),
    )

    out = svc.run(AtlasMultiItemAutopilotRequest(
        pool_id='p1',
        project_path=str(tmp_path),
        policy_id='full_auto_multi_item_v1',
        require_approval=False,
        include_context_refresh=False,
        include_evaluator=False,
        include_harness_provisioning=False,
        include_self_correction=False,
    ))

    assert out.status == 'completed'
    assert out.processed_count == 2
    assert [r.status for r in out.item_results] == ['completed', 'completed']
    assert out.stop_reason == ''
    assert 'requirement_coverage_incomplete' not in out.warnings
    assert out.metadata['quality_rollup']['requirement_coverage']['all_verified'] is True


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


def _manual_required_autopilot(tmp_path):
    """Build an autopilot whose evaluator returns ``manual_required`` after an applied,
    unverifiable change (mirrors a static file whose verification cannot auto-run)."""
    pool = AtlasPlanPool(
        pool_id='p1',
        root_goal='g',
        project_path=str(tmp_path),
        items=[
            AtlasPlanItem(
                item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation',
                risk_level='low', status='ready', target_files=['index.html'],
                metadata={'action_type': 'create', 'approval': {'decision': 'approved'}, 'proposed_content': '<!doctype html><h1>Hi</h1>'},
            )
        ],
    )

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
            return SimpleNamespace(status='applied', changed_files=['index.html'],
                                   model_dump=lambda: {'status': 'applied', 'changed_files': ['index.html'], 'actual_file_changed': True, 'file_results': [{'path': 'index.html', 'status': 'applied'}]})

    class Verification:
        # Verification runs and passes; the evaluator (below) is what conservatively returns
        # manual_required (the post-verification gate runs only when vr is passed/failed).
        def run_after_auto_safe_apply(self, request):
            return SimpleNamespace(status='passed', warnings=[], model_dump=lambda: {'status': 'passed', 'warnings': []})

    evaluator = SimpleNamespace(evaluate=lambda request: SimpleNamespace(
        metadata={'eval_id': 'ev1'},
        decision=SimpleNamespace(model_dump=lambda: {'decision': 'manual_required'}),
    ))
    return AtlasMultiItemAutopilotService(
        storage=Storage(), journal=Journal(), automation_gate=AtlasAutomationGateService(),
        auto_safe_apply_service=AutoSafe(), auto_verification_service=Verification(),
        context_refresh_service=SimpleNamespace(refresh=lambda request: SimpleNamespace(status='available', bundle_id='ctx1')),
        evaluator_service=evaluator,
    )


def test_full_auto_does_not_stop_on_manual_required_with_default_flag(tmp_path):
    # Mirrors the live chat-panel path: it calls /run with policy full_auto_multi_item_v1 and does
    # NOT pass stop_on_manual_required (so it defaults to True). The policy itself drops
    # manual_required from stop_decisions, so an applied change is not paused regardless.
    svc = _manual_required_autopilot(tmp_path)
    out = svc.run(AtlasMultiItemAutopilotRequest(
        pool_id='p1', project_path=str(tmp_path), policy_id='full_auto_multi_item_v1',
        require_approval=False, include_context_refresh=False, include_evaluator=True,
        include_harness_provisioning=False,  # stop_on_manual_required defaults to True
    ))
    assert out.status != 'stopped'
    assert out.item_results[0].status != 'stopped'
    assert out.item_results[0].reason != 'evaluator_manual_required'
    assert out.item_results[0].changed_files == ['index.html']


def test_guarded_policy_still_stops_on_manual_required(tmp_path):
    # Non-full-auto (supervised/guarded) policies keep manual_required in stop_decisions, so the
    # manual-review pause is preserved where it is intended.
    svc = _manual_required_autopilot(tmp_path)
    out = svc.run(AtlasMultiItemAutopilotRequest(
        pool_id='p1', project_path=str(tmp_path), policy_id='guarded_multi_item_v1',
        require_approval=False, include_context_refresh=False, include_evaluator=True,
        include_harness_provisioning=False, stop_on_manual_required=True,
    ))
    assert out.status == 'stopped'
    assert out.item_results[0].reason == 'evaluator_manual_required'
