from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.atlas_action_type import normalize_action_type
from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest
from agent.atlas_multi_item_autopilot_service import AtlasMultiItemAutopilotService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_run_quality_rollup import compute_run_quality_rollup


class _NoopJournal:
    def append_event(self, *_args, **_kwargs):
        return None

    def save_plan_pool(self, _pool):
        return None


class _PassingSmoke:
    def verify(self, *_args, **_kwargs):
        return {"status": "browser_smoke_passed"}


class _Runner:
    def run_command(self, *_args, **_kwargs):
        return SimpleNamespace(
            status="passed",
            returncode=0,
            stdout="",
            stderr="",
            warnings=[],
            errors=[],
            model_dump=lambda: {"status": "passed"},
        )


def test_wp8_browser_game_acceptance_verifies_core_behavior_signals(tmp_path: Path) -> None:
    html = """\
<!doctype html><html><body>
<canvas id="game" width="320" height="180"></canvas>
<button id="restart">restart</button>
<script>
const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
let score = 0, lives = 3, gameOver = false;
let player = { x: 20, y: 80 };
let enemies = [{ x: 280, y: 80, vx: -2 }];
let bullets = [];
document.addEventListener('keydown', event => {
  if (event.key === 'ArrowUp') player.y -= 8;
  if (event.key === ' ') bullets.push({ x: player.x + 8, y: player.y });
});
document.getElementById('restart').addEventListener('click', () => {
  score = 0; lives = 3; gameOver = false; enemies = [{ x: 280, y: 80, vx: -2 }];
});
function collision(a, b) { return Math.abs(a.x - b.x) < 14 && Math.abs(a.y - b.y) < 14; }
function update() {
  for (const enemy of enemies) enemy.x += enemy.vx;
  for (const bullet of bullets) bullet.x += 6;
  for (const enemy of enemies) for (const bullet of bullets) if (collision(enemy, bullet)) score += 1;
  if (enemies.some(enemy => collision(enemy, player))) lives -= 1;
  if (lives <= 0) gameOver = true;
}
function draw() {
  update();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillText('score ' + score + ' lives ' + lives + (gameOver ? ' game over' : ''), 10, 20);
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
</script></body></html>
"""
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    item = AtlasPlanItem(
        item_id="game",
        pool_id="pool_1",
        title="Complete browser game",
        goal="player input enemy shooting collision score lives game over restart",
        status="ready",
        target_files=["index.html"],
        done_definition=["player input enemy shooting collision score lives game over restart"],
        metadata={
            "safe_apply": {"status": "applied", "changed_files": ["index.html"]},
            "verification_contract": {
                "contract_id": "canvas_game",
                "expected_signals": [
                    "keydown",
                    "enemies",
                    "bullets",
                    "collision",
                    "score",
                    "lives",
                    "game over",
                    "restart",
                ],
            },
        },
    )
    pool = AtlasPlanPool(pool_id="pool_1", root_goal=item.goal, project_path=str(tmp_path), items=[item])
    storage = AtlasPlanPoolStorage(tmp_path / "ca")
    journal = AtlasJournal(tmp_path / "ca")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    service = AtlasAutoVerificationService(
        journal=journal,
        storage=storage,
        command_runner=_Runner(),
        playwright_verifier=_PassingSmoke(),
    )

    out = service.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id="pool_1", item_id="game", run_id="run_1"))

    assert out.status == "passed"
    assert out.metadata["task_verification_contract"]["contract_id"] == "canvas_game_v1"
    assert out.metadata["task_verification_contract"]["missing_signals"] == []
    assert out.metadata["verify_level"] == "runtime_smoke_checked"
    assert storage.load_pool("pool_1").metadata["task_verification_contracts"]["game"]["status"] == "passed"


