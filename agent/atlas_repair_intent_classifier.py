from __future__ import annotations

import re

# Keywords/patterns indicating a repair/fix intent
_REPAIR_PATTERNS = [
    re.compile(r'\bnot\s+chang\w*\b', re.IGNORECASE),
    re.compile(r'\bnot\s+mov\w*\b', re.IGNORECASE),
    re.compile(r"\bdon'?t\s+work\b", re.IGNORECASE),
    re.compile(r"\bdoes\s+not\s+work\b", re.IGNORECASE),
    re.compile(r"\bdoesn'?t\s+work\b", re.IGNORECASE),
    re.compile(r'\bnot\s+work\w*\b', re.IGNORECASE),
    re.compile(r'直ってない', re.IGNORECASE),
    re.compile(r'変わってない', re.IGNORECASE),
    re.compile(r'動いていない', re.IGNORECASE),
    re.compile(r'\b失敗\b'),
    re.compile(r'\bbug\b', re.IGNORECASE),
    re.compile(r'\bfix\b', re.IGNORECASE),
    re.compile(r'\bbroken\b', re.IGNORECASE),
    re.compile(r'\bnot\s+display\w*\b', re.IGNORECASE),
    re.compile(r'\bnot\s+render\w*\b', re.IGNORECASE),
    re.compile(r'\bnot\s+appear\w*\b', re.IGNORECASE),
    re.compile(r'\bnot\s+show\w*\b', re.IGNORECASE),
    re.compile(r'\bstill\s+broken\b', re.IGNORECASE),
    re.compile(r'\bstill\s+not\b', re.IGNORECASE),
]

# Patterns suggesting a test-only response (no implementation change)
_TEST_ONLY_PATTERNS = [
    re.compile(r'\badd\s+test\b', re.IGNORECASE),
    re.compile(r'\bwrite\s+test\b', re.IGNORECASE),
    re.compile(r'\bcreate\s+test\b', re.IGNORECASE),
    re.compile(r'\btest\s+only\b', re.IGNORECASE),
    re.compile(r'\bonly\s+test\b', re.IGNORECASE),
]


def classify_repair_intent(
    user_message: str,
    *,
    previous_changed_files: list[str] | None = None,
) -> dict:
    """Classify whether a user message expresses repair/fix intent.

    Returns:
        {
            is_repair: bool,
            repair_type: "implementation_fix" | "none",
            primary_target_files: list[str],  # files to prioritize as first update targets
            matched_pattern: str,             # first matched pattern name
        }

    When is_repair=True and previous_changed_files is known, those files are
    returned as primary_target_files so the planner prioritizes them as the
    first implementation update target rather than creating test-only plans.
    """
    for pattern in _REPAIR_PATTERNS:
        m = pattern.search(user_message)
        if m:
            return {
                "is_repair": True,
                "repair_type": "implementation_fix",
                "primary_target_files": list(previous_changed_files or []),
                "matched_pattern": m.re.pattern,
            }

    return {
        "is_repair": False,
        "repair_type": "none",
        "primary_target_files": [],
        "matched_pattern": "",
    }


def is_test_only_repair_plan(plan_items: list[dict]) -> bool:
    """Return True if all implementation-like items only modify test files.

    Used to warn/block plans that respond to a repair prompt by only adding
    tests without touching the reported implementation file.
    """
    impl_items = [
        it for it in plan_items
        if str(it.get("item_type") or "").lower() in {"implementation", "documentation"}
    ]
    if not impl_items:
        return False

    for item in impl_items:
        target_files = list(item.get("target_files") or [])
        file_changes = item.get("file_changes") or []
        all_paths = target_files + [str(fc.get("path") or "") for fc in file_changes if isinstance(fc, dict)]
        # If any item touches a non-test file, it's not test-only
        if any(_is_non_test_file(p) for p in all_paths):
            return False
    return True


def _is_non_test_file(path: str) -> bool:
    p = path.lower().replace("\\", "/")
    # Test files: paths containing test/, tests/, spec/, __tests__/, or filenames matching test_*.py etc.
    test_indicators = ("/test/", "/tests/", "/spec/", "/__tests__/", "test_", "_test.", ".spec.", ".test.")
    return not any(ind in p for ind in test_indicators)
