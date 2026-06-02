from __future__ import annotations

from pathlib import Path

import main
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_self_correction_schema import AtlasSelfCorrectionRequest
from agent.atlas_self_correction_service import AtlasSelfCorrectionService
from fastapi.testclient import TestClient
from tests.test_atlas_auto_verification_api import _client
from tests.test_atlas_self_correction_service import _FakeApply, _FakePatchService, _FakeVerify


_BROKEN_COLOR_HTML = """\
<!doctype html>
<html><body>
<canvas id="c"></canvas>
<script>
function loop() { requestAnimationFrame(loop); }
requestAnimationFrame(loop);
</script>
</body></html>
"""

_FIXED_COLOR_HTML = """\
<!doctype html>
<html>
<head>
<style>
@keyframes colorShift { from { background-color: hsl(0,100%,50%); } to { background-color: hsl(360,100%,50%); } }
canvas { transform: translateY(0); }
</style>
</head>
<body><canvas id="c"></canvas>
<script>
const ctx = document.getElementById('c').getContext('2d');
let phase = 0;
const amplitude = 24;
const frequency = 0.04;
function loop(t) {
  const y = amplitude * Math.sin(frequency * t + phase);
  ctx.fillStyle = 'hsl(' + ((phase * 60) % 360) + ', 100%, 50%)';
  ctx.fillRect(0, y + 40, 20, 20);
  document.getElementById('c').style.transform = 'translateY(' + y + 'px)';
  phase += 0.02;
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
</script></body></html>
"""


def _create_visual_pool(tmp_path: Path, *, risk_level: str = "low") -> AtlasPlanPool:
    item = AtlasPlanItem(
        item_id="i1",
        pool_id="p1",
        title="visual",
        goal="animate colors on a canvas",
        done_definition=["the canvas animates with changing colors"],
        item_type="implementation",
        risk_level=risk_level,
        status="ready",
        target_files=["index.html"],
        metadata={
            "action_type": "update",
            "approval": {"decision": "approved"},
            "source_proposal_id": "pp_visual",
            "proposed_content": _BROKEN_COLOR_HTML,
        },
    )
    pool = AtlasPlanPool(
        pool_id="p1",
        root_goal="animate colors on a canvas",
        project_path=str(tmp_path),
        status="ready",
        items=[item],
    )
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path, workspace_id="default")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return pool


def _visual_client(tmp_path: Path, llm_json_fn=None) -> TestClient:
    client = _client(tmp_path)
    main.app.state.atlas_llm_json_fn = llm_json_fn
    return client


def test_single_item_safe_apply_and_verify_recovers_visual_contract_failure(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><html><body>old</body></html>", encoding="utf-8")
    calls: list[str] = []

    def llm_json_fn(*_args, **_kwargs):
        calls.append("proposal")
        return {
            "target_files": ["index.html"],
            "proposed_content": _FIXED_COLOR_HTML,
            "risk_level": "low",
            "summary": "repair visual color mutation",
        }

    client = _visual_client(tmp_path, llm_json_fn=llm_json_fn)
    pool = _create_visual_pool(tmp_path)

    res = client.post(
        "/api/atlas/automation/safe-apply-one-and-verify",
        json={"pool_id": pool.pool_id, "item_id": pool.items[0].item_id, "run_id": "r_visual"},
    ).json()

    assert res["status"] == "applied_and_verified"
    vr = res.get("auto_verification_result") or {}
    assert vr["status"] == "passed"
    assert vr["metadata"]["recovered_by_self_correction"] is True
    assert vr["metadata"]["attempt_count"] == 1
    assert vr["metadata"]["final_verification_status"] == "passed"
    assert res.get("failure_stop_suggestion") == {}
    assert calls == ["proposal"]
    assert "hsl(" in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_single_item_no_llm_falls_back_with_skip_reason(tmp_path: Path) -> None:
    if hasattr(main.app.state, "atlas_llm_json_fn"):
        main.app.state.atlas_llm_json_fn = None
    (tmp_path / "index.html").write_text("<!doctype html><html><body>old</body></html>", encoding="utf-8")
    client = _visual_client(tmp_path, llm_json_fn=None)
    pool = _create_visual_pool(tmp_path)

    res = client.post(
        "/api/atlas/automation/safe-apply-one-and-verify",
        json={"pool_id": pool.pool_id, "item_id": pool.items[0].item_id, "run_id": "r_no_llm"},
    ).json()

    assert res["status"] == "applied_but_verification_failed"
    metadata = (res.get("failure_stop_suggestion") or {}).get("metadata") or {}
    assert metadata["self_correction"] == "skipped:no_llm"


def test_visual_missing_color_mutation_repair_instruction_is_generic() -> None:
    svc = AtlasPatchProposalService(journal=object(), storage=object())
    instruction = svc._verification_repair_instruction("visual_missing:color_mutation_signal")
    assert "hsl" in instruction
    assert "rgb" in instruction
    assert "Python テストだけ" in instruction


def test_primary_reason_prefers_specific_visual_missing_signal() -> None:
    svc = AtlasPatchProposalService(journal=object(), storage=object())
    reason = svc._primary_verification_reason({"warnings": ["visual_contract_failed", "visual_missing:color_mutation_signal"]})
    assert reason == "visual_missing:color_mutation_signal"


def test_single_item_self_correction_preserves_high_risk_gate(tmp_path: Path) -> None:
    ca_root = tmp_path / "ca"
    ca_root.mkdir()
    storage = AtlasPlanPoolStorage(ca_root)
    journal = AtlasJournal(ca_root, workspace_id="default")
    item = AtlasPlanItem(
        item_id="i1",
        pool_id="p1",
        title="high",
        goal="high risk change",
        item_type="implementation",
        status="ready",
        risk_level="high",
        target_files=["index.html"],
    )
    storage.save_pool(AtlasPlanPool(pool_id="p1", root_goal="g", project_path=str(tmp_path), items=[item]))
    apply = _FakeApply("applied")
    svc = AtlasSelfCorrectionService(
        storage=storage,
        journal=journal,
        patch_proposal_service=_FakePatchService(has_content=True),
        auto_safe_apply_service=apply,
        auto_verification_service=_FakeVerify(fail_times=0),
    )

    out = svc.run(AtlasSelfCorrectionRequest(pool_id="p1", item_id="i1", run_id="r1", verification_result={"status": "failed"}))

    assert out.status == "skipped"
    assert "risk_level_not_auto_reapplyable" in out.reason
    assert apply.calls == 0
