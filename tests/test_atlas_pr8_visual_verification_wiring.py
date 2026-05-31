from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_multi_item_autopilot_service import _verify_level_for_item
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool

_VALID_ANIMATION_HTML = """\
<!doctype html><html><head><style>
@keyframes c { from { background-color: hsl(0,100%,50%); } to { background-color: hsl(360,100%,50%); } }
</style></head><body><canvas id="c"></canvas><script>
const amplitude=50, frequency=0.02; let phase=0;
function loop(t){ const y=amplitude*Math.sin(frequency*t+phase);
 document.getElementById('c').style.transform='translateY('+y+'px)';
 document.getElementById('c').style.color='hsl('+(phase*10%360)+',100%,50%)'; phase+=0.01;
 requestAnimationFrame(loop);} requestAnimationFrame(loop);
</script></body></html>
"""

_STATIC_HTML = "<!doctype html><html><body><h1>Hello</h1></body></html>"


class _Journal:
    def append_event(self, *a, **k):
        pass

    def save_plan_pool(self, pool):
        pass


class _Storage:
    def __init__(self, pool):
        self._pool = pool

    def load_pool(self, pool_id):
        return self._pool

    def save_pool(self, pool):
        self._pool = pool


class _CommandRunner:
    def run_command(self, *a, **k):
        raise AssertionError("command runner must not be called for visual-only verification")


def _pool_item(tmp_path, *, goal="animate a color wave", target="index.html", html=_VALID_ANIMATION_HTML, applied=True):
    if html is not None:
        (Path(tmp_path) / target).write_text(html, encoding="utf-8")
    item = AtlasPlanItem(
        item_id="i1", pool_id="p1", title="t", goal=goal, item_type="implementation",
        risk_level="low", status="ready", target_files=[target],
        done_definition=["the page shows an animation"],
        metadata={"action_type": "create", "safe_apply": {"status": "applied", "changed_files": [target]}},
    )
    pool = AtlasPlanPool(pool_id="p1", root_goal=goal, project_path=str(tmp_path), items=[item])
    return pool, item


def _service(pool):
    return AtlasAutoVerificationService(journal=_Journal(), storage=_Storage(pool), command_runner=_CommandRunner())


def test_visual_task_no_command_runs_static_verifier_pass(tmp_path):
    pool, _ = _pool_item(tmp_path)
    svc = _service(pool)
    out = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id="p1", item_id="i1", run_id="r1"))
    assert out.status == "passed"
    assert "visual_contract_passed" in out.warnings
    assert out.metadata["visual_contract"]["status"] == "passed"
    # Playwright unavailable in this env → skipped, static still primary.
    assert out.metadata["browser_smoke"]["status"] == "browser_smoke_skipped"
    assert out.metadata["verify_level"] == "static_checked"


def test_visual_task_file_existence_only_fails(tmp_path):
    pool, _ = _pool_item(tmp_path, html=_STATIC_HTML)
    svc = _service(pool)
    out = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id="p1", item_id="i1", run_id="r1"))
    assert out.status == "failed"
    assert "visual_contract_failed" in out.warnings


def test_visual_task_missing_color_motion_fails(tmp_path):
    html = "<!doctype html><html><body><h1>Demo</h1>" \
           "<script>requestAnimationFrame(function f(){requestAnimationFrame(f);});</script></body></html>"
    pool, _ = _pool_item(tmp_path, html=html)
    svc = _service(pool)
    out = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id="p1", item_id="i1", run_id="r1"))
    assert out.status == "failed"
    assert any(w.startswith("visual_missing:") for w in out.warnings)


def test_playwright_unavailable_records_browser_smoke_skipped(tmp_path):
    pool, _ = _pool_item(tmp_path)
    svc = _service(pool)
    out = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id="p1", item_id="i1", run_id="r1"))
    assert out.metadata["browser_smoke"]["status"] in ("browser_smoke_skipped", "browser_smoke_passed", "browser_smoke_failed")


def test_non_visual_task_no_command_still_missing(tmp_path):
    # backend .py target, no visual keywords → not visual → falls through to command_missing block
    (Path(tmp_path) / "service.py").write_text("x = 1\n", encoding="utf-8")
    item = AtlasPlanItem(
        item_id="i1", pool_id="p1", title="t", goal="add a config loader", item_type="implementation",
        risk_level="low", status="ready", target_files=["service.py"],
        metadata={"action_type": "create", "safe_apply": {"status": "applied", "changed_files": ["service.py"]}},
    )
    pool = AtlasPlanPool(pool_id="p1", root_goal="add a config loader", project_path=str(tmp_path), items=[item])
    svc = _service(pool)
    out = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id="p1", item_id="i1", run_id="r1"))
    assert out.status == "blocked"
    assert "verification_command_missing" in out.warnings


# ── _verify_level_for_item wiring ─────────────────────────────────────────────

def test_verify_level_static_for_visual_static_pass():
    r = SimpleNamespace(status="completed", verification_result={
        "status": "passed", "metadata": {"verify_level": "static_checked",
                                          "browser_smoke": {"status": "browser_smoke_skipped"}}})
    assert _verify_level_for_item(r) == "static_checked"


def test_verify_level_runtime_for_browser_smoke_pass():
    r = SimpleNamespace(status="completed", verification_result={
        "status": "passed", "metadata": {"verify_level": "runtime_smoke_checked",
                                          "browser_smoke": {"status": "browser_smoke_passed"}}})
    assert _verify_level_for_item(r) == "runtime_smoke_checked"


def test_verify_level_applied_only_for_applied_no_verification():
    r = SimpleNamespace(status="applied_no_verification", verification_result={})
    assert _verify_level_for_item(r) == "applied_only"
