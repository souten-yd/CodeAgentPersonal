from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request

from agent.atlas_auto_safe_apply_service import AtlasAutoSafeApplyService
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_safe_apply_adapter import AtlasSafeApplyAdapter
from agent.atlas_safe_apply_execution_service import AtlasSafeApplyExecutionService
from agent.atlas_self_correction_service import AtlasSelfCorrectionService
from agent.test_command_runner import TestCommandRunner


def _project_intelligence_coordinator(request: Request | Any) -> Any | None:
    return getattr(getattr(getattr(request, "app", None), "state", None), "project_intelligence", None)


def build_safe_apply_execution_service(
    *,
    request: Request | Any,
    storage: AtlasPlanPoolStorage,
    journal: AtlasJournal,
    workspace_root: Path | str,
) -> AtlasSafeApplyExecutionService:
    adapter_obj = getattr(getattr(request, "app", None), "state", None)
    adapter_obj = getattr(adapter_obj, "atlas_safe_apply_adapter", None) if adapter_obj is not None else None
    safe_apply_adapter = adapter_obj() if callable(adapter_obj) else adapter_obj
    if safe_apply_adapter is None:
        implementation_executor = getattr(getattr(request, "app", None), "state", None)
        implementation_executor = getattr(implementation_executor, "atlas_implementation_executor", None) if implementation_executor is not None else None
        if implementation_executor is None:
            implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=workspace_root)
        safe_apply_adapter = AtlasSafeApplyAdapter(implementation_executor=implementation_executor)

    impl = getattr(safe_apply_adapter, "implementation_executor", None)
    if impl is not None and hasattr(impl, "workspace_root"):
        try:
            safe_apply_adapter.implementation_executor = impl.__class__(workspace_root=workspace_root)
        except Exception:
            impl.workspace_root = workspace_root

    return AtlasSafeApplyExecutionService(
        storage=storage,
        journal=journal,
        safe_apply_adapter=safe_apply_adapter,
        workspace_root=workspace_root,
        project_intelligence=_project_intelligence_coordinator(request),
    )


def build_self_correction_service(
    *,
    request: Request | Any,
    storage: AtlasPlanPoolStorage,
    journal: AtlasJournal,
    workspace_root: Path | str,
    command_runner: Any | None = None,
) -> AtlasSelfCorrectionService | None:
    llm_json_fn = getattr(getattr(getattr(request, "app", None), "state", None), "atlas_llm_json_fn", None)
    if llm_json_fn is None:
        return None

    safe_apply_service = build_safe_apply_execution_service(
        request=request,
        storage=storage,
        journal=journal,
        workspace_root=workspace_root,
    )
    auto_safe_apply_service = AtlasAutoSafeApplyService(
        automation_gate=AtlasAutomationGateService(),
        safe_apply_service=safe_apply_service,
        journal=journal,
        storage=storage,
    )
    auto_verification_service = AtlasAutoVerificationService(
        journal=journal,
        storage=storage,
        command_runner=command_runner or TestCommandRunner(),
        project_intelligence=_project_intelligence_coordinator(request),
    )
    patch_proposal_service = AtlasPatchProposalService(
        journal=journal,
        storage=storage,
        llm_json_fn=llm_json_fn,
        project_intelligence=_project_intelligence_coordinator(request),
    )
    return AtlasSelfCorrectionService(
        storage=storage,
        journal=journal,
        patch_proposal_service=patch_proposal_service,
        auto_safe_apply_service=auto_safe_apply_service,
        auto_verification_service=auto_verification_service,
    )
