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
  const PLAN_POOL_ABSOLUTE_MAX_MS = 2700000;
  const PATCHGEN_ABSOLUTE_MAX_MS = 3600000;

  async function atlasFetch(path, options) {
    const opts = options || {};
    const timeoutMs = opts.timeoutMs || DEFAULT_TIMEOUT_MS;
    const controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    try {
      // FormData bodies must let the browser set multipart Content-Type (with the
      // boundary); forcing application/json would corrupt the upload.
      const isFormBody = (typeof FormData !== 'undefined') && opts.body instanceof FormData;
      const response = await fetch(API_BASE + path, {
        ...opts,
        headers: isFormBody
          ? (opts.headers || undefined)
          : { 'Content-Type': 'application/json', ...(opts.headers || {}) },
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
    // Local models can take a long time while still making progress. The browser does NOT police
    // generation time: whether the model is still generating tokens, has stalled, or is done is
    // judged SERVER-SIDE (status running/ready/failed + is_stalled, which the server derives from
    // the live token heartbeat). The client just reads that verdict and reacts. There is no
    // client-side absolute deadline — a long-but-progressing local model (GPU busy, tokens still
    // flowing) must never be aborted by a browser stopwatch. We stop only when the server reports a
    // terminal/stalled state, or the status endpoint itself becomes unreachable.
    // maxWaitMs is accepted for backward compatibility but intentionally ignored.
    async pollPlanPoolUntilReady(poolId, workspaceId, maxWaitMs, intervalMs = 1500) {
      void maxWaitMs;
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await new Promise((r) => setTimeout(r, intervalMs));
        const st = await this.getPlanPoolStatus(poolId);
        if (!st.ok) {
          // 404 right after submit just means the job file isn't written yet — keep waiting.
          if (st.status === 404) continue;
          // Status endpoint unreachable / server error: the server is the authority and we can no
          // longer read it, so surface the failure instead of spinning forever.
          return st;
        }
        const status = (st.data && st.data.status) || '';
        const currentPhase = (st.data && (st.data.current_phase || st.data.phase)) || '';
        const secondsSinceProgress = Number(st.data && st.data.seconds_since_progress);
        const tokensGenerated = Number(st.data && st.data.tokens_generated);
        const maxCtx = Number(st.data && st.data.max_ctx);
        if (typeof window !== 'undefined' && (status === 'running' || status === 'revising')) {
          window.dispatchEvent(new CustomEvent('atlas:llm-progress', {
            detail: { phase: currentPhase, tokens: tokensGenerated, maxCtx, secondsSince: secondsSinceProgress, poolId },
          }));
        }
        const progressDetail = [
          currentPhase ? `フェーズ: ${currentPhase}` : '',
          Number.isFinite(secondsSinceProgress) ? `最終進捗から ${Math.round(secondsSinceProgress)} 秒` : '',
          Number.isFinite(tokensGenerated) && tokensGenerated > 0 ? `tokens: ${tokensGenerated}` : '',
        ].filter(Boolean).join(' / ');
        // Server-side stall verdict (derived from the token heartbeat). This is the ONLY timeout
        // judgment — the browser does not second-guess it.
        if (st.data && st.data.is_stalled === true) {
          const reason = st.data.stalled_reason || 'LLM生成の進捗が停止している可能性があります。';
          const action = st.data.suggested_action || '少し待つか、再実行してください。';
          return {
            ok: false, status: 200, error: true, code: 'plan_pool_stalled',
            message: `${reason}${progressDetail ? ` (${progressDetail})` : ''} ${action}`,
            detail: { error: 'plan_pool_stalled', status, current_phase: currentPhase, seconds_since_progress: secondsSinceProgress },
          };
        }
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
    },
    listPlanPools() {
      return atlasFetch('/api/atlas/plan-pools');
    },
    getPlanPool(poolId) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}`);
    },
    getPlanRuntimeStatus(poolId, workspaceId) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/runtime-status${query({ workspace_id: workspaceId })}`);
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
    getPipelineEvents(poolId, runId, workspaceId, afterSequence) {
      return atlasFetch(`/api/atlas/pipeline/events/${encodeURIComponent(poolId)}/${encodeURIComponent(runId)}${query({ workspace_id: workspaceId, after_sequence: afterSequence })}`);
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
    decideCriticalEvent(payload) {
      return atlasFetch('/api/atlas/critical-decisions/decide', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    resetPoolExecution(poolId, payload) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/reset-execution`, { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    async requestRevision(poolId, payload) {
      const resp = await atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/request-revision`, {
        method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 30000,
      });
      if (!resp.ok) return resp;
      // Async path: server returned immediately with status "revising" — poll until ready.
      if (resp.data && resp.data.status === 'revising') {
        return await this.pollPlanPoolUntilReady(poolId, payload && payload.workspace_id);
      }
      return resp;
    },
    cancelPlanPool(poolId, payload) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/cancel`, { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    grantSafetyOverride(poolId, payload) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/safety-override`, { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    clarifyPlanPool(poolId, payload) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/clarify`, { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    grantSafetyOverride(poolId, payload) {
      return atlasFetch(`/api/atlas/plan-pools/${encodeURIComponent(poolId)}/safety-override`, { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getAutomationFeatures() {
      return atlasFetch('/api/atlas/automation-features');
    },
    setAutomationFeatures(payload) {
      return atlasFetch('/api/atlas/automation-features', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    executeSafeApply(payload) {
      return atlasFetch('/api/atlas/safe-apply/execute', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 300000 });
    },
    restoreChangeSnapshot(payload) {
      return atlasFetch('/api/atlas/change-snapshots/restore', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    async pollVerificationUntilDone(poolId, itemId) {
      const absMax = root.ATLAS_PLAN_ABSOLUTE_MAX_MS || PLAN_POOL_ABSOLUTE_MAX_MS;
      const start = Date.now();
      while (Date.now() - start < absMax) {
        await new Promise((r) => setTimeout(r, 1500));
        const st = await atlasFetch(`/api/atlas/verification/status${query({ pool_id: poolId, item_id: itemId })}`, { timeoutMs: 15000 });
        if (!st.ok) {
          if (st.status === 404) continue;
          return st;
        }
        const d = st.data || {};
        if (d.is_stalled) {
          const sec = Math.round(d.seconds_since_progress || 0);
          return { ok: false, status: 200, error: true, code: 'verification_stalled', message: `検証コマンドが${sec}秒無進捗です。コマンドがハングしている可能性があります。`, detail: { error: 'verification_stalled' } };
        }
        if (d.status === 'done') return { ok: true, status: 200, data: d.result || d };
        if (d.status === 'failed') return { ok: false, status: 200, error: true, code: 'verification_failed', message: d.error || '検証に失敗しました。', detail: { error: 'verification_failed' } };
      }
      return { ok: false, status: 0, error: true, code: 'verification_absolute_timeout', message: '検証が絶対上限に達しました。', detail: { error: 'verification_absolute_timeout' } };
    },
    async runVerification(payload) {
      const resp = await atlasFetch('/api/atlas/verification/run', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 30000 });
      if (!resp.ok) return resp;
      if (resp.data && resp.data.status === 'running') {
        return await this.pollVerificationUntilDone(payload.pool_id, payload.item_id);
      }
      return resp;
    },
    async pollDebugReviewUntilDone(poolId, itemId) {
      const absMax = root.ATLAS_PLAN_ABSOLUTE_MAX_MS || PLAN_POOL_ABSOLUTE_MAX_MS;
      const start = Date.now();
      while (Date.now() - start < absMax) {
        await new Promise((r) => setTimeout(r, 1500));
        const st = await atlasFetch(`/api/atlas/debug-review/status${query({ pool_id: poolId, item_id: itemId })}`, { timeoutMs: 15000 });
        if (!st.ok) {
          if (st.status === 404) continue;
          return st;
        }
        const d = st.data || {};
        if (d.is_stalled) {
          const sec = Math.round(d.seconds_since_progress || 0);
          return { ok: false, status: 200, error: true, code: 'debug_review_stalled', message: `デバッグレビューが${sec}秒無進捗です。モデルが停止している可能性があります。`, detail: { error: 'debug_review_stalled' } };
        }
        if (d.status === 'done') return { ok: true, status: 200, data: d.result || d };
        if (d.status === 'failed') return { ok: false, status: 200, error: true, code: 'debug_review_failed', message: d.error || 'デバッグレビューに失敗しました。', detail: { error: 'debug_review_failed' } };
      }
      return { ok: false, status: 0, error: true, code: 'debug_review_absolute_timeout', message: 'デバッグレビューが絶対上限に達しました。', detail: { error: 'debug_review_absolute_timeout' } };
    },
    async runDebugReview(payload) {
      const resp = await atlasFetch('/api/atlas/debug-review/run', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 30000 });
      if (!resp.ok) return resp;
      if (resp.data && resp.data.status === 'running') {
        return await this.pollDebugReviewUntilDone(payload.pool_id, payload.item_id);
      }
      return resp;
    },
    getPatchGenStatus(poolId, itemId) {
      return atlasFetch(`/api/atlas/patch-proposals/status${query({ pool_id: poolId, item_id: itemId })}`, { timeoutMs: 10000 });
    },
    async generatePatchProposal(payload) {
      const poolId = payload && payload.pool_id;
      const itemId = payload && payload.item_id;
      const generatePromise = atlasFetch('/api/atlas/patch-proposals/generate', {
        method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: PATCHGEN_ABSOLUTE_MAX_MS,
      });
      if (!poolId || !itemId) return generatePromise;
      const self = this;
      let watcherDone = false;
      let resolveStall;
      const stallPromise = new Promise((resolve) => { resolveStall = resolve; });
      (async () => {
        const startTime = Date.now();
        while (!watcherDone && Date.now() - startTime < PATCHGEN_ABSOLUTE_MAX_MS) {
          await new Promise((r) => setTimeout(r, 2000));
          if (watcherDone) break;
          try {
            const st = await self.getPatchGenStatus(poolId, itemId);
            if (!st.ok || !st.data) continue;
            const d = st.data;
            // Surface live patch-generation progress on the SAME theme-colored indicator used
            // during plan generation, so the post-approval development phase shows phase + tokens
            // (mirrors pollPlanPoolUntilReady's atlas:llm-progress dispatch).
            if (typeof window !== 'undefined' && d.status === 'running') {
              window.dispatchEvent(new CustomEvent('atlas:llm-progress', {
                detail: {
                  phase: d.phase || 'patch_generation',
                  tokens: Number(d.tokens_generated) || 0,
                  maxCtx: Number(d.max_ctx) || 0,
                  secondsSince: Number(d.seconds_since_progress),
                  poolId,
                },
              }));
            }
            if (d.status === 'done') break;
            if (d.is_stalled) {
              const sec = Math.round(d.seconds_since_progress || 0);
              resolveStall({
                ok: false, status: 200, error: true, code: 'patchgen_stalled',
                message: `パッチ生成のLLMが${sec}秒無進捗です。${d.suggested_action || 'モデルが停止の可能性があります。再実行してください。'}`,
                detail: { error: 'patchgen_stalled', pool_id: poolId, item_id: itemId, seconds_since_progress: d.seconds_since_progress },
              });
              break;
            }
          } catch (_) { continue; }
        }
      })();
      const result = await Promise.race([generatePromise, stallPromise]);
      watcherDone = true;
      // Transport resilience: a synchronous patch generation holds the HTTP connection open for the
      // whole (10-60s+) LLM run with no bytes flowing, which mobile/LAN links routinely drop -> the
      // browser sees `network_error` even though the server THREAD keeps generating and writes the
      // patchgen job to completion. Surfacing that error makes the item skip as
      // missing_patch_or_content. Instead, recover the server-side outcome by polling the status.
      if (result && result.error && result.code === 'network_error' && poolId && itemId) {
        const recovered = await self.recoverPatchGenAfterDisconnect(poolId, itemId);
        if (recovered) return recovered;
      }
      return result;
    },
    async recoverPatchGenAfterDisconnect(poolId, itemId) {
      const start = Date.now();
      while (Date.now() - start < PATCHGEN_ABSOLUTE_MAX_MS) {
        await new Promise((r) => setTimeout(r, 2000));
        let st;
        try { st = await this.getPatchGenStatus(poolId, itemId); } catch (_) { continue; }
        if (!st || !st.ok || !st.data) continue;
        const d = st.data;
        if (d.is_stalled) return null; // server itself is not progressing -> surface original error
        if (d.status === 'running') {
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('atlas:llm-progress', {
              detail: {
                phase: d.phase || 'patch_generation',
                tokens: Number(d.tokens_generated) || 0,
                maxCtx: Number(d.max_ctx) || 0,
                secondsSince: Number(d.seconds_since_progress),
                poolId,
              },
            }));
          }
          continue;
        }
        if (d.status === 'done') {
          const base = d.patch_generation || { state: d.patch_generation_state, outcome: d.patch_generation_outcome };
          const success = !!base && base.state === 'succeeded' && base.outcome === 'success';
          // Mirror the field the build loop reads (patch_generation.patch_content_available) so a
          // recovered success is treated as appliable, not skipped.
          const pg = { ...base, patch_content_available: success };
          return {
            ok: true,
            status: 200,
            data: {
              status: success ? 'proposed' : ((base && base.state) || 'failed'),
              metadata: { patch_generation: pg, patch_content_available: success },
              recovered_after_disconnect: true,
            },
          };
        }
        if (d.status === 'failed' || d.status === 'cancelled') {
          return {
            ok: true,
            status: 200,
            data: {
              status: 'failed',
              metadata: { patch_generation: d.patch_generation || { state: d.status }, patch_content_available: false },
              recovered_after_disconnect: true,
            },
          };
        }
      }
      return null;
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
      return atlasFetch('/api/atlas/automation/safe-apply-one', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 300000 });
    },

    getVerificationAllowlist() {
      return atlasFetch('/api/atlas/verification/allowlist');
    },
    autoVerifyOne(payload) {
      return atlasFetch('/api/atlas/automation/verify-one', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 300000 });
    },
    autoSafeApplyOneAndVerify(payload) {
      return atlasFetch('/api/atlas/automation/safe-apply-one-and-verify', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 600000 });
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
      // This endpoint is SYNCHRONOUS server-side: it applies, verifies (browser smoke can take tens
      // of seconds), and runs self-correction (each repair = an LLM regenerate + re-apply + re-verify
      // that on a local model can take a couple of minutes). The default 2-minute fetch timeout
      // therefore aborts a legitimately-running item mid-repair and makes the UI look "stuck at apply".
      // Allow up to the server-side max_runtime budget.
      return atlasFetch('/api/atlas/multi-item-autopilot/run', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 1800000 });
    },
    getMultiItemAutopilotResult(poolId, autopilotRunId) {
      return atlasFetch(`/api/atlas/multi-item-autopilot/results/${encodeURIComponent(poolId)}/${encodeURIComponent(autopilotRunId)}`);
    },
    getLatestMultiItemAutopilotResult(payload) {
      return atlasFetch('/api/atlas/multi-item-autopilot/latest', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    getMultiItemAutopilotProgress(poolId, runId) {
      return atlasFetch(`/api/atlas/multi-item-autopilot/progress${query({ pool_id: poolId, run_id: runId })}`, { timeoutMs: 10000 });
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
    runAutonomousCodegen(payload) {
      return atlasFetch('/api/atlas/autonomous-codegen/start', {
        method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 1800000,
      });
    },
    getAutonomousCodegenStatus(poolId, orchestratorRunId) {
      return atlasFetch(`/api/atlas/autonomous-codegen/status/${encodeURIComponent(poolId)}/${encodeURIComponent(orchestratorRunId)}`);
    },
    getLatestAutonomousCodegen(poolId) {
      return atlasFetch(`/api/atlas/autonomous-codegen/latest/${encodeURIComponent(poolId)}`);
    },
    resolvePlayTarget(payload) {
      return atlasFetch('/api/atlas/play/target/resolve', {
        method: 'POST',
        body: JSON.stringify(payload || {}),
        timeoutMs: 30000,
      });
    },
    resolvePlayEnvironment(payload) {
      return atlasFetch('/api/atlas/play/environment/resolve', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    startPlaySession(payload) {
      return atlasFetch('/api/atlas/play/sessions/start', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 30000 });
    },
    getPlaySession(sessionId) {
      return atlasFetch(`/api/atlas/play/sessions/${encodeURIComponent(sessionId)}`, { timeoutMs: 15000 });
    },
    stopPlaySession(sessionId) {
      return atlasFetch(`/api/atlas/play/sessions/${encodeURIComponent(sessionId)}/stop`, { method: 'POST', body: JSON.stringify({}) });
    },
    restartPlaySession(sessionId) {
      return atlasFetch(`/api/atlas/play/sessions/${encodeURIComponent(sessionId)}/restart`, { method: 'POST', body: JSON.stringify({}) });
    },
    listPlayWorkspaceFiles(payload) {
      return atlasFetch('/api/atlas/play/workspace/files/list', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    readPlayWorkspaceFile(payload) {
      return atlasFetch('/api/atlas/play/workspace/files/read', { method: 'POST', body: JSON.stringify(payload || {}) });
    },
    writePlayWorkspaceFile(payload) {
      return atlasFetch('/api/atlas/play/workspace/files/write', { method: 'POST', body: JSON.stringify(payload || {}) });
    },

    // --- Capsule (PR-PPC-7) ---
    getCapsuleCapabilities() {
      return atlasFetch('/api/atlas/capsule/capabilities', { timeoutMs: 15000 });
    },
    buildCapsule(payload) {
      return atlasFetch('/api/atlas/capsule/build', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 60000 });
    },

    // --- Portal (PR-PPC-8..11) ---
    getPortalCapabilities() {
      return atlasFetch('/api/portal/capabilities', { timeoutMs: 15000 });
    },
    listPortalCatalog() {
      return atlasFetch('/api/portal/catalog', { timeoutMs: 15000 });
    },
    browsePortalImport(path) {
      return atlasFetch('/api/portal/import/browse', { method: 'POST', body: JSON.stringify({ path: path || '' }), timeoutMs: 15000 });
    },
    uploadPortalImport(file) {
      const form = new FormData();
      form.append('file', file, file.name);
      return atlasFetch('/api/portal/import/upload', { method: 'POST', body: form, timeoutMs: 180000 });
    },
    listPortalSnapshots(installationId) {
      return atlasFetch(`/api/portal/installations/${encodeURIComponent(installationId)}/snapshots`, { timeoutMs: 15000 });
    },
    repairPortalManifest(packageId, version, contentHash) {
      return atlasFetch(
        `/api/portal/packages/${encodeURIComponent(packageId)}/${encodeURIComponent(version)}/${encodeURIComponent(contentHash)}/repair-manifest`,
        { method: 'POST', timeoutMs: 30000 },
      );
    },
    updatePortalPackageDisplay(packageId, version, contentHash, payload) {
      return atlasFetch(
        `/api/portal/packages/${encodeURIComponent(packageId)}/${encodeURIComponent(version)}/${encodeURIComponent(contentHash)}/display`,
        { method: 'PUT', body: JSON.stringify(payload || {}), timeoutMs: 15000 },
      );
    },
    preflightPortalImport(archivePath) {
      return atlasFetch('/api/portal/import/preflight', { method: 'POST', body: JSON.stringify({ archive_path: archivePath }) });
    },
    importPortalPackage(archivePath) {
      return atlasFetch('/api/portal/import', { method: 'POST', body: JSON.stringify({ archive_path: archivePath }), timeoutMs: 60000 });
    },
    exportPortalPackageUrl(packageId, version, contentHash) {
      return API_BASE + `/api/portal/packages/${encodeURIComponent(packageId)}/${encodeURIComponent(version)}/${encodeURIComponent(contentHash)}/export`;
    },
    uninstallPortalPackage(packageId, version, contentHash) {
      return atlasFetch(`/api/portal/packages/${encodeURIComponent(packageId)}/${encodeURIComponent(version)}/${encodeURIComponent(contentHash)}`, { method: 'DELETE' });
    },
    forkPortalToAtlas(payload) {
      return atlasFetch('/api/portal/fork-to-atlas', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 60000 });
    },
    installPortalPackage(payload) {
      return atlasFetch('/api/portal/install', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 30000 });
    },
    runPortalPackage(payload) {
      return atlasFetch('/api/portal/run', { method: 'POST', body: JSON.stringify(payload || {}), timeoutMs: 60000 });
    },
    stopPortalRun(playSessionId) {
      return atlasFetch(`/api/portal/runs/${encodeURIComponent(playSessionId)}/stop`, { method: 'POST', body: JSON.stringify({}) });
    },
    purgePortalRun(playSessionId) {
      return atlasFetch(`/api/portal/runs/${encodeURIComponent(playSessionId)}/purge`, { method: 'POST', body: JSON.stringify({}) });
    },
    getPortalInstallationData(installationId) {
      return atlasFetch(`/api/portal/installations/${encodeURIComponent(installationId)}/data`, { timeoutMs: 15000 });
    },
    portalInstallationDataBackupUrl(installationId) {
      return API_BASE + `/api/portal/installations/${encodeURIComponent(installationId)}/data/backup`;
    },
    deletePortalInstallationData(installationId, confirmDeleteData) {
      return atlasFetch(`/api/portal/installations/${encodeURIComponent(installationId)}/data`, { method: 'DELETE', body: JSON.stringify({ confirm_delete_data: !!confirmDeleteData }) });
    },
    savePortalRunData(playSessionId) {
      return atlasFetch(`/api/portal/runs/${encodeURIComponent(playSessionId)}/data/save`, { method: 'POST', body: JSON.stringify({}) });
    },
    snapshotPortalRunData(playSessionId, snapshotId) {
      return atlasFetch(`/api/portal/runs/${encodeURIComponent(playSessionId)}/data/snapshot`, { method: 'POST', body: JSON.stringify({ snapshot_id: snapshotId || null }) });
    },
    discardPortalRunData(playSessionId) {
      return atlasFetch(`/api/portal/runs/${encodeURIComponent(playSessionId)}/data/discard`, { method: 'POST', body: JSON.stringify({}) });
    },
    portalRunHeartbeat(playSessionId, reconnectToken) {
      return atlasFetch(`/api/portal/runs/${encodeURIComponent(playSessionId)}/heartbeat`, { method: 'POST', body: JSON.stringify({ reconnect_token: reconnectToken }) });
    },
    portalRunDisconnect(playSessionId, reconnectToken) {
      return atlasFetch(`/api/portal/runs/${encodeURIComponent(playSessionId)}/disconnect`, { method: 'POST', body: JSON.stringify({ reconnect_token: reconnectToken }) });
    },
    portalRunResume(playSessionId, reconnectToken) {
      return atlasFetch(`/api/portal/runs/${encodeURIComponent(playSessionId)}/resume`, { method: 'POST', body: JSON.stringify({ reconnect_token: reconnectToken }) });
    },

  };

  root.AtlasPipelineAPI = AtlasPipelineAPI;
})();
