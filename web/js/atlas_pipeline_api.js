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
    submitClarificationAnswers(payload) {
      return atlasFetch("/api/atlas/clarifications/answer", { method: "POST", body: JSON.stringify(payload || {}) });
    },
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
