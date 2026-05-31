from __future__ import annotations

# Ordered verify levels from lowest to highest confidence
VERIFY_LEVELS: list[str] = [
    "applied_only",       # File written; no checks performed
    "static_checked",     # Static analysis / lint / file structure checked
    "syntax_checked",     # Syntax/compile check passed
    "runtime_smoke_checked",  # Runtime smoke test passed (e.g., pytest, browser smoke)
    "requirement_checked",    # All stated requirements verified end-to-end
]

_LEVEL_INDEX: dict[str, int] = {lvl: i for i, lvl in enumerate(VERIFY_LEVELS)}


def verify_level_rank(level: str) -> int:
    """Return the numeric rank of a verify level (higher = more confident)."""
    return _LEVEL_INDEX.get(level, -1)


def is_execution_confirmed(verify_level: str) -> bool:
    """Return True only if verify_level >= runtime_smoke_checked."""
    return verify_level_rank(verify_level) >= verify_level_rank("runtime_smoke_checked")


def is_requirement_confirmed(verify_level: str) -> bool:
    """Return True only if verify_level == requirement_checked."""
    return verify_level == "requirement_checked"


def missing_verify_levels(achieved: str) -> list[str]:
    """Return levels above the achieved level that have not been reached."""
    rank = verify_level_rank(achieved)
    return [lvl for lvl in VERIFY_LEVELS if verify_level_rank(lvl) > rank]


def verify_level_display(verify_level: str) -> str:
    """Return a human-readable status note for the given verify level."""
    if verify_level == "applied_only":
        return "適用のみ・実行検証なし (applied_only)"
    if verify_level == "static_checked":
        return "静的検証済み (static_checked)"
    if verify_level == "syntax_checked":
        return "構文検証済み (syntax_checked)"
    if verify_level == "runtime_smoke_checked":
        return "実行確認済み (runtime_smoke_checked)"
    if verify_level == "requirement_checked":
        return "要件充足確認済み (requirement_checked)"
    return f"不明 ({verify_level})"
