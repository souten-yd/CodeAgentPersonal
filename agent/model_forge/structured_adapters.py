"""Structured Forge method adapters and deterministic Safe Apply compilation."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

from agent.atlas_plan_item_file_changes import validate_protected_relative_path
from agent.model_forge.method_artifacts import InMemoryMethodArtifactStore, MethodArtifactStore
from agent.model_forge.method_contracts import (
    CompiledPrompt,
    MethodRegistry,
    MethodRequest,
    MethodResult,
)
from agent.model_forge.method_taxonomy import MethodVariant


_SYSTEM_TEXT = (
    "Return only the requested JSON contract. Do not apply files, run commands, "
    "or bypass Proposal, Safe Apply, or Verification."
)


def _extract_json_object(raw_output: str) -> dict | None:
    text = str(raw_output or "").strip()
    if not text:
        return None
    fenced = re.match(r"```(?:json)?\s*([\s\S]*?)\s*```$", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _normalize_file_change(raw: object) -> tuple[dict | None, str]:
    if not isinstance(raw, dict):
        return None, "invalid_file_change"
    path = _string(raw.get("path")).strip().replace("\\", "/")
    ok, reason, _resolved = validate_protected_relative_path(path)
    if not ok:
        return None, reason or "unsafe_target_path"
    action_type = _string(
        raw.get("action_type") or raw.get("action") or raw.get("op") or raw.get("operation") or "update"
    ).lower()
    action_type = {
        "replace": "update",
        "edit": "update",
        "append": "update",
        "write": "create",
    }.get(action_type, action_type)
    if action_type not in {"create", "update"}:
        return None, "forbidden_action_type"

    change: dict[str, object] = {"path": path, "action_type": action_type}
    proposed_content = raw.get("proposed_content", raw.get("content"))
    if isinstance(proposed_content, str) and proposed_content:
        change.update(content_mode="full_content", proposed_content=proposed_content)
    elif isinstance(raw.get("edits"), list) and raw["edits"]:
        edits: list[dict[str, str]] = []
        for edit in raw["edits"]:
            if not isinstance(edit, dict):
                return None, "invalid_edit_intent"
            old_string = _string(edit.get("old_string") or edit.get("old_text"))
            new_string = _string(edit.get("new_string") or edit.get("new_text"))
            if not old_string:
                return None, "missing_edit_anchor"
            edits.append({"old_string": old_string, "new_string": new_string})
        change.update(content_mode="edits", edits=edits)
    elif _string(raw.get("old_string") or raw.get("old_text")):
        change.update(
            content_mode="edits",
            edits=[{
                "old_string": _string(raw.get("old_string") or raw.get("old_text")),
                "new_string": _string(raw.get("new_string") or raw.get("new_text")),
            }],
        )
    elif isinstance(raw.get("append_content"), str) and raw["append_content"]:
        change.update(content_mode="append", append_content=raw["append_content"])
    elif isinstance(raw.get("patch"), str) and raw["patch"]:
        change.update(content_mode="unified_diff", patch=raw["patch"])
    else:
        return None, "content_missing"
    return change, ""


def compile_safe_apply_file_changes(entries: object) -> tuple[dict | None, list[str]]:
    """Normalize model entries without applying them or granting approval readiness."""
    if not isinstance(entries, list) or not entries:
        return None, ["file_changes_missing"]
    changes: list[dict] = []
    errors: list[str] = []
    for entry in entries:
        normalized, error = _normalize_file_change(entry)
        if error:
            errors.append(error)
        elif normalized is not None:
            changes.append(normalized)
    if errors or not changes:
        return None, list(dict.fromkeys(errors or ["file_changes_missing"]))
    return {
        "format": "atlas_file_changes.v1",
        "file_changes": changes,
        "change_set": {
            "mode": "atomic",
            "apply_strategy": "preflight_all_then_apply_all",
            "partial_apply_allowed": False,
        },
        "approval_required": True,
        "safe_apply_ready": False,
    }, []


class StructuredMethodAdapter(ABC):
    variant: MethodVariant
    response_key: str

    def __init__(self, artifact_store: MethodArtifactStore | None = None) -> None:
        self.artifact_store = artifact_store or InMemoryMethodArtifactStore()

    @property
    @abstractmethod
    def response_contract(self) -> str: ...

    def prepare_prompt(self, request: MethodRequest) -> CompiledPrompt:
        payload = {
            "goal": request.goal,
            "route": request.route.value,
            "allowed_refs": request.allowed_refs,
            "forbidden_refs": request.forbidden_refs,
            "output_contract": request.output_contract,
            "verification_contract": request.verification_contract,
            "required_response": self.response_contract,
        }
        return CompiledPrompt(
            prompt_text=json.dumps(payload, ensure_ascii=False, indent=2),
            system_text=_SYSTEM_TEXT,
            metadata={"method_variant": self.variant.value},
        )

    def parse_output(self, request: MethodRequest, raw_output: str) -> MethodResult:
        raw_ref = self.artifact_store.put("raw", raw_output)
        payload = _extract_json_object(raw_output)
        if payload is None or not isinstance(payload.get(self.response_key), list):
            return MethodResult(
                request_id=request.request_id,
                method_variant=self.variant,
                status="failed",
                raw_output_ref=raw_ref,
                errors=["schema_invalid"],
            )
        parsed_ref = self.artifact_store.put("parsed", payload)
        return MethodResult(
            request_id=request.request_id,
            method_variant=self.variant,
            status="passed",
            raw_output_ref=raw_ref,
            parsed_output_ref=parsed_ref,
        )

    def compile_patch(self, request: MethodRequest, result: MethodResult) -> MethodResult:
        if not result.parsed_output_ref:
            return result
        payload = self.artifact_store.get(result.parsed_output_ref)
        entries = payload.get(self.response_key) if isinstance(payload, dict) else None
        patch, errors = compile_safe_apply_file_changes(self._entries_for_compile(entries))
        if errors or patch is None:
            return result.model_copy(update={
                "status": "blocked",
                "blocked_reasons": list(dict.fromkeys([*result.blocked_reasons, *errors])),
                "safe_apply_ready": False,
            })
        patch_ref = self.artifact_store.put("safe-apply-patch", patch)
        return result.model_copy(update={
            "patch_ref": patch_ref,
            "edit_intent_ref": result.parsed_output_ref if self.variant == MethodVariant.EDIT_INTENT_LIST else "",
            "requires_human_review": True,
            "safe_apply_ready": False,
        })

    def _entries_for_compile(self, entries: object) -> object:
        return entries

    def verify_contract(self, request: MethodRequest, result: MethodResult) -> MethodResult:
        if result.status != "passed" or not result.patch_ref:
            return result.model_copy(update={"contract_valid": False, "safe_apply_ready": False})
        try:
            patch = self.artifact_store.get(result.patch_ref)
        except KeyError:
            return result.model_copy(update={
                "status": "failed",
                "contract_valid": False,
                "safe_apply_ready": False,
                "errors": [*result.errors, "patch_artifact_missing"],
            })
        valid = isinstance(patch, dict) and bool(patch.get("file_changes")) and patch.get("safe_apply_ready") is False
        return result.model_copy(update={
            "status": "passed" if valid else "failed",
            "contract_valid": valid,
            "safe_apply_ready": False,
            "requires_human_review": True,
            "errors": result.errors if valid else [*result.errors, "patch_contract_invalid"],
        })


class StructuredPatchJsonAdapter(StructuredMethodAdapter):
    variant = MethodVariant.STRUCTURED_PATCH_JSON
    response_key = "file_changes"
    response_contract = "JSON object with a non-empty file_changes array using Atlas file change fields"


class PatchDslJsonAdapter(StructuredMethodAdapter):
    variant = MethodVariant.PATCH_DSL_JSON
    response_key = "operations"
    response_contract = "JSON object with operations; each operation has path, action, and content or edits"


class EditIntentListAdapter(StructuredMethodAdapter):
    variant = MethodVariant.EDIT_INTENT_LIST
    response_key = "intents"
    response_contract = "JSON object with intents; each intent has path and an anchored old_text/new_text edit"


def build_structured_method_registry(
    artifact_store: MethodArtifactStore | None = None,
) -> MethodRegistry:
    store = artifact_store or InMemoryMethodArtifactStore()
    registry = MethodRegistry()
    registry.register(StructuredPatchJsonAdapter(store))
    registry.register(PatchDslJsonAdapter(store))
    registry.register(EditIntentListAdapter(store))
    return registry