def test_wp8_missing_requirement_and_unavailable_verification_do_not_complete(tmp_path: Path) -> None:
    (tmp_path / "score.py").write_text("def score():\n    return 'score implemented'\n", encoding="utf-8")
    pool = AtlasPlanPool(
        pool_id="pool_1",
        root_goal="score and persistence",
        project_path=str(tmp_path),
        automation_level="full_autopilot",
        items=[],
        metadata={
            "requirement_trace": [
                {"requirement_id": "req_score", "description": "score implemented", "required": True},
                {"requirement_id": "req_persist", "description": "persistence reload", "required": True},
            ]
        },
    )
    rollup = compute_run_quality_rollup(
        pool,
        [SimpleNamespace(status="completed", changed_files=["score.py"], verification_result={"status": "passed"})],
        project_path=str(tmp_path),
    )
    assert rollup["degraded"] is True
    assert rollup["requirement_coverage"]["success_eligible"] is False
    assert "req_persist" in rollup["requirement_coverage"]["incomplete_requirement_ids"]

    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_2",
        title="Apply unverified code",
        goal="valid result",
        status="ready",
        target_files=["app.py"],
        metadata={"action_type": "create", "proposed_content": "def value():\n    return 'valid result'\n"},
    )
    pool_2 = AtlasPlanPool(pool_id="pool_2", root_goal="valid result", project_path=str(tmp_path), items=[item])

    class _Storage:
        def load_pool(self, _pool_id):
            return pool_2

        def save_pool(self, _pool):
            return None

    class _AutoSafe:
        def execute_one(self, _request):
            return SimpleNamespace(
                status="applied",
                changed_files=["app.py"],
                model_dump=lambda: {
                    "status": "applied",
                    "changed_files": ["app.py"],
                    "actual_file_changed": True,
                    "file_results": [{"path": "app.py", "status": "applied"}],
                },
            )

    class _Verification:
        def run_after_auto_safe_apply(self, _request):
            return SimpleNamespace(
                status="blocked",
                warnings=["test_harness_unavailable", "pytest_not_installed"],
                model_dump=lambda: {"status": "blocked", "warnings": ["test_harness_unavailable", "pytest_not_installed"]},
            )

    service = AtlasMultiItemAutopilotService(
        storage=_Storage(),
        journal=_NoopJournal(),
        automation_gate=SimpleNamespace(decide_pre_safe_apply=lambda *_args, **_kwargs: SimpleNamespace(decision="allow", reasons=[])),
        auto_safe_apply_service=_AutoSafe(),
        auto_verification_service=_Verification(),
        context_refresh_service=SimpleNamespace(refresh=lambda _request: SimpleNamespace(status="available", bundle_id="ctx1")),
        evaluator_service=SimpleNamespace(evaluate=lambda _request: SimpleNamespace(metadata={}, decision=SimpleNamespace(model_dump=lambda: {"decision": "continue"}))),
    )

    out = service.run(
        AtlasMultiItemAutopilotRequest(
            pool_id="pool_2",
            project_path=str(tmp_path),
            policy_id="full_auto_multi_item_v1",
            require_approval=False,
            include_context_refresh=False,
            include_evaluator=False,
            include_harness_provisioning=False,
            include_self_correction=False,
        )
    )

    assert out.status != "completed"
    assert out.item_results[0].status == "blocked"
    assert out.item_results[0].reason == "verification_unavailable_harness_missing"


def test_wp8_legacy_fallback_and_unknown_action_audit_paths_fail_closed(tmp_path: Path) -> None:
    assert normalize_action_type("mystery") == ""

    pool = AtlasPlanPool(pool_id="pool_1", root_goal="legacy fallback audit", project_path=str(tmp_path))
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Unknown action",
        goal="do not create unknown",
        status="ready",
        target_files=["unknown.txt"],
        metadata={"action_type": "mystery", "proposed_content": "TODO should not be written\n"},
    )
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out["status"] == "blocked"
    assert "unsupported_action_type" in out["reasons"]
    assert not (tmp_path / "unknown.txt").exists()

    legacy_text = Path("agent/implementation_executor.py").read_text(encoding="utf-8")
    proposal_text = Path("agent/atlas_patch_proposal_service.py").read_text(encoding="utf-8")
    assert 'raise RuntimeError("skeleton create path is disabled; use full-content generation")' in legacy_text
    assert "append fallback is not allowed" in legacy_text
    assert "Empty/unknown action_type defaults to create" not in proposal_text
