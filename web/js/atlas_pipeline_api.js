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
    getRepoContextImpactedTests(payload) {
      return atlasFetch('/api/atlas/repo-context/impacted-tests', {
        method: 'POST',
        body: JSON.stringify(payload || {})
      });
    },

  };

  root.AtlasPipelineAPI = AtlasPipelineAPI;
})();
