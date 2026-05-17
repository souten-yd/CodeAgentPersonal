from pathlib import Path

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
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
    pool = AtlasPlanPoolBuilder().build_fallback_pool(root_goal='x', project_path=str(tmp_path), project_name='p')
    item = pool.items[0]
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
