from __future__ import annotations

from pathlib import Path

from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.atlas_placeholder_detector import is_placeholder_only_content
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool

_PLACEHOLDER = "def draw():\n    pass  # TODO: placeholder\n"
_REAL = "def add(a, b):\n    total = a + b\n    return total\n\n\ndef mul(a, b):\n    return a * b\n"


def _item(content: str, rel: str = "src/x.py") -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id="i1", pool_id="p1", title="Item", goal="Do", item_type="implementation",
        status="ready", risk_level="low", target_files=[rel],
        metadata={"action_type": "create", "proposed_content": content},
    )


def _pool(item: AtlasPlanItem, enforcement: str | None) -> AtlasPlanPool:
    meta = {"automation_features": {"quality_gate_enforcement": enforcement}} if enforcement else {}
    return AtlasPlanPool(pool_id="p1", root_goal="g", items=[item], metadata=meta)


def test_is_placeholder_only_content_helper():
    assert is_placeholder_only_content(_PLACEHOLDER, file_path="src/x.py") is True
    assert is_placeholder_only_content(_REAL, file_path="src/x.py") is False


def test_block_mode_rejects_placeholder_only_before_write(tmp_path: Path):
    item = _item(_PLACEHOLDER)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=_pool(item, "block"))
    assert out["status"] == "blocked"
    assert "placeholder_only_content" in out["reasons"]
    assert not (tmp_path / "src" / "x.py").exists()  # nothing written


def test_block_mode_allows_real_content(tmp_path: Path):
    item = _item(_REAL)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=_pool(item, "block"))
    assert out["status"] == "applied"
    assert (tmp_path / "src" / "x.py").read_text(encoding="utf-8") == _REAL


def test_warn_mode_does_not_block_placeholder(tmp_path: Path):
    item = _item(_PLACEHOLDER)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=_pool(item, "warn"))
    assert out["status"] == "applied"  # legacy behaviour preserved when not enforcing


def test_absent_features_default_does_not_block(tmp_path: Path):
    item = _item(_PLACEHOLDER)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=_pool(item, None))
    assert out["status"] == "applied"  # backward compatible (no automation_features)
