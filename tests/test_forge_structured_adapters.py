from __future__ import annotations

import json

import pytest

from agent.model_forge.method_artifacts import InMemoryMethodArtifactStore
from agent.model_forge.method_contracts import MethodRequest
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.structured_adapters import (
    EditIntentListAdapter,
    PatchDslJsonAdapter,
    StructuredPatchJsonAdapter,
    build_structured_method_registry,
)


def _request(variant: MethodVariant) -> MethodRequest:
    return MethodRequest(
        request_id="request",
        route=ForgeRoute.PATCH_DSL,
        method_variant=variant,
        model_id="model",
        provider_id="local",
        goal="update the greeting",
        allowed_refs=["app.py"],
    )


@pytest.mark.parametrize(
    ("adapter_type", "variant"),
    [
        (StructuredPatchJsonAdapter, MethodVariant.STRUCTURED_PATCH_JSON),
        (PatchDslJsonAdapter, MethodVariant.PATCH_DSL_JSON),
        (EditIntentListAdapter, MethodVariant.EDIT_INTENT_LIST),
    ],
)
def test_structured_adapters_prepare_bounded_prompts(adapter_type, variant):
    prompt = adapter_type().prepare_prompt(_request(variant))
    assert "update the greeting" in prompt.prompt_text
    assert "app.py" in prompt.prompt_text
    assert "Safe Apply" in prompt.system_text
    assert prompt.metadata["method_variant"] == variant.value


def test_structured_patch_json_compiles_to_non_ready_safe_apply_artifact():
    store = InMemoryMethodArtifactStore()
    adapter = StructuredPatchJsonAdapter(store)
    request = _request(adapter.variant)
    raw = "```json\n" + json.dumps({
        "file_changes": [{
            "path": "app.py",
            "action_type": "update",
            "edits": [{"old_string": "hello", "new_string": "hello world"}],
        }]
    }) + "\n```"

    parsed = adapter.parse_output(request, raw)
    compiled = adapter.compile_patch(request, parsed)
    verified = adapter.verify_contract(request, compiled)
    artifact = store.get(verified.patch_ref)

    assert verified.status == "passed"
    assert verified.contract_valid is True
    assert verified.safe_apply_ready is False
    assert verified.requires_human_review is True
    assert artifact["format"] == "atlas_file_changes.v1"
    assert artifact["approval_required"] is True
    assert artifact["file_changes"][0]["content_mode"] == "edits"


def test_patch_dsl_compiles_write_operation():
    store = InMemoryMethodArtifactStore()
    adapter = PatchDslJsonAdapter(store)
    request = _request(adapter.variant)
    parsed = adapter.parse_output(request, json.dumps({
        "operations": [{"path": "new.py", "action": "create", "content": "value = 1\n"}]
    }))
    verified = adapter.verify_contract(request, adapter.compile_patch(request, parsed))
    artifact = store.get(verified.patch_ref)
    assert artifact["file_changes"] == [{
        "path": "new.py",
        "action_type": "create",
        "content_mode": "full_content",
        "proposed_content": "value = 1\n",
    }]


def test_patch_dsl_maps_replace_operation_to_anchored_update():
    store = InMemoryMethodArtifactStore()
    adapter = PatchDslJsonAdapter(store)
    request = _request(adapter.variant)
    parsed = adapter.parse_output(request, json.dumps({
        "operations": [{
            "path": "app.py",
            "op": "replace",
            "old_text": "before",
            "new_text": "after",
        }]
    }))
    verified = adapter.verify_contract(request, adapter.compile_patch(request, parsed))
    change = store.get(verified.patch_ref)["file_changes"][0]
    assert change["action_type"] == "update"
    assert change["content_mode"] == "edits"


def test_edit_intent_compiles_anchor_to_atlas_edits():
    store = InMemoryMethodArtifactStore()
    adapter = EditIntentListAdapter(store)
    request = _request(adapter.variant)
    parsed = adapter.parse_output(request, json.dumps({
        "intents": [{"path": "app.py", "old_text": "before", "new_text": "after"}]
    }))
    verified = adapter.verify_contract(request, adapter.compile_patch(request, parsed))
    artifact = store.get(verified.patch_ref)
    assert verified.edit_intent_ref == parsed.parsed_output_ref
    assert artifact["file_changes"][0]["edits"] == [
        {"old_string": "before", "new_string": "after"}
    ]


def test_invalid_json_is_failed_not_unavailable_or_passed():
    adapter = StructuredPatchJsonAdapter()
    result = adapter.parse_output(_request(adapter.variant), "not json")
    assert result.status == "failed"
    assert result.errors == ["schema_invalid"]
    assert result.contract_valid is False


@pytest.mark.parametrize("path", ["../secret.txt", ".git/config", "C:/Windows/system.ini"])
def test_deterministic_compiler_blocks_unsafe_paths(path):
    adapter = EditIntentListAdapter()
    request = _request(adapter.variant)
    parsed = adapter.parse_output(request, json.dumps({
        "intents": [{"path": path, "old_text": "before", "new_text": "after"}]
    }))
    compiled = adapter.compile_patch(request, parsed)
    assert compiled.status == "blocked"
    assert compiled.safe_apply_ready is False
    assert compiled.blocked_reasons


def test_registry_contains_all_structured_adapters_with_shared_store():
    store = InMemoryMethodArtifactStore()
    registry = build_structured_method_registry(store)
    for variant in (
        MethodVariant.STRUCTURED_PATCH_JSON,
        MethodVariant.PATCH_DSL_JSON,
        MethodVariant.EDIT_INTENT_LIST,
    ):
        assert registry.supports(variant)
        assert registry.get(variant).artifact_store is store
