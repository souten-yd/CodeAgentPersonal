"""Contract tests for (A) plan-level per-file decomposition.

Validates that a multi-file implementation item is expanded into real per-file
sub-items (the path validated 6/6 vs the 2-file atomic item's 0/4), while single-file
and non-implementation items pass through unchanged, ordering/dependencies are correct,
and test files stay as retained artifacts rather than their own units.
"""
from __future__ import annotations

from agent.atlas_plan_decomposition import (
    assign_app_verification_scope,
    decompose_multi_file_items,
    should_decompose_item,
)
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_target_contract import PlanOperation


def _item(item_id, target_files, *, item_type="implementation", depends_on=None, ops=None):
    return AtlasPlanItem(
        item_id=item_id,
        pool_id="pool_x",
        title=f"Item {item_id}",
        goal=f"goal {item_id}",
        item_type=item_type,
        target_files=list(target_files),
        depends_on=list(depends_on or []),
        operations=[PlanOperation(**o) for o in (ops or [])],
        requirement_ids=["req_1", "req_2"],
    )


def _pool(items):
    return AtlasPlanPool(pool_id="pool_x", root_goal="g", items=items)


def test_multi_file_item_expands_to_one_subitem_per_code_file():
    pool = _pool([
        _item(
            "step_4",
            ["js/game.js", "js/main.js"],
            ops=[
                {"type": "modify_file", "path": "js/game.js"},
                {"type": "modify_file", "path": "js/main.js"},
            ],
        )
    ])
    _, notes = decompose_multi_file_items(pool)

    assert len(pool.items) == 2
    assert [it.item_id for it in pool.items] == ["step_4__f0_js_game_js", "step_4__f1_js_main_js"]
    # each sub-item targets exactly one file, with file-scoped operations
    assert pool.items[0].target_files == ["js/game.js"]
    assert pool.items[1].target_files == ["js/main.js"]
    assert [op.path for op in pool.items[0].operations] == ["js/game.js"]
    assert [op.path for op in pool.items[1].operations] == ["js/main.js"]
    # requirement coverage is inherited by every unit
    assert pool.items[0].requirement_ids == ["req_1", "req_2"]
    assert notes and "step_4" in notes[0]
    # group roles drive when behavioural/visual smoke runs: only the final file of the
    # feature runs it; earlier members defer (premature smoke on a partial app is noise)
    assert pool.items[0].metadata.get("group_role") == "member"
    assert pool.items[1].metadata.get("group_role") == "final"


def test_subitems_chain_define_before_use():
    pool = _pool([_item("step_4", ["js/game.js", "js/main.js"], depends_on=["step_3"])])
    decompose_multi_file_items(pool)
    # first sub keeps the original dependency; later subs chain on the previous file
    assert pool.items[0].depends_on == ["step_3"]
    assert pool.items[1].depends_on == ["step_4__f0_js_game_js"]


def test_downstream_dependency_remapped_to_last_subitem():
    pool = _pool([
        _item("step_4", ["js/game.js", "js/main.js"]),
        _item("step_5", ["js/ui.js"], depends_on=["step_4"]),
    ])
    decompose_multi_file_items(pool)
    step5 = next(it for it in pool.items if it.item_id == "step_5")
    # step_5 must wait for ALL of step_4's files => depends on the LAST sub-item
    assert step5.depends_on == ["step_4__f1_js_main_js"]


def test_test_files_are_not_required_targets_of_any_unit():
    pool = _pool([_item("step_4", ["js/game.js", "js/main.js", "tests/test_main.js"])])
    decompose_multi_file_items(pool)
    # only the 2 CODE files become units, each STRICTLY single-target (a test ride-along
    # would make the unit a multi-target generation and re-introduce multi_file_content_missing)
    assert len(pool.items) == 2
    for it in pool.items:
        assert len(it.target_files) == 1
        assert "tests/test_main.js" not in it.target_files
    assert all(not it.item_id.endswith("test_main_js") for it in pool.items)


def test_single_file_and_non_implementation_pass_through():
    pool = _pool([
        _item("step_1", ["js/only.js"]),
        _item("step_2", ["a.js", "b.js"], item_type="verification"),
    ])
    before = [it.item_id for it in pool.items]
    _, notes = decompose_multi_file_items(pool)
    assert [it.item_id for it in pool.items] == before
    assert notes == []
    assert should_decompose_item(pool.items[0]) is False


def test_idempotent_on_already_decomposed_pool():
    pool = _pool([_item("step_4", ["js/game.js", "js/main.js"])])
    decompose_multi_file_items(pool)
    ids_after_first = [it.item_id for it in pool.items]
    decompose_multi_file_items(pool)
    assert [it.item_id for it in pool.items] == ids_after_first


def test_verification_scope_defers_whole_app_smoke_until_last_app_toucher():
    # a typical web plan: scaffold -> code -> code -> ... -> final css. Only the LAST item that
    # touches the app runtime runs the whole-app smoke; every earlier app item defers it.
    pool = _pool([
        _item("step_1", ["index.html", "css/style.css"]),
        _item("step_2", ["js/game.js"]),
        _item("step_3", ["js/main.js"]),
        _item("step_5", ["css/style.css"]),
    ])
    decompose_multi_file_items(pool)
    by_id = {it.item_id: it for it in pool.items}
    # step_1 expanded to 2 items, both deferred (later items still touch the app)
    assert by_id["step_1__f0_index_html"].metadata["verification_scope"] == "deferred_smoke"
    assert by_id["step_2"].metadata["verification_scope"] == "deferred_smoke"
    assert by_id["step_3"].metadata["verification_scope"] == "deferred_smoke"
    # the LAST item touching the app runs the integration smoke
    assert by_id["step_5"].metadata["verification_scope"] == "integration"


def test_verification_scope_marks_non_app_items_normal():
    pool = _pool([
        _item("step_1", ["lib/util.py"]),
        _item("step_2", ["index.html"]),
    ])
    assign_app_verification_scope(pool)
    by_id = {it.item_id: it for it in pool.items}
    assert by_id["step_1"].metadata["verification_scope"] == "normal"  # pure python, not the app
    assert by_id["step_2"].metadata["verification_scope"] == "integration"  # only/last app item


def test_runtime_metadata_not_carried_onto_subitems():
    item = _item("step_4", ["js/game.js", "js/main.js"])
    item.metadata = {"patch_generation": {"state": "running", "attempt": 5}, "keep": 1}
    pool = _pool([item])
    decompose_multi_file_items(pool)
    for sub in pool.items:
        assert "patch_generation" not in sub.metadata
        assert sub.metadata.get("keep") == 1
        assert sub.metadata.get("decomposed_from") == "step_4"
        assert sub.status == "queued"
