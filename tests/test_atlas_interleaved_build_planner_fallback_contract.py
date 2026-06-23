from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")


def test_planner_fallback_is_declared_before_use_in_build_loop():
    # Regression: the interleaved build loop referenced an UNDECLARED `plannerFallback`, throwing
    # "ReferenceError: Can't find variable: plannerFallback" the moment a content-required item failed
    # patch generation. That aborted the whole build/safety-override flow and surfaced as
    # "Safety override に失敗しました", masking the real per-item failure reason.
    decl = PANEL.index("const plannerFallback =")
    use = PANEL.index("if (plannerFallback && plannerFallback.reason)")
    assert decl < use, "plannerFallback must be declared before it is used"


def test_planner_fallback_recovered_from_warning_or_metadata():
    # The reason is sourced from the structured object when present, else recovered from the
    # "planner_fallback:<reason>" warning the patch service echoes into the result.
    body = PANEL[PANEL.index("const fallbackWarning ="):PANEL.index("let cause =")]
    assert "warnings.map(String).find((w) => w.startsWith('planner_fallback:'))" in body
    assert "resultMeta.planner_fallback" in body
    assert "propMeta.planner_fallback" in body


def test_planner_fallback_cause_is_user_facing():
    # A fallback-skeleton plan must be explained as the cause (plan has no implementation steps),
    # not a generic "blocked" message.
    assert "プランがフォールバック（実装ステップ未生成）のため、パッチ生成できません" in PANEL


def test_blocked_status_short_circuits_retry_loop():
    # A server `blocked` result means generation was refused without invoking the LLM (stateful:
    # plan_revision_required / planner_fallback / clarification open / invalid item). Retrying with the
    # same pool state can only block again, so the loop must stop immediately instead of burning all 5
    # attempts in milliseconds ("retries increment instantly without waiting for the LLM").
    loop = PANEL[PANEL.index("const GEN_MAX_ATTEMPTS = 5;"):PANEL.index("if (hasContent) {")]
    assert "r.data.status === 'blocked'" in loop
    assert "break;" in loop
