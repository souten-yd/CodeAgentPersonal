from pathlib import Path

import pytest

from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


ROOT = Path(__file__).resolve().parents[1]
STORAGE_PATH = ROOT / "agent" / "atlas_plan_pool_storage.py"


def make_storage(tmp_path: Path) -> AtlasPlanPoolStorage:
    return AtlasPlanPoolStorage(tmp_path)


def make_pool(pool_id: str = "pool_1") -> AtlasPlanPool:
    return AtlasPlanPool(pool_id=pool_id, root_goal="Goal")


def make_item(item_id: str = "item_1", pool_id: str = "pool_1", status: str = "queued") -> AtlasPlanItem:
    return AtlasPlanItem(item_id=item_id, pool_id=pool_id, title="Item", goal="Do item", status=status)


def save_pool_with_item(tmp_path: Path, status: str = "queued") -> AtlasPlanPoolStorage:
    storage = make_storage(tmp_path)
    storage.save_pool(make_pool())
    storage.append_item("pool_1", make_item(status=status))
    return storage


def test_save_and_load_pool(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    pool = make_pool()

    path = storage.save_pool(pool)

    assert storage.exists("pool_1") is True
    loaded = storage.load_pool("pool_1")
    assert loaded.pool_id == "pool_1"
    assert loaded.root_goal == "Goal"
    assert loaded.status == pool.status
    assert path.exists()


def test_save_creates_expected_path_under_ca_data_atlas_plan_pools(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)

    assert storage.pool_path("pool_1") == tmp_path / "atlas" / "plan_pools" / "pool_1.json"


def test_list_pool_ids(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    storage.save_pool(make_pool("pool_2"))
    storage.save_pool(make_pool("pool_1"))

    assert storage.list_pool_ids() == ["pool_1", "pool_2"]


def test_append_item(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    storage.save_pool(make_pool())

    updated = storage.append_item("pool_1", make_item())
    loaded = storage.load_pool("pool_1")

    assert len(updated.items) == 1
    assert len(loaded.items) == 1
    assert loaded.item_ids() == ["item_1"]


def test_append_item_rejects_wrong_pool_id(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    storage.save_pool(make_pool())

    with pytest.raises(ValueError):
        storage.append_item("pool_1", make_item(pool_id="pool_2"))


def test_append_item_rejects_duplicate_item_id(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    storage.save_pool(make_pool())
    storage.append_item("pool_1", make_item())

    with pytest.raises(ValueError):
        storage.append_item("pool_1", make_item())


def test_update_item(tmp_path: Path) -> None:
    storage = save_pool_with_item(tmp_path)

    storage.update_item("pool_1", "item_1", status="ready")
    loaded = storage.load_pool("pool_1")
    item = loaded.get_item("item_1")

    assert item is not None
    assert item.status == "ready"
    assert item.updated_at
    assert loaded.updated_at


def test_update_item_rejects_missing_item(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    storage.save_pool(make_pool())

    with pytest.raises(KeyError):
        storage.update_item("pool_1", "missing", status="ready")


def test_mark_item_completed_syncs_status_lists(tmp_path: Path) -> None:
    storage = save_pool_with_item(tmp_path, status="ready")
    pool = storage.load_pool("pool_1")
    pool.failed_item_ids = ["item_1"]
    pool.blocked_item_ids = ["item_1"]
    pool.skipped_item_ids = ["item_1"]
    pool.current_item_id = "item_1"
    storage.save_pool(pool)

    updated = storage.mark_item_completed("pool_1", "item_1")
    item = updated.get_item("item_1")

    assert item is not None
    assert item.status == "completed"
    assert "item_1" in updated.completed_item_ids
    assert "item_1" not in updated.failed_item_ids
    assert "item_1" not in updated.blocked_item_ids
    assert "item_1" not in updated.skipped_item_ids
    assert updated.current_item_id == ""


def test_mark_item_failed_records_error_and_syncs_lists(tmp_path: Path) -> None:
    storage = save_pool_with_item(tmp_path, status="ready")

    updated = storage.mark_item_failed("pool_1", "item_1", error="boom")
    item = updated.get_item("item_1")

    assert item is not None
    assert item.status == "failed"
    assert "item_1" in updated.failed_item_ids
    assert "item_1" not in updated.completed_item_ids
    assert "item_1" not in updated.blocked_item_ids
    assert "item_1" not in updated.skipped_item_ids
    assert "boom" in item.errors


def test_mark_item_blocked_records_reason_and_syncs_lists(tmp_path: Path) -> None:
    storage = save_pool_with_item(tmp_path, status="ready")

    updated = storage.mark_item_blocked("pool_1", "item_1", reason="needs approval")
    item = updated.get_item("item_1")

    assert item is not None
    assert item.status == "blocked"
    assert "item_1" in updated.blocked_item_ids
    assert "item_1" not in updated.completed_item_ids
    assert "item_1" not in updated.failed_item_ids
    assert "item_1" not in updated.skipped_item_ids
    assert "needs approval" in item.warnings


@pytest.mark.parametrize("pool_id", ["../x", "a/b", "a\\b"])
def test_pool_id_path_traversal_rejected(tmp_path: Path, pool_id: str) -> None:
    storage = make_storage(tmp_path)

    with pytest.raises(ValueError):
        storage.pool_path(pool_id)
    with pytest.raises(ValueError):
        storage.save_pool(make_pool(pool_id))
    with pytest.raises(ValueError):
        storage.load_pool(pool_id)


def test_item_id_path_traversal_rejected(tmp_path: Path) -> None:
    storage = save_pool_with_item(tmp_path)

    with pytest.raises(ValueError):
        storage.update_item("pool_1", "../x", status="ready")
    with pytest.raises(ValueError):
        storage.mark_item_completed("pool_1", "../x")


def test_no_runtime_or_api_side_effect_tokens_in_storage() -> None:
    text = STORAGE_PATH.read_text(encoding="utf-8")

    for token in (
        "FastAPI",
        "@app.",
        "subprocess",
        "ImplementationExecutor(",
        "safe" + "_apply",
        "run" + "_command",
        "delete" + "_file",
    ):
        assert token not in text
