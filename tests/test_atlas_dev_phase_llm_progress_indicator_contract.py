"""The theme-colored LLM-progress indicator must also drive the post-approval dev phase.

During plan generation, `pollPlanPoolUntilReady` dispatches `atlas:llm-progress` so the
`#atlas-llm-progress-line` indicator (theme color + animation + token counter) renders. The
post-approval software development phase must reuse the SAME indicator:
  - patch generation: surface live tokens from the existing patchgen-status watcher;
  - apply/verify: keep the indicator's phase current even though no tokens stream there.
These contract checks pin those two dispatches so the always-visible dev-phase indicator
does not silently regress.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = (ROOT / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")
PANEL = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_patch_generation_watcher_dispatches_llm_progress_with_tokens():
    # The generatePatchProposal status watcher already polls getPatchGenStatus; it must also feed
    # the shared indicator with phase + tokens (mirroring the plan-generation dispatch).
    body = _slice(API, "async generatePatchProposal(", "decidePatchProposal(")
    assert "getPatchGenStatus(" in body
    assert "atlas:llm-progress" in body
    assert "tokens_generated" in body
    assert "seconds_since_progress" in body


def test_generate_recovers_server_result_on_client_disconnect():
    # A long synchronous patch generation can drop the mobile/LAN connection (network_error) even
    # though the server finishes and persists the patchgen job. The client must recover the
    # server-side outcome by polling status instead of surfacing a misleading network_error that
    # makes the item skip as missing_patch_or_content.
    body = _slice(API, "async generatePatchProposal(", "async recoverPatchGenAfterDisconnect(")
    assert "network_error" in body
    assert "self.recoverPatchGenAfterDisconnect(" in body
    recover = _slice(API, "async recoverPatchGenAfterDisconnect(", "decidePatchProposal(")
    assert "getPatchGenStatus(" in recover
    assert "'done'" in recover and "patch_content_available" in recover
    assert "atlas:llm-progress" in recover  # indicator stays live during recovery


def test_apply_verify_peek_loop_keeps_indicator_phase_current():
    # The Stage 4 (apply + verify) autopilot peek loop must keep the indicator phase current so it
    # stays visible across the whole development phase, not just during generation.
    body = _slice(PANEL, "async function approveAndRunPipeline(", "function escapeText(")
    assert "atlas:llm-progress" in body
    assert "verifying" in body and "applying" in body


def test_build_flow_interleaves_generate_and_apply_per_item():
    # ROOT-CAUSE FIX for safe_apply_not_applied: generating ALL patches then applying them as a
    # batch caused edit drift. The build loop must generate -> approve -> apply+verify ONE item at a
    # time (single-item autopilot) so each patch is generated against the CURRENT file state.
    body = _slice(PANEL, "async function approveAndRunPipeline(", "function escapeText(")
    # The apply call must target a SINGLE item (interleaved), not the whole appliable batch.
    assert "item_ids: [itemId]" in body
    # ...and it must sit inside the per-item generation loop (after a successful generatePatchProposal).
    gen_idx = body.index("generatePatchProposal(")
    apply_idx = body.index("item_ids: [itemId]")
    assert apply_idx > gen_idx
    # The old generate-all-then-batch-apply call must be gone.
    assert "item_ids: appliableIds" not in body


def test_self_correction_recovers_safe_apply_drift_backend():
    # Defense in depth: the autopilot regenerates a drifted patch against current content and
    # re-applies it (safe_apply_drift_recovered) instead of failing with safe_apply_not_applied.
    svc = (Path(__file__).resolve().parents[1] / "agent" / "atlas_multi_item_autopilot_service.py").read_text(encoding="utf-8")
    assert "_recover_safe_apply_drift" in svc
    assert "safe_apply_drift_recovered" in svc
    assert "edit_not_applicable" in svc
    # Edits-only patches (how the model expresses existing-file modifications) must count as
    # applicable content in the eligibility check, else they skip as missing_patch_or_content.
    elig_start = svc.index("def _check_eligibility(")
    elig = svc[elig_start:svc.index("\n    def ", elig_start)]
    assert "has_edits" in elig and 'reason": "missing_patch_or_content' in elig


def test_indicator_is_cleared_when_dev_phase_finishes():
    # The shared indicator must be torn down when the run ends (setBusy(false) -> clearLlmProgressLine).
    assert "clearLlmProgressLine()" in PANEL
    setbusy = _slice(PANEL, "function setBusy(", "function setTranscribingStatus(")
    assert "clearLlmProgressLine()" in setbusy
