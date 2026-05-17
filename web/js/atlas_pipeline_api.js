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
    submitClarificationAnswers(payload) {
      return atlasFetch("/api/atlas/clarifications/answer", { method: "POST", body: JSON.stringify(payload || {}) });
    },
  };

  root.AtlasPipelineAPI = AtlasPipelineAPI;
})();
