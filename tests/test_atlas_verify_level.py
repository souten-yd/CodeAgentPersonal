from __future__ import annotations

from agent.atlas_verify_level_schema import (
    VERIFY_LEVELS,
    is_execution_confirmed,
    is_requirement_confirmed,
    missing_verify_levels,
    verify_level_display,
    verify_level_rank,
)


def test_levels_are_ordered():
    ranks = [verify_level_rank(lvl) for lvl in VERIFY_LEVELS]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks)  # all unique


def test_applied_only_is_lowest():
    assert verify_level_rank("applied_only") == 0


def test_requirement_checked_is_highest():
    assert verify_level_rank("requirement_checked") == verify_level_rank(VERIFY_LEVELS[-1])


def test_execution_not_confirmed_below_runtime_smoke():
    for lvl in ("applied_only", "static_checked", "syntax_checked"):
        assert is_execution_confirmed(lvl) is False, f"Expected False for {lvl}"


def test_execution_confirmed_at_runtime_smoke_and_above():
    for lvl in ("runtime_smoke_checked", "requirement_checked"):
        assert is_execution_confirmed(lvl) is True, f"Expected True for {lvl}"


def test_requirement_not_confirmed_below_requirement_checked():
    for lvl in ("applied_only", "static_checked", "syntax_checked", "runtime_smoke_checked"):
        assert is_requirement_confirmed(lvl) is False


def test_requirement_confirmed_only_at_requirement_checked():
    assert is_requirement_confirmed("requirement_checked") is True


def test_missing_verify_levels_for_applied_only():
    missing = missing_verify_levels("applied_only")
    assert "runtime_smoke_checked" in missing
    assert "requirement_checked" in missing
    assert "applied_only" not in missing


def test_missing_verify_levels_for_requirement_checked():
    assert missing_verify_levels("requirement_checked") == []


def test_display_applied_only_contains_keyword():
    d = verify_level_display("applied_only")
    assert "適用のみ" in d
    assert "実行検証なし" in d


def test_display_runtime_smoke_checked_contains_keyword():
    d = verify_level_display("runtime_smoke_checked")
    assert "実行確認済み" in d
