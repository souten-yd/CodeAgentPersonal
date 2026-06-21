from __future__ import annotations

import json

import pytest

from agent.model_forge.method_artifacts import InMemoryMethodArtifactStore
from agent.model_forge.method_contracts import MethodRequest
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.remaining_adapters import (
    AnchoredEditBlockAdapter,
    DeterministicTextPatchAdapter,
    RepairCompassAdapter,
    ReviewOnlyAdapter,
    UnifiedDiffAdapter,
    build_method_registry,
)
from agent.model_forge.route_taxonomy import ForgeRoute


def _request(variant: MethodVariant) -> MethodRequest:
    return MethodRequest(
        request_id="request",
        route=ForgeRoute.DIRECT_PATCH,
        method_variant=variant,
        model_id="model",
        provider_id="local",
        goal="replace old with new",
        allowed_refs=["app.py"],
    )


def _run(adapter, raw: str):
    request = _request(adapter.variant)
    parsed = adapter.parse_output(request, raw)
    compiled = adapter.compile_patch(request, parsed)
    return adapter.verify_contract(request, compiled)


def test_anchored_edit_block_compiles_to_safe_apply_edits():
    store = InMemoryMethodArtifactStore()
    adapter = AnchoredEditBlockAdapter(store)
    result = _run(adapter, """<<<FILE app.py>>>
<<<FIND>>>
print("old")
<<<REPLACE>>>
print("new")
<<<END>>>""")
    artifact = store.get(result.patch_ref)
    assert result.status == "passed" and result.contract_valid
    assert result.safe_apply_ready is False and result.requires_human_review
    assert artifact["file_changes"][0]["edits"] == [{
        "old_string": 'print("old")', "new_string": 'print("new")'
    }]


def test_anchored_edit_block_reports_missing_anchor():
    result = _run(AnchoredEditBlockAdapter(), "<<<FILE app.py>>><<<END>>>")
    assert result.status == "failed"
    assert "anchor_not_found" in result.errors


def test_unified_diff_compiles_each_file_without_applying():
    store = InMemoryMethodArtifactStore()
    adapter = UnifiedDiffAdapter(store)
    raw = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-old
+new
diff --git a/test_app.py b/test_app.py
--- a/test_app.py
+++ b/test_app.py
@@ -1 +1 @@
-assert old
+assert new
"""
    result = _run(adapter, raw)
    artifact = store.get(result.patch_ref)
    assert result.contract_valid is True
    assert [change["path"] for change in artifact["file_changes"]] == ["app.py", "test_app.py"]
    assert all(change["content_mode"] == "unified_diff" for change in artifact["file_changes"])


def test_unified_diff_rejects_delete():
    raw = """diff --git a/app.py b/app.py
--- a/app.py
+++ /dev/null
@@ -1 +0,0 @@
-old
"""
    result = _run(UnifiedDiffAdapter(), raw)
    assert result.status == "failed"
    assert result.patch_ref == ""


def test_deterministic_text_patch_compiles_replacements():
    store = InMemoryMethodArtifactStore()
    adapter = DeterministicTextPatchAdapter(store)
    result = _run(adapter, json.dumps({
        "replacements": [{"path": "app.py", "old_text": "old", "new_text": "new"}]
    }))
    artifact = store.get(result.patch_ref)
    assert artifact["file_changes"][0]["content_mode"] == "edits"
    assert result.safe_apply_ready is False


def test_review_only_never_produces_patch():
    result = _run(ReviewOnlyAdapter(), "P1: app.py lacks an input validation guard.")
    assert result.status == "passed" and result.contract_valid
    assert result.patch_ref == ""
    assert result.safe_apply_ready is False
    assert result.requires_human_review is True


def test_repair_compass_records_steps_without_patch():
    store = InMemoryMethodArtifactStore()
    adapter = RepairCompassAdapter(store)
    result = _run(adapter, json.dumps({
        "steps": ["Reproduce the failure", "Add a focused regression test"],
        "blocked_reasons": ["runtime_evidence_required"],
    }))
    assert result.status == "passed" and result.contract_valid
    assert result.patch_ref == ""
    assert result.blocked_reasons == ["runtime_evidence_required"]
    assert store.get(result.parsed_output_ref)["steps"][0] == "Reproduce the failure"


@pytest.mark.parametrize(
    "variant",
    [
        MethodVariant.STRUCTURED_PATCH_JSON,
        MethodVariant.PATCH_DSL_JSON,
        MethodVariant.EDIT_INTENT_LIST,
        MethodVariant.ANCHORED_EDIT_BLOCK,
        MethodVariant.UNIFIED_DIFF,
        MethodVariant.DETERMINISTIC_TEXT_PATCH,
        MethodVariant.REVIEW_ONLY,
        MethodVariant.REPAIR_COMPASS_STEPS,
    ],
)
def test_full_registry_contains_implemented_adapters(variant):
    assert build_method_registry().supports(variant)
