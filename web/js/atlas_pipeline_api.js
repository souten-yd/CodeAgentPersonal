(function () {
  const root = (typeof window !== 'undefined' ? window : globalThis);
  const API_BASE = root.API || '';

  // Map a gateway/proxy status (often returning an HTML error page from Cloudflare/runpod) to a
  // short, safe, user-facing message. We never surface the raw HTML body to the UI.
  function gatewayMessage(status, statusText) {
    if (status === 502 || status === 503 || status === 504 || status === 524) {
      return 'サーバが時間内に応答しませんでした（タイムアウト）。モデルが混雑しています。少し待って再実行してください。';
    }
    if (status === 0) return 'リクエストがタイムアウト/中断されました。少し待って再実行してください。';
    return `リクエストに失敗しました (HTTP ${status}${statusText ? ' ' + statusText : ''})`;
  }

  function looksLikeHtml(text) {
    const head = String(text || '').slice(0, 200).toLowerCase();
    return head.includes('<html') || head.includes('<!doctype') || head.includes('cf-error') || head.includes('cloudflare');
  }

  async function parseResponse(response) {
    const contentType = response.headers.get('content-type') || '';
    const isJson = contentType.includes('application/json');
    const payload = isJson ? await response.json().catch(() => null) : await response.text();
    if (!response.ok) {
      // Non-JSON error body (e.g. a Cloudflare/runpod 5xx HTML page): NEVER pass the raw HTML to the
      // UI. Replace it with a short canned message and a status-derived code.
      if (!isJson || looksLikeHtml(payload)) {
        const isGateway = [502, 503, 504, 524, 0].includes(response.status);
        return {
          ok: false,
          status: response.status,
          code: isGateway ? 'gateway_timeout' : `http_${response.status}`,
          error: true,
          message: gatewayMessage(response.status, response.statusText),
          detail: { error: isGateway ? 'gateway_timeout' : 'http_error', status: response.status },
        };
      }
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

  // Default per-request timeout. Long-running operations (plan creation, autopilot) pass a larger
  // timeoutMs. On abort we synthesize a gateway-style timeout result instead of throwing raw.
  const DEFAULT_TIMEOUT_MS = 120000;

  async function atlasFetch(path, options) {
    const opts = options || {};
    const timeoutMs = opts.timeoutMs || DEFAULT_TIMEOUT_MS;
    const controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    try {
      const response = await fetch(API_BASE + path, {
        headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
        ...opts,
        signal: controller ? controller.signal : undefined,
      });
      return await parseResponse(response);
    } catch (err) {
      const aborted = err && (err.name === 'AbortError' || /abort/i.test(String(err)));
      return {
        ok: false,
        status: 0,
        code: aborted ? 'gateway_timeout' : 'network_error',
        error: true,
        message: aborted ? gatewayMessage(0) : 'ネットワークエラーが発生しました。接続を確認して再実行してください。',
        detail: { error: aborted ? 'timeout' : 'network_error' },
      };
    } finally {
      if (timer) clearTimeout(timer);
    }
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
    // Async plan-pool creation: the server returns immediately with {pool_id, status:"queued"} and
    // does the slow LLM planning on a background thread. We poll status until ready, then fetch the
    // full pool. This avoids the proxy 524 timeout that produced the raw Cloudflare HTML in the UI.
    async createPlanPool(payload) {
      const started = await atlasFetch('/api/atlas/plan-pools', {
        method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 30000,
      });
      if (!started.ok) return started;
      const data = started.data || {};
      // Async path: poll the job to completion.
      if (data.pool_id && (data.status === 'queued' || data.status === 'running')) {
        return await this.pollPlanPoolUntilReady(data.pool_id, payload && payload.workspace_id);
      }
      // Sync path (server returned the full pool directly): pass through unchanged.
      return started;
    },
    getPlanPoolStatus(poolId) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/status`, { timeoutMs: 15000 });
    },
    // Local models (e.g. Gemma-4B on RunPod) can take several minutes to plan + research + critique.
    // Keep polling well past the old 240s so slow-but-successful runs aren't reported as timeouts.
    async pollPlanPoolUntilReady(poolId, workspaceId, maxWaitMs = 480000, intervalMs = 1500) {
      const startTime = Date.now();
      while (Date.now() - startTime < maxWaitMs) {
        await new Promise((r) => setTimeout(r, intervalMs));
        const st = await this.getPlanPoolStatus(poolId);
        if (!st.ok) {
          // 404 right after submit just means the job file isn't written yet — keep waiting.
          if (st.status === 404) continue;
          return st;
        }
        const status = (st.data && st.data.status) || '';
        if (status === 'ready') {
          return await atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}${query({ workspace_id: workspaceId })}`, { timeoutMs: 30000 });
        }
        if (status === 'failed') {
          return {
            ok: false, status: 200, error: true, code: 'plan_pool_failed',
            message: (st.data && st.data.error) || 'プラン作成に失敗しました。再実行してください。',
            detail: { error: 'plan_pool_failed' },
          };
        }
      }
      return {
        ok: false, status: 0, error: true, code: 'plan_pool_timeout',
        message: 'プラン作成がタイムアウトしました。モデルが混雑しています。少し待って再実行してください。',
        detail: { error: 'plan_pool_timeout' },
      };
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
    cancelPlanPool(poolId, payload) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/cancel`, { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    clarifyPlanPool(poolId, payload) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/clarify`, { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getAutomationFeatures() {
      return atlasFetch('/api/atlas/automation-features');
    },
    setAutomationFeatures(payload) {
      return atlasFetch('/api/atlas/automation-features', { method: 'POST', body: JSON.stringify(payload || {}) });
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
    getContextRefreshV2(payload) {
      return atlasFetch('/api/atlas/context-refresh/v2', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
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


    getPostManualExecutionRefreshPolicies() { return atlasFetch('/api/atlas/post-manual-execution-refresh/policies'); },
    refreshAfterManualExecution(payload) { return atlasFetch('/api/atlas/post-manual-execution-refresh/refresh', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getPostManualExecutionRefreshResult(poolId, refreshRunId) { return atlasFetch(`/api/atlas/post-manual-execution-refresh/results/${encodeURIComponent(poolId)}/${encodeURIComponent(refreshRunId)}`); },
    getLatestPostManualExecutionRefresh(payload) { return atlasFetch('/api/atlas/post-manual-execution-refresh/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },

    getSymbolIndex(payload) { return atlasFetch('/api/atlas/code-intel/symbol-index', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getDependencyGraph(payload) { return atlasFetch('/api/atlas/code-intel/dependency-graph', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getRelatedTests(payload) { return atlasFetch('/api/atlas/code-intel/related-tests', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getBoundedRetryPolicies() { return atlasFetch('/api/atlas/bounded-retry/policies'); },
    runBoundedRetry(payload) { return atlasFetch('/api/atlas/bounded-retry/run', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getBoundedRetryResult(poolId, retryRunId) { return atlasFetch(`/api/atlas/bounded-retry/results/${encodeURIComponent(poolId)}/${encodeURIComponent(retryRunId)}`); },
    getLatestBoundedRetryResult(payload) { return atlasFetch('/api/atlas/bounded-retry/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getPatchRegenPolicies() { return atlasFetch('/api/atlas/patch-regen/policies'); },
    runPatchRegen(payload) { return atlasFetch('/api/atlas/patch-regen/run', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getPatchRegenResult(poolId, regenRunId) { return atlasFetch(`/api/atlas/patch-regen/results/${encodeURIComponent(poolId)}/${encodeURIComponent(regenRunId)}`); },
    getLatestPatchRegenResult(payload) { return atlasFetch('/api/atlas/patch-regen/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getPatchCandidateApprovalPolicies() { return atlasFetch('/api/atlas/patch-candidate-approval/policies'); },
    decidePatchCandidateApproval(payload) { return atlasFetch('/api/atlas/patch-candidate-approval/decide', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getPatchCandidateApprovalResult(poolId, approvalRunId) { return atlasFetch(`/api/atlas/patch-candidate-approval/results/${encodeURIComponent(poolId)}/${encodeURIComponent(approvalRunId)}`); },
    getLatestPatchCandidateApproval(payload) { return atlasFetch('/api/atlas/patch-candidate-approval/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getSafeApplyHandoff(poolId, handoffId) { return atlasFetch(`/api/atlas/safe-apply-handoffs/${encodeURIComponent(poolId)}/${encodeURIComponent(handoffId)}`); },
    getLatestSafeApplyHandoff(payload) { return atlasFetch('/api/atlas/safe-apply-handoffs/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getSupervisedHandoffSafeApplyPolicies() { return atlasFetch('/api/atlas/supervised-handoff-safe-apply/policies'); },
    executeSupervisedHandoffSafeApply(payload) { return atlasFetch('/api/atlas/supervised-handoff-safe-apply/execute', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getSupervisedHandoffSafeApplyResult(poolId, executionId) { return atlasFetch(`/api/atlas/supervised-handoff-safe-apply/results/${encodeURIComponent(poolId)}/${encodeURIComponent(executionId)}`); },
    getLatestSupervisedHandoffSafeApply(payload) { return atlasFetch('/api/atlas/supervised-handoff-safe-apply/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getSupervisedHandoffVerificationPolicies() { return atlasFetch('/api/atlas/supervised-handoff-verification/policies'); },
    runSupervisedHandoffVerification(payload) { return atlasFetch('/api/atlas/supervised-handoff-verification/run', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getSupervisedHandoffVerificationResult(poolId, verificationRunId) { return atlasFetch(`/api/atlas/supervised-handoff-verification/results/${encodeURIComponent(poolId)}/${encodeURIComponent(verificationRunId)}`); },
    getLatestSupervisedHandoffVerification(payload) { return atlasFetch('/api/atlas/supervised-handoff-verification/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getSupervisedHandoffRetryPolicies() { return atlasFetch('/api/atlas/supervised-handoff-retry/policies'); },
    runSupervisedHandoffRetry(payload) { return atlasFetch('/api/atlas/supervised-handoff-retry/run', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getSupervisedHandoffRetryResult(poolId, supervisedRetryRunId) { return atlasFetch(`/api/atlas/supervised-handoff-retry/results/${encodeURIComponent(poolId)}/${encodeURIComponent(supervisedRetryRunId)}`); },
    getLatestSupervisedHandoffRetry(payload) { return atlasFetch('/api/atlas/supervised-handoff-retry/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getPatchRegenRecommendationPolicies() { return atlasFetch('/api/atlas/patch-regen-recommendation/policies'); },
    runPatchRegenRecommendation(payload) { return atlasFetch('/api/atlas/patch-regen-recommendation/run', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getPatchRegenRecommendationResult(poolId, recommendationRunId) { return atlasFetch(`/api/atlas/patch-regen-recommendation/results/${encodeURIComponent(poolId)}/${encodeURIComponent(recommendationRunId)}`); },
    getLatestPatchRegenRecommendation(payload) { return atlasFetch('/api/atlas/patch-regen-recommendation/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getManualNextActionExecutorPolicies() { return atlasFetch('/api/atlas/manual-next-action-executor/policies'); },
    executeManualNextAction(payload) { return atlasFetch('/api/atlas/manual-next-action-executor/execute', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getManualNextActionExecutorResult(poolId, executorRunId) { return atlasFetch(`/api/atlas/manual-next-action-executor/results/${encodeURIComponent(poolId)}/${encodeURIComponent(executorRunId)}`); },
    getLatestManualNextActionExecutor(payload) { return atlasFetch('/api/atlas/manual-next-action-executor/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    previewManualNextActionConfirmationToken(payload) { return atlasFetch('/api/atlas/manual-next-action-executor/confirmation-token-preview', { method: 'POST', body: JSON.stringify(payload || {}) }); },

    getGuardedOperatorLoopPolicies() { return atlasFetch('/api/atlas/guarded-operator-loop/policies'); },
    runGuardedOperatorLoop(payload) { return atlasFetch('/api/atlas/guarded-operator-loop/run', { method: 'POST', body: JSON.stringify(payload || {}) }); },
    getGuardedOperatorLoopResult(poolId, loopRunId) { return atlasFetch(`/api/atlas/guarded-operator-loop/results/${encodeURIComponent(poolId)}/${encodeURIComponent(loopRunId)}`); },
    getLatestGuardedOperatorLoop(payload) { return atlasFetch('/api/atlas/guarded-operator-loop/latest', { method: 'POST', body: JSON.stringify(payload || {}) }); },

    getRepoIndexPolicies() {
      return atlasFetch('/api/atlas/repo-index/policies');
    },
    buildRepoIndex(payload) {
      return atlasFetch('/api/atlas/repo-index/build', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
    },
    getRepoIndexImpacts(payload) {
      return atlasFetch('/api/atlas/repo-index/impacts', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
    },
    getRepoIndexRelatedTests(payload) {
      return atlasFetch('/api/atlas/repo-index/related-tests', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
    },
    getLatestRepoIndex(payload) {
      return atlasFetch('/api/atlas/repo-index/latest', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
    },
    getRepoIndexResult(projectHash, indexRunId) {
      return atlasFetch(`/api/atlas/repo-index/results/${encodeURIComponent(projectHash)}/${encodeURIComponent(indexRunId)}`);
    },
    getRepoContextPolicies() {
      return atlasFetch('/api/atlas/repo-context/policies');
    },
    getRepoContextSnapshot(payload) {
      return atlasFetch('/api/atlas/repo-context/snapshot', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
    },
    getRepoContextScopeSummary(payload) {
      return atlasFetch('/api/atlas/repo-context/scope-summary', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
    },
    getRepoContextVerificationPlan(payload) {
      return atlasFetch('/api/atlas/repo-context/verification-plan', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getRepoContextPlanItemImpactMap(payload) {
      return atlasFetch('/api/atlas/repo-context/plan-item-impact-map', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getPlannerPackagingV2(payload) {
      return atlasFetch('/api/atlas/repo-context/planner-packaging-v2', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getVerificationRecommendation(payload) {
      return atlasFetch('/api/atlas/repo-context/verification-recommendation', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
    },
    getVerificationRecommendationHandoff(payload) {
      return atlasFetch('/api/atlas/repo-context/verification-recommendation-handoff', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
    },
    getRepoContextImpactedTests(payload) {
      return atlasFetch('/api/atlas/repo-context/impacted-tests', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
    },
    getAutomationProfilePolicies() {
      return atlasFetch('/api/atlas/automation-safety-profile/policies');
    },
    getLatestAutomationProfile() {
      return atlasFetch('/api/atlas/automation-safety-profile/latest');
    },
    previewAutomationProfile(payload) {
      return atlasFetch('/api/atlas/automation-safety-profile/preview', {
        method: 'POST', body: JSON.stringify(payload || {})
      });
    },
    selectAutomationProfile(payload) {
      return atlasFetch('/api/atlas/automation-safety-profile/select', {
        method: 'POST', body: JSON.stringify(payload || {})
      });
    },
    getPreAuthorizedEnvelopes() {
      return atlasFetch('/api/atlas/automation-safety-profile/pre-authorized-envelopes');
    },
    startAutonomousLoopFromEnvelope(payload) {
      return atlasFetch('/api/atlas/automation-safety-profile/start-autonomous-loop', {
        method: 'POST', body: JSON.stringify(payload || {})
      });
    },

  };

  root.AtlasPipelineAPI = AtlasPipelineAPI;
})();
