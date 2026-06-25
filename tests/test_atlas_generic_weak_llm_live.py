"""GA7 real 8080 weak-model checks for generic app hardening.

These tests intentionally skip when no local OpenAI-compatible server is reachable.
When :8080 is available they produce real model evidence for web-app and
business/config scenarios without applying files to the repository workspace.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import pytest

from agent.atlas_edit_primitives import file_type_edit_policy
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_post_apply_preview import preview_plan_item_post_apply
from agent.atlas_post_apply_validators import run_post_apply_validators
from agent.model_forge.weak_large_file_edit_policy import EDIT_ONLY_MAX_OUTPUT_TOKENS, weak_large_file_edit_policy


BASE_URL = os.environ.get("FORGE_LOCAL_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
MODEL_ID = os.environ.get("FORGE_LOCAL_MODEL", "").strip()


def _probe_model() -> str:
    try:
        req = urllib_request.Request(f"{BASE_URL}/v1/models", method="GET")
        with urllib_request.urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"no local model server reachable at {BASE_URL}: {exc}")
    models = data.get("data") if isinstance(data, dict) else []
    if isinstance(models, list) and models:
        model = str(models[0].get("id") or models[0].get("model") or "")
        if model:
            return MODEL_ID or model
    legacy = data.get("models") if isinstance(data, dict) else []
    if isinstance(legacy, list) and legacy:
        model = str(legacy[0].get("model") or legacy[0].get("name") or "")
        if model:
            return MODEL_ID or model
    pytest.skip(f"local model server at {BASE_URL} returned no model ids")


def _run_live_scenario(*, model_id: str, case_id: str, file_path: str, content: str, goal: str) -> dict:
    root = Path(tempfile.mkdtemp())
    ws = root / "ws"
    ca = root / "ca"
    ws.mkdir()
    ca.mkdir()
    target = ws / file_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    storage = AtlasPlanPoolStorage(ca)
    journal = AtlasJournal(ca, workspace_id="default")
    item = AtlasPlanItem(
        item_id=case_id,
        pool_id="p",
        title=case_id,
        goal=goal,
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=[file_path],
        metadata={"action_type": "update"},
    )
    pool = AtlasPlanPool(pool_id="p", root_goal="ga7", project_path=str(ws), items=[item])
    storage.save_pool(pool)

    adapter = AtlasLLMJsonAdapter(
        base_url=BASE_URL,
        model=model_id,
        timeout_seconds=120,
        max_tokens=EDIT_ONLY_MAX_OUTPUT_TOKENS,
    )
    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=adapter)
    result = service.propose_for_item(AtlasPatchProposalRequest(pool_id="p", item_id=case_id, source_type="plan_item"))
    reloaded = storage.load_pool("p")
    proposed_item = reloaded.get_item(case_id)
    preview = preview_plan_item_post_apply(item=proposed_item, workspace_root=ws, allow_existing_full_content=False)
    validators = run_post_apply_validators(preview.get("post_apply_content_by_path") or {}, preview_result=preview)
    metadata = result.proposal.metadata if result.proposal else {}
    output_mode = _output_mode(metadata)
    size = {"chars": len(content), "lines": content.count("\n") + 1}
    large_policy = weak_large_file_edit_policy(
        size_tier="standard",
        file_chars=size["chars"],
        file_lines=size["lines"],
        file_exists=True,
    )
    type_policy = file_type_edit_policy(file_path, file_lines=size["lines"], file_chars=size["chars"]).to_dict()
    full_content_accepted_under_edit_only = (
        output_mode == "full_content"
        and bool(type_policy.get("edit_only") or large_policy.get("edit_only"))
        and bool(preview.get("applied"))
    )
    return {
        "case_id": case_id,
        "model_id": model_id,
        "endpoint": BASE_URL,
        "target_file": file_path,
        "target_file_size": size,
        "large_file_edit_policy": large_policy,
        "file_type_edit_policy": type_policy,
        "output_cap": EDIT_ONLY_MAX_OUTPUT_TOKENS,
        "output_mode": output_mode,
        "proposal_status": result.proposal.status if result.proposal else result.status,
        "proposal_warnings": list(result.proposal.warnings if result.proposal else result.warnings),
        "patch_content_available": bool(metadata.get("patch_content_available")),
        "post_apply_preview": {
            "applied": bool(preview.get("applied")),
            "reasons": list(preview.get("reasons") or []),
            "applied_count": len(preview.get("applied_changes") or []),
            "blocked_count": len(preview.get("blocked_changes") or []),
        },
        "contract_violations": list(validators.get("violations") or []),
        "validator_status": list(validators.get("validators") or []),
        "safe_apply_dry_run_result": {
            "status": "previewed" if preview.get("applied") else "blocked",
            "reasons": list(preview.get("reasons") or []),
        },
        "usage": dict(adapter.last_usage or {}),
        "full_content_accepted_under_edit_only": full_content_accepted_under_edit_only,
        "unavailable_checks": [],
    }


def _output_mode(metadata: dict) -> str:
    file_changes = metadata.get("file_changes") if isinstance(metadata.get("file_changes"), list) else []
    for change in file_changes:
        if isinstance(change, dict):
            mode = str(change.get("content_mode") or "").strip()
            if mode:
                return mode
    for key, mode in (
        ("edit_primitives", "edit_primitives"),
        ("edits", "edits"),
        ("unified_diff_preview", "unified_diff"),
        ("proposed_content", "full_content"),
    ):
        value = metadata.get(key)
        if (isinstance(value, list) and value) or (isinstance(value, str) and value):
            return mode
    return "bounded_rejection"


@pytest.mark.real_model
def test_generic_weak_llm_live_safety_scenarios():
    model_id = _probe_model()
    web_content = (
        "export function currentTitle(){ return 'Old title'; }\n"
        + "".join(f"export const filler{i} = {i};\n" for i in range(150))
    )
    config_content = '{"feature":{"enabled":false,"label":"Old"},"limits":{"max":3}}\n'
    evidence = [
        _run_live_scenario(
            model_id=model_id,
            case_id="ga7_web_app",
            file_path="src/App.tsx",
            content=web_content,
            goal="Change Old title to New title in src/App.tsx only. Preserve every other export.",
        ),
        _run_live_scenario(
            model_id=model_id,
            case_id="ga7_business_config",
            file_path="config/settings.json",
            content=config_content,
            goal="In config/settings.json set /feature/enabled to true. Preserve label and limits.",
        ),
    ]

    assert all(item["usage"].get("output_tokens", 0) > 0 for item in evidence)
    assert all(item["output_mode"] in {"edits", "edit_primitives", "unified_diff", "bounded_rejection"} for item in evidence)
    assert not any(item["full_content_accepted_under_edit_only"] for item in evidence)
    assert any(item["post_apply_preview"]["applied"] for item in evidence)

    out_dir = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "ca_data")) / "model_forge" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "package": "GA7",
        "base_url": BASE_URL,
        "model_id": model_id,
        "scenarios": evidence,
    }
    (out_dir / "ga7_generic_weak_llm_live.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("GA7 evidence:", json.dumps(payload, ensure_ascii=False))
