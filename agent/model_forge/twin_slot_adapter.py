"""Method adapter that deterministically compiles model slot-fill output."""
from __future__ import annotations

import json

from agent.model_forge.method_artifacts import InMemoryMethodArtifactStore, MethodArtifactStore
from agent.model_forge.method_contracts import CompiledPrompt, MethodRequest, MethodResult
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.structured_adapters import compile_safe_apply_file_changes
from agent.model_forge.twin_edit_slots import TwinEditSlot


class TwinLocalizedSlotPatchAdapter:
    variant = MethodVariant.TWIN_LOCALIZED_SLOT_PATCH

    def __init__(self, artifact_store: MethodArtifactStore | None = None) -> None:
        self.artifact_store = artifact_store or InMemoryMethodArtifactStore()

    def prepare_prompt(self, request: MethodRequest) -> CompiledPrompt:
        slot = TwinEditSlot.model_validate(request.metadata.get("twin_edit_slot"))
        return CompiledPrompt(
            system_text=(
                "Return only code for the supplied slot. Do not choose or repeat an anchor, "
                "apply files, or bypass Proposal, Safe Apply, or Verification."
            ),
            prompt_text=json.dumps({
                "goal": request.goal,
                "slot": slot.model_dump(mode="json"),
                "required_response": {"slot_content": "code only"},
            }, ensure_ascii=False, indent=2),
            metadata={"method_variant": self.variant.value, "slot_id": slot.slot_id},
        )

    def parse_output(self, request: MethodRequest, raw_output: str) -> MethodResult:
        raw_ref = self.artifact_store.put("raw", raw_output)
        text = str(raw_output or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        slot = TwinEditSlot.model_validate(request.metadata.get("twin_edit_slot"))
        if not text or len(text.splitlines()) > slot.max_new_lines:
            return MethodResult(request_id=request.request_id, method_variant=self.variant, status="failed", raw_output_ref=raw_ref, errors=["slot_content_invalid"])
        if slot.anchor_text and slot.anchor_text in text:
            return MethodResult(request_id=request.request_id, method_variant=self.variant, status="blocked", raw_output_ref=raw_ref, blocked_reasons=["model_repeated_owned_anchor"])
        parsed_ref = self.artifact_store.put("slot-fill", {"slot_content": text, "slot": slot.model_dump(mode="json")})
        return MethodResult(request_id=request.request_id, method_variant=self.variant, status="passed", raw_output_ref=raw_ref, parsed_output_ref=parsed_ref)

    def compile_patch(self, request: MethodRequest, result: MethodResult) -> MethodResult:
        if result.status != "passed" or not result.parsed_output_ref:
            return result
        payload = self.artifact_store.get(result.parsed_output_ref)
        slot = TwinEditSlot.model_validate(payload["slot"])
        if not slot.anchor_text or slot.anchor_occurrences != 1:
            return result.model_copy(update={"status": "blocked", "blocked_reasons": [*result.blocked_reasons, "slot_anchor_not_unique"]})
        content = str(payload["slot_content"])
        if slot.operation == "insert_after":
            new_text = slot.anchor_text + "\n" + content
        elif slot.operation in {"replace_symbol_body", "replace_range"}:
            new_text = content
        else:
            return result.model_copy(update={"status": "blocked", "blocked_reasons": [*result.blocked_reasons, "slot_operation_unsupported"]})
        patch, errors = compile_safe_apply_file_changes([{
            "path": slot.file, "action_type": "update", "old_text": slot.anchor_text, "new_text": new_text,
        }])
        if errors or patch is None:
            return result.model_copy(update={"status": "blocked", "blocked_reasons": [*result.blocked_reasons, *errors]})
        return result.model_copy(update={
            "patch_ref": self.artifact_store.put("safe-apply-patch", patch),
            "requires_human_review": True, "safe_apply_ready": False,
        })

    def verify_contract(self, request: MethodRequest, result: MethodResult) -> MethodResult:
        valid = result.status == "passed" and bool(result.patch_ref)
        return result.model_copy(update={
            "status": "passed" if valid else result.status,
            "contract_valid": valid, "safe_apply_ready": False, "requires_human_review": True,
        })
