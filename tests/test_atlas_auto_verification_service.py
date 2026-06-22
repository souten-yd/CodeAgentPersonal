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


def test_auto_verification_auto_derives_pytest_from_test_target(tmp_path):
    # Generic default: no verification command configured, but the item touches a pytest file ->
    # run pytest on it instead of reporting "nothing to verify", so generated code is verified.
    (tmp_path / 'src').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'src' / 'test_calc.py').write_text('def test_ok():\n    assert True\n', encoding='utf-8')
    storage, journal, pool, item = _setup(tmp_path)
    item.target_files = ['src/calc.py', 'src/test_calc.py']  # no metadata['verification']
    storage.save_pool(pool)
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1'))
    assert r.command_id == 'pytest_selected'
    assert r.status == 'passed'


def test_auto_verification_blocks_when_no_test_target_and_no_command(tmp_path):
    # No command and no test-looking target -> still honestly blocked (nothing to verify).
    storage, journal, pool, item = _setup(tmp_path)
    item.target_files = ['src/calc.py']  # not a test file
    storage.save_pool(pool)
    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    r = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1'))
    assert r.status == 'blocked'
    assert 'verification_command_missing' in r.warnings


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


def test_asset_only_step_verifies_through_plan_index_html(tmp_path):
    # Incremental browser-build: step 1 creates index.html + script.js; a later step changes only
    # script.js. That step has no .html target of its own but must still be verified through the
    # plan's index.html (which loads script.js) instead of degrading the run to "nothing to verify".
    storage, journal, pool, item = _setup(tmp_path)
    pool.root_goal = 'Create a basic Space Invaders game with core gameplay mechanics'
    step1 = AtlasPlanItem(item_id='step_1', pool_id=pool.pool_id, title='setup', goal='create files',
                          target_files=['index.html', 'style.css', 'script.js'])
    pool.items = [step1, item]
    item.item_id = 'step_2'
    item.goal = 'Implement player ship movement'
    item.target_files = ['script.js']
    item.metadata['safe_apply']['changed_files'] = ['script.js']
    storage.save_pool(pool)
    (Path(pool.project_path) / 'index.html').write_text(
        '<html><body><canvas></canvas><script src="script.js"></script></body></html>', encoding='utf-8')

    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    assert svc._resolve_visual_html(item, pool) == 'index.html'


def test_asset_only_canvas_game_step_uses_pool_goal_for_visual_contract(tmp_path):
    storage, journal, pool, item = _setup(tmp_path)
    pool.root_goal = (
        'Create a Space Invaders game using HTML where the player can move their ship '
        'using the left and right arrow keys and shoot bullets at enemies by pressing the space bar.'
    )
    pool.metadata['requirement_trace'] = [
        {'requirement_id': 'req_001', 'description': 'インベーダーゲームをHTMLで作って'},
        {'requirement_id': 'req_002', 'description': '左右キーで自機を移動しスペースで弾丸を発射する'},
    ]
    step1 = AtlasPlanItem(
        item_id='step_1',
        pool_id=pool.pool_id,
        title='Create Basic HTML Structure',
        goal='Set up the basic structure for the Space Invaders game.',
        target_files=['index.html'],
    )
    pool.items = [step1, item]
    item.item_id = 'step_4'
    item.goal = 'Enemies move and shoot at the player.'
    item.target_files = ['script.js']
    item.metadata['safe_apply']['changed_files'] = ['script.js']
    item.metadata['original_step_payload'] = {
        'acceptance_criteria': [
            'Enemies move across the screen.',
            'Enemies shoot bullets at the player.',
        ],
        'done_definition': [
            'Enemies move across the screen.',
            'Enemies shoot bullets at the player.',
        ],
    }
    storage.save_pool(pool)
    (Path(pool.project_path) / 'index.html').write_text(
        '<!doctype html><html><body><canvas id="gameCanvas"></canvas>'
        '<script src="script.js"></script></body></html>',
        encoding='utf-8',
    )
    (Path(pool.project_path) / 'script.js').write_text(
        "const canvas = document.getElementById('gameCanvas');\n"
        "const ctx = canvas.getContext('2d');\n"
        "const enemies = [{x: 0, y: 10, isAlive: true}];\n"
        "const enemyBullets = [];\n"
        "function update(){ enemies[0].x += 1; enemyBullets.push({x: enemies[0].x, y: 20}); }\n"
        "setInterval(function(){ ctx.clearRect(0,0,canvas.width,canvas.height); "
        "ctx.fillRect(enemies[0].x, enemies[0].y, 10, 10); update(); }, 10);\n",
        encoding='utf-8',
    )

    class _Smoke:
        def verify(self, *_args, **kwargs):
            assert kwargs.get('contract_id') == 'canvas_game_visual_v1'
            return {'status': 'browser_smoke_passed', 'contract_id': kwargs.get('contract_id')}

    svc = AtlasAutoVerificationService(
        journal=journal,
        storage=storage,
        command_runner=_runner(),
        playwright_verifier=_Smoke(),
    )
    out = svc.run_after_auto_safe_apply(
        AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1')
    )

    assert out.status == 'passed'
    assert out.metadata['visual_contract_id'] == 'canvas_game_visual_v1'
    assert out.metadata['visual_classification']['artifact_type'] == 'canvas_game'
    assert 'Space Invaders game' in out.metadata['visual_classification_context']
    assert 'visual_contract_failed' not in out.warnings


def test_direct_html_step_does_not_inherit_pool_goal_for_visual_classification(tmp_path):
    storage, journal, pool, item = _setup(tmp_path)
    pool.root_goal = 'Create a dashboard, then add a rainbow animation in a later step.'
    item.goal = 'Create the dashboard HTML scaffold.'
    item.target_files = ['index.html']
    item.metadata['safe_apply']['changed_files'] = ['index.html']
    item.metadata['original_step_payload'] = {
        'acceptance_criteria': ['Dashboard heading is visible.'],
    }
    storage.save_pool(pool)

    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())

    assert svc._visual_task_description(item, pool) == 'Create the dashboard HTML scaffold. Dashboard heading is visible.'
    assert svc._visual_classification_description(item, pool) == svc._visual_task_description(item, pool)


def test_asset_step_not_referenced_by_plan_html_stays_unresolved(tmp_path):
    # A test-file step (tests/...js) that no plan page loads must NOT be falsely verified through
    # index.html — it stays unresolved so the missing-test-runner condition is reported honestly.
    storage, journal, pool, item = _setup(tmp_path)
    pool.root_goal = 'Create a basic Space Invaders game with core gameplay mechanics'
    step1 = AtlasPlanItem(item_id='step_1', pool_id=pool.pool_id, title='setup', goal='create files',
                          target_files=['index.html', 'script.js'])
    pool.items = [step1, item]
    item.item_id = 'step_7'
    item.goal = 'write unit tests'
    item.target_files = ['tests/test_game_mechanics.js']
    item.metadata['safe_apply']['changed_files'] = ['tests/test_game_mechanics.js']
    storage.save_pool(pool)
    (Path(pool.project_path) / 'index.html').write_text(
        '<html><body><script src="script.js"></script></body></html>', encoding='utf-8')

    svc = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_runner())
    assert svc._resolve_visual_html(item, pool) == ''


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
