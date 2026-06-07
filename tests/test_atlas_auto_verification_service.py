from pathlib import Path

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_requirement_tracer import AtlasRequirementTracer
from agent.test_command_runner import TestCommandRunner


def _runner():
    return TestCommandRunner(allowed_commands=[
        "python -m pytest -q",
        "pytest -q",
        "node --check",
        "python -m py_compile",
        "python -m json.tool",
        "python scripts/check_ui_inline_script_syntax.py",
    ])


def _setup(tmp_path):
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    item = AtlasPlanItem(
        item_id='item_001',
        pool_id='pool_1',
        title='Verify explicit item',
        goal='',
        item_type='implementation',
        status='ready',
        target_files=[],
        metadata={'action_type': 'update'},
    )
    pool = AtlasPlanPool(pool_id='pool_1', root_goal='x', project_path=str(tmp_path), project_name='p', items=[item])
    item.metadata.setdefault('safe_apply', {})['status'] = 'applied'
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return storage, journal, pool, item


def test_auto_verification_blocks_arbitrary_command(tmp_path):
    storage, journal, pool, item = _setup(tmp_path)
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1', metadata={'command':'echo hi'}))
    assert r.status == 'blocked'
    assert 'arbitrary_command_forbidden' in r.warnings


def test_auto_verification_blocks_unsafe_test_path(tmp_path):
    storage, journal, pool, item = _setup(tmp_path)
    item.metadata['verification'] = {'command_id': 'pytest_selected', 'test_path': '../secret'}
    storage.save_pool(pool)
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1'))
    assert r.status == 'blocked'
    assert 'unsafe_path' in r.warnings


def test_auto_verification_blocks_missing_project_path(tmp_path):
    storage, journal, pool, item = _setup(tmp_path)
    pool.project_path = ''
    item.metadata['verification'] = {'command_id': 'pytest_selected', 'test_path': 'tests/test_ok.py'}
    storage.save_pool(pool)
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1'))
    assert r.status == 'blocked'
    assert 'project_path_missing' in (r.warnings + r.errors)


def test_auto_verification_safe_apply_not_applied_includes_safe_apply_details(tmp_path):
    storage, journal, pool, item = _setup(tmp_path)
    item.metadata['safe_apply'] = {
        'status': 'blocked',
        'reasons': ['multi_file_preflight_failed'],
        'file_results': [{'path': 'style.css', 'status': 'blocked', 'reason': 'content_missing'}],
        'changed_files': [],
        'actual_file_changed': False,
    }
    storage.save_pool(pool)
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1'))
    assert r.status == 'skipped'
    assert 'safe_apply_not_applied' in r.warnings
    summary = r.orchestration_summary['safe_apply_not_applied']
    assert summary['reasons'] == ['multi_file_preflight_failed']
    assert summary['file_results'][0]['reason'] == 'content_missing'


def test_auto_verification_passes_allowlisted_pytest(tmp_path):
    (tmp_path / 'tests').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'tests' / 'test_ok.py').write_text('def test_ok():\n    assert True\n', encoding='utf-8')
    storage, journal, pool, item = _setup(tmp_path)
    item.metadata['verification'] = {'command_id': 'pytest_selected', 'test_path': 'tests/test_ok.py'}
    storage.save_pool(pool)
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1'))
    assert r.command_id == 'pytest_selected'
    assert r.status == 'passed'
    assert r.exit_code == 0
    reloaded_pool = storage.load_pool(pool.pool_id)
    reloaded_item = next(i for i in reloaded_pool.items if i.item_id == item.item_id)
    assert 'auto_verification' in (reloaded_item.metadata or {})
    assert ((reloaded_item.metadata.get('auto_verification') or {}).get('status')) == 'passed'
    events_path = tmp_path / "atlas" / "workspaces" / "default" / "plan_pools" / pool.pool_id / "pipeline_runs" / "r1" / "events.ndjson"
    events_text = events_path.read_text(encoding="utf-8") if events_path.exists() else ""
    assert "\"event_type\": \"auto_verification_passed\"" in events_text
    assert "\"event_type\": \"auto_verification_failed\"" not in events_text


