"""Anchored, diff, deterministic, review, and repair Method adapters."""
from __future__ import annotations

import json
import re

from agent.model_forge.method_artifacts import InMemoryMethodArtifactStore, MethodArtifactStore
from agent.model_forge.method_contracts import CompiledPrompt, MethodRegistry, MethodRequest, MethodResult
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.structured_adapters import (
    StructuredMethodAdapter,
    _extract_json_object,
    build_structured_method_registry,
)


_NO_APPLY_SYSTEM = (
    "Produce analysis evidence only. Do not apply files, run commands, or bypass "
    "Proposal, Safe Apply, or Verification."
)


class AnchoredEditBlockAdapter(StructuredMethodAdapter):
    variant = MethodVariant.ANCHORED_EDIT_BLOCK
    response_key = "edits"
    response_contract = (
        "One or more blocks exactly shaped as <<<FILE relative/path>>> then <<<FIND>>> "
        "unique existing text, <<<REPLACE>>> replacement text, and <<<END>>>"
    )

    _BLOCK = re.compile(
        r"<<<FILE\s+([^>\r\n]+)>>>\s*"
        r"<<<FIND>>>\s*([\s\S]*?)\s*"
        r"<<<REPLACE>>>\s*([\s\S]*?)\s*"
        r"<<<END>>>",
    )

    def parse_output(self, request: MethodRequest, raw_output: str) -> MethodResult:
        raw_ref = self.artifact_store.put("raw", raw_output)
        edits = [
            {"path": path.strip(), "old_text": old_text, "new_text": new_text}
            for path, old_text, new_text in self._BLOCK.findall(str(raw_output or ""))
        ]
        if not edits or any(not edit["old_text"] for edit in edits):
            return MethodResult(
                request_id=request.request_id,
                method_variant=self.variant,
                status="failed",
                raw_output_ref=raw_ref,
                errors=["anchor_not_found"],
            )
        parsed_ref = self.artifact_store.put("parsed", {"edits": edits})
        return MethodResult(
            request_id=request.request_id,
            method_variant=self.variant,
            status="passed",
            raw_output_ref=raw_ref,
            parsed_output_ref=parsed_ref,
        )


