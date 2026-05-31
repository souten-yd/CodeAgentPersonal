from __future__ import annotations

from pathlib import Path

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool

_ANIM_HTML = """\
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
    def append_event(self, *a, **k): pass
    def save_plan_pool(self, pool): pass


class _Storage:
    def __init__(self, pool): self._pool = pool
    def load_pool(self, pid): return self._pool
    def save_pool(self, pool): self._pool = pool


class _PassingRunner:
    """Stub command runner that always returns a passing test result."""
    def run_command(self, *a, **k):
        from types import SimpleNamespace
        return SimpleNamespace(status="passed", returncode=0, stdout="", stderr="",
                               warnings=[], errors=[], model_dump=lambda: {"status": "passed"})


class _FakeSmoke:
    def __init__(self, result): self._r = result
    def verify(self, *a, **k): return self._r


def _pool_item(tmp_path, *, html=_ANIM_HTML, target="index.html", goal="animate a color wave", command_id=None):
    if html is not None:
        (Path(tmp_path) / target).write_text(html, encoding="utf-8")
    meta = {"action_type": "create", "safe_apply": {"status": "applied", "changed_files": [target]}}
    if command_id:
        meta["verification"] = {"command_id": command_id}
    item = AtlasPlanItem(item_id="i1", pool_id="p1", title="t", goal=goal, item_type="implementation",
                         risk_level="low", status="ready", target_files=[target],
                         done_definition=["page shows an animation"], metadata=meta)
    pool = AtlasPlanPool(pool_id="p1", root_goal=goal, project_path=str(tmp_path), items=[item])
    return pool, item


def _svc(pool, *, runner=None, smoke=None):
    return AtlasAutoVerificationService(
        journal=_Journal(), storage=_Storage(pool),
        command_runner=runner or _PassingRunner(),
        playwright_verifier=smoke,
    )


def _req():
    return AtlasAutoVerificationRequest(pool_id="p1", item_id="i1", run_id="r1")


# ── #1 supplemental visual check even with a test command ─────────────────────

def test_passing_test_command_still_fails_on_broken_visual(tmp_path):
    # pytest "passes" but the artifact has no animation/color/motion → visual contract fails
    pool, item = _pool_item(tmp_path, html=_STATIC_HTML, command_id="node_check_dashboard")
    out = _svc(pool, smoke=_FakeSmoke({"status": "browser_smoke_skipped"})).run_after_auto_safe_apply(_req())
    assert out.status == "failed"
    assert "visual_contract_failed" in out.warnings
    assert out.metadata.get("visual_contract", {}).get("status") == "failed"


def test_passing_test_command_and_good_visual_passes(tmp_path):
    pool, item = _pool_item(tmp_path, html=_ANIM_HTML, command_id="node_check_dashboard")
    out = _svc(pool, smoke=_FakeSmoke({"status": "browser_smoke_skipped"})).run_after_auto_safe_apply(_req())
    assert out.status == "passed"
    assert "visual_contract_passed" in out.warnings
    assert out.metadata.get("verify_level") == "static_checked"


# ── #2 hard vs soft browser smoke ─────────────────────────────────────────────

def test_js_error_smoke_is_hard_failure_even_if_static_passes(tmp_path):
    pool, item = _pool_item(tmp_path, html=_ANIM_HTML)  # no command → visual-only path
    smoke = _FakeSmoke({"status": "browser_smoke_failed", "reason": "js_error",
                        "console_errors": ["ReferenceError: x is not defined"]})
    out = _svc(pool, smoke=smoke).run_after_auto_safe_apply(_req())
    assert out.status == "failed"
    assert any(w.startswith("browser_smoke_failed:js_error") for w in out.warnings)


def test_style_sampling_smoke_is_warning_when_static_passes(tmp_path):
    pool, item = _pool_item(tmp_path, html=_ANIM_HTML)
    smoke = _FakeSmoke({"status": "browser_smoke_failed", "reason": "animation_not_detected_no_style_change"})
    out = _svc(pool, smoke=smoke).run_after_auto_safe_apply(_req())
    # Static contract passed → soft smoke failure only warns, does not fail
    assert out.status == "passed"
    assert any(w.startswith("browser_smoke_warning:animation_not_detected") for w in out.warnings)


def test_playwright_error_smoke_is_soft_warning(tmp_path):
    pool, item = _pool_item(tmp_path, html=_ANIM_HTML)
    smoke = _FakeSmoke({"status": "browser_smoke_failed", "reason": "playwright_error: timeout"})
    out = _svc(pool, smoke=smoke).run_after_auto_safe_apply(_req())
    assert out.status == "passed"
    assert any(w.startswith("browser_smoke_warning:playwright_error") for w in out.warnings)


def test_browser_smoke_passed_lifts_verify_level(tmp_path):
    pool, item = _pool_item(tmp_path, html=_ANIM_HTML)
    smoke = _FakeSmoke({"status": "browser_smoke_passed"})
    out = _svc(pool, smoke=smoke).run_after_auto_safe_apply(_req())
    assert out.status == "passed"
    assert out.metadata.get("verify_level") == "runtime_smoke_checked"
