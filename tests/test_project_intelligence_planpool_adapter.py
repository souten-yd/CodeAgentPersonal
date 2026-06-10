"""PIR-10 CompiledPlan to authoritative Atlas PlanPool adapter tests."""

from __future__ import annotations

from agent.architecture_blueprint.contracts import BlueprintElement, BlueprintRevision
from agent.architecture_blueprint.lifecycle import planner_decision
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.project_intelligence.plan_compiler import compile_plan
from agent.project_intelligence.planpool_adapter import (
    build_plan_pool_from_compiled_plan,
    compiled_plan_to_plan_payload,
    create_authoritative_plan_pool,
)


def _revision() -> BlueprintRevision:
    return BlueprintRevision(
        blueprint_id="bp",
        revision_id="bprev-10",
        project_id="p",
        workspace_id="w",
        scope="change_set",
        source_requirement_ids=["R1", "R2"],
        selected_architecture=planner_decision("d", "target", [], "", []),
        elements=[
            BlueprintElement(
                element_id="e_a",
                canonical_ref="bp://a.py",
                element_type="file",
                name="a.py",
                requirement_ids=["R1"],
                expected_actual_refs=["file://a.py"],
                acceptance_criteria=["a.py updated"],
                verification_contract_ids=["vc:a"],
            ),
            BlueprintElement(
                element_id="e_b",
                canonical_ref="bp://b.py",
                element_type="file",
                name="b.py",
                requirement_ids=["R2"],
                depends_on_element_ids=["e_a"],
                expected_actual_refs=["file://b.py"],
                acceptance_criteria=["b.py updated"],
                verification_contract_ids=["vc:b"],
            ),
        ],
    )


def _compiled(completed: set[str] | None = None):
    return compile_plan(
        _revision(),
        project_mode="existing",
        completed_item_ids=completed,
        actual_twin_revision_id="tw-10",
        convergence_report_id="cv-10",
        context_manifest_id="cm-10",
    )


def test_compiled_plan_payload_carries_manifest_and_element_mapping() -> None:
    plan = _compiled()
    payload = compiled_plan_to_plan_payload(plan, root_goal="Ship PIR-10")

    assert payload["metadata"]["blueprint_revision_id"] == "bprev-10"
    assert payload["metadata"]["actual_twin_revision_id"] == "tw-10"
    assert payload["metadata"]["convergence_report_id"] == "cv-10"
    assert payload["metadata"]["context_manifest_id"] == "cm-10"
    assert payload["metadata"]["planning_envelope_hash"] == plan.planning_envelope_hash
    assert payload["metadata"]["element_item_map"] == {"e_a": "item:e_a", "e_b": "item:e_b"}
    assert payload["implementation_steps"][1]["depends_on"] == ["item:e_a"]
    assert payload["implementation_steps"][0]["target_files"] == ["a.py"]


def test_build_plan_pool_from_compiled_plan_preserves_completed_items_and_metadata() -> None:
    plan = _compiled(completed={"item:e_a"})
    pool = build_plan_pool_from_compiled_plan(plan, root_goal="Ship PIR-10", pool_id="pool-pir10")

    first = pool.get_item("item:e_a")
    second = pool.get_item("item:e_b")
    assert first is not None and first.status == "completed"
    assert second is not None and second.depends_on == ["item:e_a"]
    assert "item:e_a" in pool.completed_item_ids
    assert pool.metadata["blueprint_revision_id"] == "bprev-10"
    assert pool.metadata["actual_twin_revision_id"] == "tw-10"
    assert first.metadata["blueprint_element_ids"] == ["e_a"]
    assert first.metadata["planning_envelope_hash"] == plan.planning_envelope_hash


def test_create_authoritative_plan_pool_uses_storage_roundtrip(tmp_path) -> None:
    storage = AtlasPlanPoolStorage(tmp_path)
    plan = _compiled()
    pool = create_authoritative_plan_pool(
        plan,
        storage=storage,
        root_goal="Ship PIR-10",
        project_path=str(tmp_path),
        project_name="KasaneCore",
        pool_id="pool-pir10",
    )

    reloaded = storage.load_pool(pool.pool_id)
    assert reloaded.pool_id == "pool-pir10"
    assert reloaded.metadata["blueprint_revision_id"] == "bprev-10"
    assert reloaded.metadata["context_manifest_id"] == "cm-10"
    assert reloaded.get_item("item:e_b") is not None
