(function () {
  const root = (typeof window !== 'undefined' ? window : globalThis);
  const API_BASE = root.API || '';

  async function parseResponse(response) {
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = payload && typeof payload === 'object' ? payload.detail : payload;
      const code = response.status === 404 && String(detail || '').toLowerCase().includes('pipeline state not found')
        ? 'pipeline_state_not_found'
        : (payload && typeof payload === 'object' ? payload.code : '');
      return {
        ok: false,
        status: response.status,
        code,
        error: true,
        message: detail || response.statusText || 'Atlas request failed',
        detail: payload,
      };
    }
    return { ok: true, status: response.status, data: payload };
  }

  async function atlasFetch(path, options) {
    const response = await fetch(API_BASE + path, {
      headers: { 'Content-Type': 'application/json', ...(options && options.headers ? options.headers : {}) },
      ...options,
    });
    return parseResponse(response);
  }

  function query(params) {
    const search = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value) !== '') search.set(key, String(value));
    });
    const text = search.toString();
    return text ? `?${text}` : '';
  }

  const AtlasPipelineAPI = {
    createPlanPool(payload) {
      return atlasFetch('/api/atlas/plan-pools', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getPlanPool(poolId) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}`);
    },
    getPlanPoolMarkdown(poolId, workspaceId) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/markdown${query({ workspace_id: workspaceId })}`);
    },
    startPipelineDryRun(payload) {
      return atlasFetch('/api/atlas/pipeline/dry-run', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getPipelineStatus(poolId, runId, workspaceId) {
      return atlasFetch(`/api/atlas/pipeline/status/${encodeURIComponent(runId)}${query({ pool_id: poolId, workspace_id: workspaceId })}`);
    },
    getPipelineEvents(poolId, runId, workspaceId) {
      return atlasFetch(`/api/atlas/pipeline/events/${encodeURIComponent(poolId)}/${encodeURIComponent(runId)}${query({ workspace_id: workspaceId })}`);
    },
    getRecoveryLatest(workspaceId) {
      return atlasFetch(`/api/atlas/recovery/latest${query({ workspace_id: workspaceId })}`);
    },
    getRecoveryPool(poolId, workspaceId) {
      return atlasFetch(`/api/atlas/recovery/pools/${encodeURIComponent(poolId)}${query({ workspace_id: workspaceId })}`);
    },
    getContinuationLatest(workspaceId) {
      return atlasFetch(`/api/atlas/continuation/latest${query({ workspace_id: workspaceId })}`);
    },
    getContinuationPool(poolId, runId, workspaceId) {
      return atlasFetch(`/api/atlas/continuation/pools/${encodeURIComponent(poolId)}${query({ run_id: runId, workspace_id: workspaceId })}`);
    },
    getApprovals(poolId, workspaceId) {
      return atlasFetch(`/api/atlas/approvals/pools/${encodeURIComponent(poolId)}${query({ workspace_id: workspaceId })}`);
    },
    decideApproval(payload) {
      return atlasFetch('/api/atlas/approvals/decide', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    executeSafeApply(payload) {
      return atlasFetch('/api/atlas/safe-apply/execute', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    restoreChangeSnapshot(payload) {
      return atlasFetch('/api/atlas/change-snapshots/restore', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    runVerification(payload) {
      return atlasFetch('/api/atlas/verification/run', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    runDebugReview(payload) {
      return atlasFetch('/api/atlas/debug-review/run', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    generatePatchProposal(payload) {
      return atlasFetch('/api/atlas/patch-proposals/generate', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    decidePatchProposal(payload) {
      return atlasFetch('/api/atlas/patch-proposals/decide', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    createPatchProposalPlanItemDraft(payload) {
      return atlasFetch('/api/atlas/patch-proposals/planitem-draft', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getAutoPolicyPresets() {
      return atlasFetch('/api/atlas/auto-policy/presets');
    },
    decideAutomation(payload) {
      return atlasFetch('/api/atlas/automation/decide', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    autoSafeApplyOne(payload) {
      return atlasFetch('/api/atlas/automation/safe-apply-one', { method: 'POST', body: JSON.stringify(payload || {}) });
    },

    getVerificationAllowlist() {
      return atlasFetch('/api/atlas/verification/allowlist');
    },
    autoVerifyOne(payload) {
      return atlasFetch('/api/atlas/automation/verify-one', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    autoSafeApplyOneAndVerify(payload) {
      return atlasFetch('/api/atlas/automation/safe-apply-one-and-verify', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getFailureSuggestion(payload) {
      return atlasFetch('/api/atlas/automation/failure-suggestion', { method: 'POST', body: JSON.stringify(payload || {}) });
    },

    devToolGitStatus(payload) {
      return atlasFetch('/api/atlas/dev-tools/git-status', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    devToolGitDiff(payload) {
      return atlasFetch('/api/atlas/dev-tools/git-diff', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    devToolGitLsFiles(payload) {
      return atlasFetch('/api/atlas/dev-tools/git-ls-files', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    devToolProjectTree(payload) {
      return atlasFetch('/api/atlas/dev-tools/project-tree', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    devToolListFiles(payload) {
      return atlasFetch('/api/atlas/dev-tools/list-files', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    devToolFileOutline(payload) {
      return atlasFetch('/api/atlas/dev-tools/file-outline', { method: 'POST', body: JSON.stringify(payload || {}) });
    },

    getContextRefreshPolicies() {
      return atlasFetch('/api/atlas/context-refresh/policies');
    },
    runContextRefresh(payload) {
      return atlasFetch('/api/atlas/context-refresh/run', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getContextRefreshBundle(poolId, bundleId) {
      return atlasFetch(`/api/atlas/context-refresh/bundles/${encodeURIComponent(poolId)}/${encodeURIComponent(bundleId)}`);
    },
    getLatestContextRefresh(payload) {
      return atlasFetch('/api/atlas/context-refresh/latest', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getEvaluatorPolicies() {
      return atlasFetch('/api/atlas/evaluator/policies');
    },
    runEvaluator(payload) {
      return atlasFetch('/api/atlas/evaluator/evaluate', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getEvaluatorResult(poolId, evalId) {
      return atlasFetch(`/api/atlas/evaluator/results/${encodeURIComponent(poolId)}/${encodeURIComponent(evalId)}`);
    },
    getLatestEvaluatorResult(payload) {
      return atlasFetch('/api/atlas/evaluator/latest', { method: 'POST', body: JSON.stringify(payload || {}) });
    },

    getMultiItemAutopilotPolicies() {
      return atlasFetch('/api/atlas/multi-item-autopilot/policies');
    },
    runMultiItemAutopilot(payload) {
      return atlasFetch('/api/atlas/multi-item-autopilot/run', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getMultiItemAutopilotResult(poolId, autopilotRunId) {
      return atlasFetch(`/api/atlas/multi-item-autopilot/results/${encodeURIComponent(poolId)}/${encodeURIComponent(autopilotRunId)}`);
    },
    getLatestMultiItemAutopilotResult(payload) {
      return atlasFetch('/api/atlas/multi-item-autopilot/latest', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    submitClarificationAnswers(payload) {
      return atlasFetch("/api/atlas/clarifications/answer", { method: "POST", body: JSON.stringify(payload || {}) });
    },
    getPatchRegenFromRecommendationPolicies() {
      return atlasFetch('/api/atlas/patch-regen-from-recommendation/policies');
    },
    runPatchRegenFromRecommendation(payload) {
      return atlasFetch('/api/atlas/patch-regen-from-recommendation/run', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getPatchRegenFromRecommendationResult(poolId, recommendationExecId) {
      return atlasFetch(`/api/atlas/patch-regen-from-recommendation/results/${encodeURIComponent(poolId)}/${encodeURIComponent(recommendationExecId)}`);
    },
    getLatestPatchRegenFromRecommendation(payload) {
      return atlasFetch('/api/atlas/patch-regen-from-recommendation/latest', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getSupervisedItemStatusPolicies() { return atlasFetch('/api/atlas/supervised-item-status/policies'); },
    finalizeSupervisedItemStatus(payload) { return atlasFetch('/api/atlas/supervised-item-status/finalize', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getSupervisedItemStatusResult(poolId, finalizeRunId) { return atlasFetch(`/api/atlas/supervised-item-status/results/${encodeURIComponent(poolId)}/${encodeURIComponent(finalizeRunId)}`); },
    getLatestSupervisedItemStatus(payload) { return atlasFetch('/api/atlas/supervised-item-status/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },

    getMultiItemSupervisedStatusPolicies() { return atlasFetch('/api/atlas/multi-item-supervised-status/policies'); },
    buildMultiItemSupervisedStatus(payload) { return atlasFetch('/api/atlas/multi-item-supervised-status/build', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getMultiItemSupervisedStatusResult(poolId, multiStatusRunId) { return atlasFetch(`/api/atlas/multi-item-supervised-status/results/${encodeURIComponent(poolId)}/${encodeURIComponent(multiStatusRunId)}`); },
    getLatestMultiItemSupervisedStatus(payload) { return atlasFetch('/api/atlas/multi-item-supervised-status/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },

    getNextActionOrchestratorPolicies() { return atlasFetch('/api/atlas/next-action-orchestrator/policies'); },
    prepareNextAction(payload) { return atlasFetch('/api/atlas/next-action-orchestrator/prepare', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getNextActionOrchestratorResult(poolId, orchestratorRunId) { return atlasFetch(`/api/atlas/next-action-orchestrator/results/${encodeURIComponent(poolId)}/${encodeURIComponent(orchestratorRunId)}`); },
    getLatestNextActionOrchestrator(payload) { return atlasFetch('/api/atlas/next-action-orchestrator/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },

  };

  root.AtlasPipelineAPI = AtlasPipelineAPI;
})();

export async function getSymbolIndex(payload) {
  const r = await fetch("/api/atlas/code-intel/symbol-index", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`symbol-index failed: ${r.status}`);
  return r.json();
}

export async function getDependencyGraph(payload) {
  const r = await fetch("/api/atlas/code-intel/dependency-graph", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`dependency-graph failed: ${r.status}`);
  return r.json();
}

export async function getRelatedTests(payload) {
  const r = await fetch("/api/atlas/code-intel/related-tests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`related-tests failed: ${r.status}`);
  return r.json();
}


export async function getBoundedRetryPolicies(){ return apiGet("/api/atlas/bounded-retry/policies"); }
export async function runBoundedRetry(payload){ return apiPost("/api/atlas/bounded-retry/run", payload); }
export async function getBoundedRetryResult(poolId, retryRunId){ return apiGet(`/api/atlas/bounded-retry/results/${encodeURIComponent(poolId)}/${encodeURIComponent(retryRunId)}`); }
export async function getLatestBoundedRetryResult(payload){ return apiPost("/api/atlas/bounded-retry/latest", payload); }

export async function getPatchRegenPolicies(){ return apiGet('/api/atlas/patch-regen/policies'); }
export async function runPatchRegen(payload){ return apiPost('/api/atlas/patch-regen/run', payload); }
export async function getPatchRegenResult(poolId, regenRunId){ return apiGet(`/api/atlas/patch-regen/results/${encodeURIComponent(poolId)}/${encodeURIComponent(regenRunId)}`); }
export async function getLatestPatchRegenResult(payload){ return apiPost('/api/atlas/patch-regen/latest', payload); }


export async function getPatchCandidateApprovalPolicies(){return apiGet('/api/atlas/patch-candidate-approval/policies');}
export async function decidePatchCandidateApproval(payload){return apiPost('/api/atlas/patch-candidate-approval/decide',payload);}
export async function getPatchCandidateApprovalResult(poolId, approvalRunId){return apiGet(`/api/atlas/patch-candidate-approval/results/${encodeURIComponent(poolId)}/${encodeURIComponent(approvalRunId)}`);}
export async function getLatestPatchCandidateApproval(payload){return apiPost('/api/atlas/patch-candidate-approval/latest',payload);}
export async function getSafeApplyHandoff(poolId, handoffId){return apiGet(`/api/atlas/safe-apply-handoffs/${encodeURIComponent(poolId)}/${encodeURIComponent(handoffId)}`);}
export async function getLatestSafeApplyHandoff(payload){return apiPost('/api/atlas/safe-apply-handoffs/latest',payload);}
export async function getSupervisedHandoffSafeApplyPolicies(){return apiGet('/api/atlas/supervised-handoff-safe-apply/policies');}
export async function executeSupervisedHandoffSafeApply(payload){return apiPost('/api/atlas/supervised-handoff-safe-apply/execute',payload);}
export async function getSupervisedHandoffSafeApplyResult(poolId, executionId){return apiGet(`/api/atlas/supervised-handoff-safe-apply/results/${encodeURIComponent(poolId)}/${encodeURIComponent(executionId)}`);}
export async function getLatestSupervisedHandoffSafeApply(payload){return apiPost('/api/atlas/supervised-handoff-safe-apply/latest',payload);}


export async function getSupervisedHandoffVerificationPolicies(){ const r=await fetch("/api/atlas/supervised-handoff-verification/policies"); return r.json(); }
export async function runSupervisedHandoffVerification(payload){ const r=await fetch("/api/atlas/supervised-handoff-verification/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}); return r.json(); }
export async function getSupervisedHandoffVerificationResult(poolId, verificationRunId){ const r=await fetch(`/api/atlas/supervised-handoff-verification/results/${encodeURIComponent(poolId)}/${encodeURIComponent(verificationRunId)}`); return r.json(); }
export async function getLatestSupervisedHandoffVerification(payload){ const r=await fetch("/api/atlas/supervised-handoff-verification/latest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}); return r.json(); }

export async function getSupervisedHandoffRetryPolicies(){return apiGet("/api/atlas/supervised-handoff-retry/policies");}
export async function runSupervisedHandoffRetry(payload){return apiPost("/api/atlas/supervised-handoff-retry/run",payload);}
export async function getSupervisedHandoffRetryResult(poolId, supervisedRetryRunId){return apiGet(`/api/atlas/supervised-handoff-retry/results/${encodeURIComponent(poolId)}/${encodeURIComponent(supervisedRetryRunId)}`);}
export async function getLatestSupervisedHandoffRetry(payload){return apiPost("/api/atlas/supervised-handoff-retry/latest",payload);}


export async function getPatchRegenRecommendationPolicies(){ return apiGet('/api/atlas/patch-regen-recommendation/policies'); }
export async function runPatchRegenRecommendation(payload){ return apiPost('/api/atlas/patch-regen-recommendation/run', payload); }
export async function getPatchRegenRecommendationResult(poolId, recommendationRunId){ return apiGet(`/api/atlas/patch-regen-recommendation/results/${encodeURIComponent(poolId)}/${encodeURIComponent(recommendationRunId)}`); }
export async function getLatestPatchRegenRecommendation(payload){ return apiPost('/api/atlas/patch-regen-recommendation/latest', payload); }

export async function getPatchRegenFromRecommendationPolicies(){return apiGet('/api/atlas/patch-regen-from-recommendation/policies');}
export async function runPatchRegenFromRecommendation(payload){return apiPost('/api/atlas/patch-regen-from-recommendation/run',payload);}
export async function getPatchRegenFromRecommendationResult(poolId,recommendationExecId){return apiGet(`/api/atlas/patch-regen-from-recommendation/results/${encodeURIComponent(poolId)}/${encodeURIComponent(recommendationExecId)}`);}
export async function getLatestPatchRegenFromRecommendation(payload){return apiPost('/api/atlas/patch-regen-from-recommendation/latest',payload);}