def test_auto_verification_fails_when_acceptance_content_is_missing(tmp_path):
    (tmp_path / 'tests').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'tests' / 'test_ok.py').write_text('def test_ok():\n    assert True\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('def greet():\n    return "Hi"\n', encoding='utf-8')
    storage, journal, pool, item = _setup(tmp_path)
    item.goal = 'Expose Hello World greeting'
    item.done_definition = ['Hello World appears in app output']
    item.target_files = ['app.py']
    item.metadata['safe_apply']['changed_files'] = ['app.py']
    item.metadata['verification'] = {'command_id': 'pytest_selected', 'test_path': 'tests/test_ok.py'}
    storage.save_pool(pool)
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1'))
    assert r.status == 'failed'
    assert 'requirement_coverage_incomplete' in r.warnings
    coverage = r.metadata['requirement_coverage']
    assert coverage['success_eligible'] is False
    assert coverage['by_status']['missing'] >= 1


def test_auto_verification_records_requirement_coverage_when_acceptance_matches(tmp_path):
    (tmp_path / 'tests').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'tests' / 'test_ok.py').write_text('def test_ok():\n    assert True\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('def greet():\n    return "Hello World"\n', encoding='utf-8')
    storage, journal, pool, item = _setup(tmp_path)
    item.goal = 'Expose Hello World greeting'
    item.done_definition = ['Hello World appears in app output']
    item.target_files = ['app.py']
    item.metadata['safe_apply']['changed_files'] = ['app.py']
    item.metadata['verification'] = {'command_id': 'pytest_selected', 'test_path': 'tests/test_ok.py'}
    storage.save_pool(pool)
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1'))
    assert r.status == 'passed'
    assert r.metadata['requirement_coverage']['success_eligible'] is True
    assert r.metadata['requirement_coverage']['by_status']['verified'] >= 1


def test_auto_verification_allows_first_item_when_pool_requirement_is_incomplete(tmp_path):
    (tmp_path / 'tests').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'tests' / 'test_ok.py').write_text('def test_ok():\n    assert True\n', encoding='utf-8')
    (tmp_path / 'index.html').write_text('<!doctype html><h1>Hello World</h1>', encoding='utf-8')
    shared_pool_done = [
        'Hello World text is visible',
        'Rainbow CSS animation is implemented',
    ]
    item_1 = AtlasPlanItem(
        item_id='item_001',
        pool_id='pool_1',
        title='Create Hello World scaffold',
        goal='Create Hello World HTML page',
        status='ready',
        target_files=['index.html'],
        done_definition=shared_pool_done,
        metadata={
            'safe_apply': {'status': 'applied', 'changed_files': ['index.html']},
            'verification': {'command_id': 'pytest_selected', 'test_path': 'tests/test_ok.py'},
            'original_step_payload': {'title': 'Create Hello World scaffold', 'goal': 'Create Hello World HTML page'},
        },
    )
    item_2 = AtlasPlanItem(
        item_id='item_002',
        pool_id='pool_1',
        title='Add rainbow CSS',
        goal='Add rainbow CSS animation',
        status='queued',
        target_files=['index.html'],
        done_definition=shared_pool_done,
        metadata={'original_step_payload': {'title': 'Add rainbow CSS', 'goal': 'Add rainbow CSS animation'}},
    )
    pool = AtlasPlanPool(
        pool_id='pool_1',
        root_goal='Create a Hello World page. Add rainbow CSS animation.',
        project_path=str(tmp_path),
        status='approved',
        items=[item_1, item_2],
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

    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id='pool_1', item_id='item_001', run_id='r1'))

    assert r.status == 'passed'
    assert 'requirement_coverage_incomplete' not in r.warnings
    item_coverage = r.metadata['requirement_coverage']
    assert item_coverage['scope'] == 'item'
    assert item_coverage['success_eligible'] is True
    assert item_coverage['by_status']['verified'] >= 1
    pool_coverage = r.metadata['pool_requirement_coverage']
    assert pool_coverage['scope'] == 'pool'
    assert pool_coverage['progress_only'] is True
    assert pool_coverage['all_verified'] is False
    assert pool_coverage['by_status'].get('partial', 0) >= 1


def test_auto_verification_fails_but_does_not_restore_debug_or_patch(tmp_path):
    (tmp_path / 'tests').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'tests' / 'test_fail.py').write_text('def test_fail():\n    assert False\n', encoding='utf-8')
    storage, journal, pool, item = _setup(tmp_path)
    item.metadata['verification'] = {'command_id': 'pytest_selected', 'test_path': 'tests/test_fail.py'}
    storage.save_pool(pool)
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1'))
    assert r.status == 'failed'
    assert r.exit_code != 0
    reloaded_pool = storage.load_pool(pool.pool_id)
    reloaded_item = next(i for i in reloaded_pool.items if i.item_id == item.item_id)
    events_path = tmp_path / "atlas" / "workspaces" / "default" / "plan_pools" / pool.pool_id / "pipeline_runs" / "r1" / "events.ndjson"
    events_text = events_path.read_text(encoding="utf-8") if events_path.exists() else ""
    assert "\"event_type\": \"auto_verification_failed\"" in events_text
    assert "\"event_type\": \"auto_verification_passed\"" not in events_text
    assert "\"event_type\": \"change_snapshot_restore_manual_started\"" not in events_text
    assert "\"event_type\": \"change_snapshot_restore_auto_started\"" not in events_text
    assert "\"event_type\": \"auto_rollback_started\"" not in events_text
    assert "\"event_type\": \"debug_review_manual_started\"" not in events_text
    assert "\"event_type\": \"debug_review_auto_started\"" not in events_text
    assert "\"event_type\": \"patch_proposal_manual_started\"" not in events_text
    assert "\"event_type\": \"patch_proposal_auto_started\"" not in events_text


def test_visual_html_resolution_prefers_index_html(tmp_path):
    storage, journal, pool, item = _setup(tmp_path)
    item.goal = 'animate color page'
    item.target_files = ['landing.html', 'index.html']
    item.metadata['safe_apply']['changed_files'] = ['landing.html', 'index.html']
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())

    assert svc._resolve_visual_html(item, pool) == 'index.html'


def test_css_only_visual_task_blocks_without_entry_html(tmp_path):
    (tmp_path / 'styles.css').write_text('.hello { transition: color 1s; color: red; }\n', encoding='utf-8')
    storage, journal, pool, item = _setup(tmp_path)
    item.goal = 'animate text color with CSS'
    item.target_files = ['styles.css']
    item.metadata['safe_apply']['changed_files'] = ['styles.css']
    storage.save_pool(pool)

    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1'))

    assert r.status == 'blocked'
    assert 'verification_command_missing' in r.warnings