class UnifiedDiffAdapter(StructuredMethodAdapter):
    variant = MethodVariant.UNIFIED_DIFF
    response_key = "file_changes"
    response_contract = "A unified diff with relative repository paths and at least one hunk"

    def parse_output(self, request: MethodRequest, raw_output: str) -> MethodResult:
        raw_ref = self.artifact_store.put("raw", raw_output)
        text = str(raw_output or "").strip()
        fenced = re.match(r"```(?:diff)?\s*([\s\S]*?)\s*```$", text, flags=re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        changes = self._split_diff(text)
        if not changes:
            return MethodResult(
                request_id=request.request_id,
                method_variant=self.variant,
                status="failed",
                raw_output_ref=raw_ref,
                errors=["schema_invalid"],
            )
        parsed_ref = self.artifact_store.put("parsed", {"file_changes": changes})
        return MethodResult(
            request_id=request.request_id,
            method_variant=self.variant,
            status="passed",
            raw_output_ref=raw_ref,
            parsed_output_ref=parsed_ref,
        )

    @staticmethod
    def _split_diff(text: str) -> list[dict[str, str]]:
        if "@@" not in text:
            return []
        starts = [match.start() for match in re.finditer(r"(?m)^diff --git ", text)]
        chunks = [
            text[start:(starts[index + 1] if index + 1 < len(starts) else len(text))].strip()
            for index, start in enumerate(starts)
        ] if starts else [text]
        changes: list[dict[str, str]] = []
        for chunk in chunks:
            target = re.search(r"(?m)^\+\+\+\s+(?:b/)?([^\t\r\n]+)", chunk)
            if not target:
                return []
            path = target.group(1).strip()
            if path == "/dev/null":
                return []
            changes.append({"path": path, "action_type": "update", "patch": chunk + "\n"})
        return changes


class DeterministicTextPatchAdapter(StructuredMethodAdapter):
    variant = MethodVariant.DETERMINISTIC_TEXT_PATCH
    response_key = "replacements"
    response_contract = (
        "JSON object with replacements; each replacement has path, old_text, and new_text"
    )


class ReviewOnlyAdapter:
    variant = MethodVariant.REVIEW_ONLY

    def __init__(self, artifact_store: MethodArtifactStore | None = None) -> None:
        self.artifact_store = artifact_store or InMemoryMethodArtifactStore()

    def prepare_prompt(self, request: MethodRequest) -> CompiledPrompt:
        return CompiledPrompt(
            prompt_text=json.dumps({
                "goal": request.goal,
                "allowed_refs": request.allowed_refs,
                "verification_contract": request.verification_contract,
                "required_response": "Concise review findings with severity and evidence refs; no patch",
            }, ensure_ascii=False, indent=2),
            system_text=_NO_APPLY_SYSTEM,
            metadata={"method_variant": self.variant.value},
        )

    def parse_output(self, request: MethodRequest, raw_output: str) -> MethodResult:
        text = str(raw_output or "").strip()
        raw_ref = self.artifact_store.put("review", text)
        return MethodResult(
            request_id=request.request_id,
            method_variant=self.variant,
            status="passed" if text else "failed",
            raw_output_ref=raw_ref,
            parsed_output_ref=raw_ref if text else "",
            errors=[] if text else ["empty_output"],
            requires_human_review=True,
        )

    def compile_patch(self, request: MethodRequest, result: MethodResult) -> MethodResult:
        return result.model_copy(update={
            "patch_ref": "",
            "safe_apply_ready": False,
            "requires_human_review": True,
        })

    def verify_contract(self, request: MethodRequest, result: MethodResult) -> MethodResult:
        valid = result.status == "passed" and bool(result.parsed_output_ref) and not result.patch_ref
        return result.model_copy(update={
            "status": "passed" if valid else "failed",
            "contract_valid": valid,
            "safe_apply_ready": False,
            "requires_human_review": True,
        })


class RepairCompassAdapter(ReviewOnlyAdapter):
    variant = MethodVariant.REPAIR_COMPASS_STEPS

    def prepare_prompt(self, request: MethodRequest) -> CompiledPrompt:
        return CompiledPrompt(
            prompt_text=json.dumps({
                "goal": request.goal,
                "allowed_refs": request.allowed_refs,
                "verification_contract": request.verification_contract,
                "required_response": "JSON object with non-empty steps and optional blocked_reasons",
            }, ensure_ascii=False, indent=2),
            system_text=_NO_APPLY_SYSTEM,
            metadata={"method_variant": self.variant.value},
        )

    def parse_output(self, request: MethodRequest, raw_output: str) -> MethodResult:
        raw_ref = self.artifact_store.put("raw", raw_output)
        payload = _extract_json_object(raw_output)
        steps = payload.get("steps") if isinstance(payload, dict) else None
        if not isinstance(steps, list) or not steps or not all(isinstance(step, str) and step.strip() for step in steps):
            return MethodResult(
                request_id=request.request_id,
                method_variant=self.variant,
                status="failed",
                raw_output_ref=raw_ref,
                errors=["schema_invalid"],
                requires_human_review=True,
            )
        parsed_ref = self.artifact_store.put("repair-compass", payload)
        return MethodResult(
            request_id=request.request_id,
            method_variant=self.variant,
            status="passed",
            raw_output_ref=raw_ref,
            parsed_output_ref=parsed_ref,
            blocked_reasons=[str(value) for value in payload.get("blocked_reasons", [])],
            requires_human_review=True,
        )


def build_method_registry(artifact_store: MethodArtifactStore | None = None) -> MethodRegistry:
    store = artifact_store or InMemoryMethodArtifactStore()
    registry = build_structured_method_registry(store)
    registry.register(AnchoredEditBlockAdapter(store))
    registry.register(UnifiedDiffAdapter(store))
    registry.register(DeterministicTextPatchAdapter(store))
    registry.register(ReviewOnlyAdapter(store))
    registry.register(RepairCompassAdapter(store))
    return registry
