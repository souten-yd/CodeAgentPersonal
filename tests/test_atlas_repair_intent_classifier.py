from __future__ import annotations

from agent.atlas_repair_intent_classifier import classify_repair_intent, is_test_only_repair_plan


# ── classify_repair_intent ────────────────────────────────────────────────────

def test_not_changing_detected_as_repair():
    r = classify_repair_intent("The color is not changing and movement is not linear")
    assert r['is_repair'] is True
    assert r['repair_type'] == 'implementation_fix'


def test_doesnt_work_detected_as_repair():
    r = classify_repair_intent("the animation doesn't work")
    assert r['is_repair'] is True


def test_fix_keyword_detected_as_repair():
    r = classify_repair_intent("please fix the bug in index.html")
    assert r['is_repair'] is True


def test_japanese_repair_keywords():
    assert classify_repair_intent("直ってない")['is_repair'] is True
    assert classify_repair_intent("変わってない")['is_repair'] is True
    assert classify_repair_intent("動いていない")['is_repair'] is True
    assert classify_repair_intent("失敗")['is_repair'] is True


def test_non_repair_message_not_classified():
    r = classify_repair_intent("add a new color animation")
    assert r['is_repair'] is False
    assert r['repair_type'] == 'none'
    assert r['primary_target_files'] == []


def test_repair_targets_previous_changed_files():
    r = classify_repair_intent(
        "color is not changing",
        previous_changed_files=["index.html", "js/main.js"],
    )
    assert r['is_repair'] is True
    assert r['primary_target_files'] == ["index.html", "js/main.js"]


def test_repair_with_no_previous_files_returns_empty_targets():
    r = classify_repair_intent("not working", previous_changed_files=None)
    assert r['is_repair'] is True
    assert r['primary_target_files'] == []


def test_repair_targets_index_html_for_color_change_complaint():
    r = classify_repair_intent(
        "color is not changing and movement is not linear",
        previous_changed_files=["index.html"],
    )
    assert r['is_repair'] is True
    assert "index.html" in r['primary_target_files']


# ── is_test_only_repair_plan ──────────────────────────────────────────────────

def test_test_only_plan_detected():
    plan = [
        {"item_type": "implementation", "target_files": ["tests/test_animation.py"], "file_changes": []},
    ]
    assert is_test_only_repair_plan(plan) is True


def test_plan_with_implementation_file_not_test_only():
    plan = [
        {"item_type": "implementation", "target_files": ["index.html"], "file_changes": []},
        {"item_type": "implementation", "target_files": ["tests/test_animation.py"], "file_changes": []},
    ]
    assert is_test_only_repair_plan(plan) is False


def test_mixed_plan_with_non_test_target_not_test_only():
    plan = [
        {
            "item_type": "implementation",
            "target_files": [],
            "file_changes": [{"path": "js/renderer.js"}],
        },
    ]
    assert is_test_only_repair_plan(plan) is False


def test_empty_plan_items_not_test_only():
    assert is_test_only_repair_plan([]) is False


def test_non_implementation_items_ignored():
    plan = [
        {"item_type": "research", "target_files": ["anything.py"], "file_changes": []},
        {"item_type": "verification", "target_files": ["tests/check.py"], "file_changes": []},
    ]
    # Only research + verification items — no implementation items → not test-only (no impl items)
    assert is_test_only_repair_plan(plan) is False


def test_clarification_step_not_emitted_as_patch_item():
    """A clarification item should not be classified as an implementation patch."""
    plan = [
        {"item_type": "clarification", "target_files": [], "file_changes": []},
    ]
    # clarification is not implementation → not test-only (no impl items)
    assert is_test_only_repair_plan(plan) is False
