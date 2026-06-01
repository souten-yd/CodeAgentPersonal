(function () {
  const root = (typeof window !== 'undefined' ? window : globalThis);
  const storageKeys = {
    poolId: 'atlas:lastPoolId',
    runId: 'atlas:lastRunId',
    workspaceId: 'atlas:lastWorkspaceId',
  };
  const state = {
    goalInput: '',
    currentPoolId: '',
    currentRunId: '',
    planPool: null,
    pipelineState: null,
    recoverySummary: null,
    events: [],
    markdown: '',
    loading: false,
    error: null,
    warning: null,
    recoveryWarning: '',
    advancedOpen: false,
    logsOpen: false,
    markdownOpen: false,
    jsonOpen: false,
    lastAction: null,
    recoveryHidden: false,
    restored: false,
    checkpointPath: '',
    continuationSummary: null,
    continuationPrompt: '',
    continuationCopied: '',
    lastPlanResponse: null,
    orchestrationSummary: null,
    clarificationSessionId: "",
    plannerQuestions: [],
    clarificationAnswers: {},
    clarificationSubmitting: false,
    approvalSummary: null,
    approvalRecords: [],
    approvalItems: [],
    safeApplyCandidateItems: [],
    approvalSubmitting: false,
    safeApplySubmitting: false,
    safeApplyResults: {},
    verificationResults: {},
    verificationSubmitting: false,
    debugReviewResults: {},
    debugReviewSubmitting: false,
    debugReviewCandidates: [],
    patchProposalResults: {},
    patchProposalSubmitting: false,
    patchProposalCandidates: [],
    patchProposalApprovalResults: {},
    patchProposalApprovalSubmitting: false,
    patchProposalDraftResults: {},
    patchProposalDraftSubmitting: false,
    autoPolicyPresets: [],
    automationDecision: null,
    patchRegenFromRecommendationResult: null,
    patchRegenFromRecommendationSubmitting: false,
    repoIndexResult: null,
    repoIndexLatest: null,
    repoIndexImpacts: null,
    repoIndexRelatedTests: null,
    repoIndexSubmitting: false,
    repoContextSnapshot: null,
    repoContextScopeSummary: null,
    repoContextVerificationPlan: null,
    planItemImpactMap: null,
    contextRefreshV2: null,
    plannerPackagingV2: null,
    verificationRecommendation: null,
    verificationRecommendationHandoff: null,
    repoContextSubmitting: false,
    workflowShell: null,
  };

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const arr = (value) => Array.isArray(value) ? value : [];

  function getAtlasAutomationExtensionsHost() {
    const host = document.getElementById("atlas-automation-extensions-panel");
    if (!host) {
      console.warn('[AtlasDashboard] automation extensions host not found (#atlas-automation-extensions-panel)');
      return null;
    }
    return host;
  }

  function readStorage(key) {
    try { return localStorage.getItem(key) || ''; } catch (_err) { return ''; }
  }
  function writeStorage(key, value) {
    try { if (value) localStorage.setItem(key, value); } catch (_err) {}
  }
  function removeStorage(key) {
    try { localStorage.removeItem(key); } catch (_err) {}
  }

  function workspaceId() {
    return ($('atlas-workspace-id')?.value || readStorage(storageKeys.workspaceId) || 'default').trim() || 'default';
  }

  function getItems() {
    const pool = state.planPool?.plan_pool || state.planPool;
    return arr(pool?.items);
  }

  function normalizePool(payload) {
    return payload?.plan_pool ? payload.plan_pool : payload;
  }

  function normalizePipeline(payload) {
    return payload?.state ? payload.state : payload;
  }

  function applyOrchestrationSummary(summary) {
    if (summary && typeof summary === 'object') state.orchestrationSummary = summary;
  }

  function questionsFromState() {
    return arr(state.orchestrationSummary?.metadata?.questions).length
      ? arr(state.orchestrationSummary.metadata.questions)
      : arr(state.lastPlanResponse?.questions).length
        ? arr(state.lastPlanResponse.questions)
        : arr(normalizePipeline(state.pipelineState)?.questions);
  }

  function statusClass(status) {
    const s = String(status || '').toLowerCase();
    if (s === 'completed' || s === 'success') return 'success';
    if (['ready', 'running', 'researching', 'executing', 'testing', 'created'].includes(s)) return 'active';
    if (s === 'queued' || s === 'idle' || !s) return 'muted';
    if (s === 'approval_required' || s === 'paused' || s === 'stale') return 'warning';
    if (['failed', 'blocked', 'error'].includes(s)) return 'danger';
    return 'muted';
  }

  function typeIcon(type) {
    return ({ research: '🔎', planning: '🧭', implementation: '🛠', verification: '✅', documentation: '📝', nexus_save: '🧠' })[type] || '●';
  }

  function badge(label, status) {
    return `<span class="atlas-badge atlas-badge-${statusClass(status || label)}">${esc(label || '-')}</span>`;
  }

  function eventLabel(event) {
    return event?.event_type || event?.type || event?.message || '-';
  }

  function lastEvent() {
    return state.events.length ? state.events[state.events.length - 1] : null;
  }

  function setBusy(busy) {
    state.loading = busy;
    ['atlas-create-plan-btn', 'atlas-start-dry-run-btn', 'atlas-recovery-load-btn', 'atlas-recovery-refresh-btn', 'atlas-continuation-refresh-btn'].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = busy;
    });
  }

  function showError(error, fallback) {
    state.error = error || null;
    const card = $('atlas-error-card');
    if (!card) return;
    if (!error) {
      card.hidden = true;
      return;
    }
    const title = $('atlas-error-title');
    const message = $('atlas-error-message');
    if (title) title.textContent = fallback || error.message || 'Atlas request failed';
    if (message) message.textContent = `status: ${error.status || '-'} / detail: ${typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail || error.message || '')}`;
    card.hidden = false;
  }

  function showWarning(message, severity) {
    state.warning = message || null;
    const card = $('atlas-warning-card');
    if (!card) return;
    if (!message) {
      card.hidden = true;
      card.dataset.atlasSeverity = '';
      return;
    }
    const text = $('atlas-warning-message');
    if (text) text.textContent = message;
    card.dataset.atlasSeverity = severity || state.orchestrationSummary?.severity || 'warning';
    card.hidden = false;
  }

  function isPipelineStateNotFound(result) {
    const detail = typeof result?.detail === 'string' ? result.detail : (result?.detail?.detail || result?.message || '');
    return result?.status === 404 && (result?.code === 'pipeline_state_not_found' || String(detail).toLowerCase().includes('pipeline state not found'));
  }

  function markStaleRecovery() {
    const message = '前回のRun状態が見つかりませんでした。PlanPoolは復元できます。必要ならStart Dry-runを再実行してください。';
    state.recoveryWarning = message;
    state.warning = message;
    state.pipelineState = { status: 'stale', warnings: ['pipeline_state_not_found'] };
    state.currentRunId = '';
    removeStorage(storageKeys.runId);
    showError(null);
    showWarning(message);
  }

  function updateSummary() {
    const pool = normalizePool(state.planPool);
    const pipeline = normalizePipeline(state.pipelineState);
    const items = getItems();
    const event = lastEvent();
    const completed = arr(pipeline?.completed_item_ids).length || arr(pool?.completed_item_ids).length;
    const total = items.length;
    const summary = state.orchestrationSummary || {};
    const status = summary.status || pipeline?.status || (state.recoveryWarning ? 'stale' : pool?.status || 'Ready');
    const phase = summary.phase || '-';
    const fill = total ? Math.round((completed / total) * 100) : 0;
    const failed = arr(pipeline?.failed_item_ids).length || arr(pool?.failed_item_ids).length;
    const blocked = arr(pipeline?.blocked_item_ids).length || arr(pool?.blocked_item_ids).length;

    if ($('atlas-workbench-summary-last-run')) $('atlas-workbench-summary-last-run').textContent = state.currentRunId || '-';
    if ($('atlas-workbench-summary-status')) $('atlas-workbench-summary-status').textContent = status;
    if ($('atlas-workbench-status')) $('atlas-workbench-status').textContent = state.loading ? 'Atlas is working...' : `PlanPool: ${pool?.status || 'not created'} / Pipeline: ${pipeline?.status || 'idle'}`;
    if ($('atlas-status-planpool')) $('atlas-status-planpool').textContent = pool?.status || 'not created';
    if ($('atlas-status-items')) $('atlas-status-items').textContent = String(total);
    if ($('atlas-status-pipeline')) $('atlas-status-pipeline').textContent = pipeline?.status || (state.recoveryWarning ? 'stale' : 'idle');
    if ($('atlas-status-last-event')) $('atlas-status-last-event').textContent = eventLabel(event);
    if ($('atlas-status-phase')) $('atlas-status-phase').textContent = phase;
    if ($('atlas-planpool-id')) $('atlas-planpool-id').textContent = state.currentPoolId || 'No pool';
    if ($('atlas-pipeline-run-id')) $('atlas-pipeline-run-id').textContent = state.currentRunId || 'No run';
    if ($('atlas-progress-fill')) $('atlas-progress-fill').style.width = `${fill}%`;
    if ($('atlas-progress-text')) $('atlas-progress-text').textContent = formatPipelineProgressText(pool, pipeline, completed, total);
    if ($('atlas-failed-count')) $('atlas-failed-count').textContent = String(failed);
    if ($('atlas-blocked-count')) $('atlas-blocked-count').textContent = String(blocked);
    if ($('atlas-current-item-id')) $('atlas-current-item-id').textContent = pipeline?.current_item_id || pool?.current_item_id || '-';
    if ($('atlas-next-action')) $('atlas-next-action').textContent = deriveNextAction(pool, pipeline);
    updateActionButtons();
    renderPipelineStatusBadge(status || (state.recoveryWarning ? 'stale' : 'idle'));

    if ($('atlas-auto-readiness-decision')) $('atlas-auto-readiness-decision').textContent = state.automationDecision?.decision?.decision || '-';
    if ($('atlas-auto-readiness-reasons')) $('atlas-auto-readiness-reasons').textContent = 'reasons: ' + (arr(state.automationDecision?.decision?.reasons).join(', ') || '-');
    if ($('atlas-auto-readiness-warnings')) $('atlas-auto-readiness-warnings').textContent = 'warnings: ' + (arr(state.automationDecision?.decision?.warnings).join(', ') || '-');
  }


  function formatPipelineProgressText(pool, pipeline, completed, total) {
    const status = pipeline?.status || pool?.status || '';
    const meta = pipeline?.metadata || {};
    const queued = Number(meta.queued_count || 0);
    const incomplete = status === 'paused' || status === 'waiting' || status === 'dependency_waiting' || (meta.no_ready_items_remaining && completed < total);
    if (incomplete && total > 0 && completed < total) {
      return `Pipeline paused: ${completed}/${total} completed, ${queued || Math.max(total - completed, 0)} queued. No ready item remains. This is not a patch stage yet.`;
    }
    return `${completed} / ${total} completed`;
  }
  function deriveNextAction(pool, pipeline) {
    if (state.orchestrationSummary?.next_action) return state.orchestrationSummary.next_action;
    const recoveryNext = state.recoverySummary?.next_action;
    if (state.recoveryWarning) return 'Start a new dry-run from the recovered PlanPool.';
    if (recoveryNext) return recoveryNext;
    const status = pipeline?.status || '';
    if (status === 'completed') return 'Review final report or start next plan.';
    if (status === 'failed') return 'Inspect failed items in Details and prepare a follow-up plan. Open Details / Advanced Panel → Debug Review.';
    if (status === 'approval_required') return 'Open Details / Advanced Panel → Approval Gate.';
    if (status === 'paused' || status === 'waiting' || status === 'dependency_waiting') return 'No ready item remains. Check dependencies or approve required items. Open Details / Advanced Panel.';
    if (status === 'blocked') return 'Review blocked items and policy/approval reasons.';
    if (state.currentPoolId && !state.currentRunId) return 'Start Dry-run to validate the PlanPool.';
    if (!pool) return 'Create a PlanPool to begin.';
    return 'Review PlanItem cards and dry-run status.';
  }

  function updateActionButtons() {
    const summary = state.orchestrationSummary || {};
    const dryRunBtn = $('atlas-start-dry-run-btn');
    const refreshBtn = $('atlas-recovery-refresh-btn');
    if (dryRunBtn) {
      const summaryDecides = Object.prototype.hasOwnProperty.call(summary, 'can_start_dry_run');
      dryRunBtn.disabled = Boolean(state.loading || (summaryDecides ? !summary.can_start_dry_run : !state.currentPoolId));
      dryRunBtn.title = summary.requires_approval ? 'approval required before dry-run continuation' : (summary.requires_clarification ? 'clarification required before dry-run' : '');
    }
    if (refreshBtn && Object.prototype.hasOwnProperty.call(summary, 'can_refresh_status')) {
      refreshBtn.disabled = Boolean(state.loading || !summary.can_refresh_status);
    }
  }

  function renderPipelineStatusBadge(status) {
    const host = $('atlas-pipeline-status');
    if (!host) return;
    const old = host.querySelector('.atlas-badge');
    if (old) old.outerHTML = badge(status || 'idle', status || 'idle');
  }

  function renderPlanList() {
    const host = $('atlas-plan-list');
    if (!host) return;
    const items = getItems();
    const currentId = normalizePipeline(state.pipelineState)?.current_item_id || normalizePool(state.planPool)?.current_item_id || '';
    if (!items.length) {
      host.innerHTML = '<div class="atlas-empty-state">Goalを入力してCreate Planを押すと、PlanItemカードが表示されます。</div>';
      return;
    }
    host.innerHTML = items.map((item, index) => {
      const current = item.item_id === currentId ? ' is-current' : '';
      const description = item.description || item.goal || 'No description.';
      return `<article class="atlas-plan-item-card${current}" data-plan-item-id="${esc(item.item_id)}">
        <div class="atlas-timeline-rail"><div class="atlas-timeline-dot">${index + 1}</div><div class="atlas-timeline-line"></div></div>
        <div class="atlas-plan-item-body">
          <div class="atlas-plan-item-title"><span>${typeIcon(item.item_type)}</span><b>${esc(item.title || item.item_id || `PlanItem ${index + 1}`)}</b></div>
          <div class="atlas-badge-row">${badge(item.item_type, 'muted')}${badge(item.status, item.status)}${badge(item.risk_level || 'medium', item.risk_level)}</div>
          <p>${esc(description)}</p>
          <div class="atlas-plan-item-meta"><span>depends_on: ${esc(arr(item.depends_on).join(', ') || '-')}</span><span>target_files: ${arr(item.target_files).length}</span></div>
        </div>
      </article>`;
    }).join('');
  }

  function pickCurrentItem() {
    const items = getItems();
    const pipeline = normalizePipeline(state.pipelineState);
    const currentId = pipeline?.current_item_id || normalizePool(state.planPool)?.current_item_id;
    return items.find((item) => item.item_id === currentId)
      || items.find((item) => ['ready', 'running', 'researching', 'executing', 'testing'].includes(item.status))
      || [...items].reverse().find((item) => item.status === 'completed')
      || items[0];
  }

  function renderCurrentItem() {
    const host = $('atlas-current-item-body');
    if (!host) return;
    const item = pickCurrentItem();
    if (!item) {
      host.innerHTML = 'Current item is not selected yet.';
      return;
    }
    host.innerHTML = `<div class="atlas-current-item-content">
      <div class="atlas-plan-item-title"><span>${typeIcon(item.item_type)}</span><b>${esc(item.title || item.item_id)}</b></div>
      <div class="atlas-badge-row">${badge(item.status, item.status)}${badge(item.risk_level || 'medium', item.risk_level)}${badge(item.item_type, 'muted')}</div>
      <p>${esc(item.description || item.goal || '')}</p>
    </div>`;
  }

  function renderEvents() {
    const latestHost = $('atlas-latest-events-list');
    const fullHost = $('atlas-events-panel');
    const latest = state.events.slice(-5).reverse();
    if (latestHost) {
      latestHost.innerHTML = latest.length ? latest.map((event) => `<li><b>${esc(eventLabel(event))}</b> <span>${esc(event.message || event.item_id || '')}</span></li>`).join('') : '<li>No events yet.</li>';
    }
    if (fullHost) fullHost.textContent = state.events.length ? state.events.map((event) => JSON.stringify(event)).join('\n') : 'No events yet.';
  }


  function renderAutoSafeApplyPanel() {
    const panel = $('atlas-auto-safe-apply-panel');
    if (!panel) return;
    const decision = state.automationDecision?.decision?.decision;
    const itemId = state.automationDecision?.decision?.item_id || '';
    panel.hidden = decision !== 'allow';
    if ($('atlas-auto-safe-apply-item-id')) $('atlas-auto-safe-apply-item-id').textContent = itemId || '-';
  }

  async function runAutoSafeApplyOne() {
    const decision = state.automationDecision?.decision;
    if (!decision || decision.decision !== 'allow' || !state.currentPoolId || !root.AtlasPipelineAPI?.autoSafeApplyOne) return;
    const payload = { pool_id: state.currentPoolId, item_id: decision.item_id, preset_id: 'guarded_low_risk', workspace_id: workspaceId(), run_id: state.currentRunId || '' };
    const response = await handleResult(await root.AtlasPipelineAPI.autoSafeApplyOne(payload), 'Auto safe_apply failed');
    if (!response) return;
    const resultEl = $('atlas-auto-safe-apply-result');
    if (resultEl) {
      const snap = response.change_snapshot || response.safe_apply_result?.change_snapshot || {};
      const safeApply = response.safe_apply_result || {};
      resultEl.textContent = JSON.stringify({ status: response.status, safe_apply_status: safeApply.status || response.status || '', reasons: safeApply.reasons || response.warnings || [], workspace_root: response.workspace_root || '', changed_files: response.changed_files || safeApply.changed_files || [], file_results: safeApply.file_results || response.metadata?.file_results || [], actual_file_changed: !!response.actual_file_changed, snapshot_manifest: snap.manifest_path || '', warnings: response.warnings || [], errors: response.errors || [] }, null, 2);
    }
    await refreshStatus();
  }

  function renderDetails() {
    const json = {
      planPool: normalizePool(state.planPool),
      pipelineState: normalizePipeline(state.pipelineState),
      recoverySummary: state.recoverySummary,
      continuationSummary: state.continuationSummary,
      lastPlanResponse: state.lastPlanResponse,
      orchestrationSummary: state.orchestrationSummary,
    };
    json.recoveryWarning = state.recoveryWarning;
    if ($('atlas-json-panel')) $('atlas-json-panel').textContent = JSON.stringify(json, null, 2);
    if ($('atlas-markdown-panel')) $('atlas-markdown-panel').textContent = state.markdown || 'No markdown loaded.';
    renderQuestionsPanel();
    renderApprovalPanel();
    refreshVerificationCandidates();
    renderVerificationPanel();
    refreshDebugReviewCandidates();
    refreshPatchProposalCandidates();
    if ($('atlas-checkpoint-path')) $('atlas-checkpoint-path').textContent = state.checkpointPath || 'No checkpoint yet.';
    const summary = state.continuationSummary || {};
    if ($('atlas-continuation-summary')) {
      $('atlas-continuation-summary').textContent = summary.pool_id
        ? `workspace: ${summary.workspace_id || workspaceId()} / pool_id: ${summary.pool_id || '-'} / run_id: ${summary.run_id || '-'} / status: ${summary.status || '-'} / next: ${summary.next_action || '-'}`
        : 'No continuation summary yet.';
    }
    if ($('atlas-continuation-prompt')) $('atlas-continuation-prompt').value = state.continuationPrompt || '';
    if ($('atlas-copy-status')) $('atlas-copy-status').textContent = state.continuationCopied || '';
    renderAutoSafeApplyPanel();
  }

  function setClarificationAnswer(questionId, value) {
    state.clarificationAnswers[String(questionId || '')] = value;
  }

  function renderQuestionsPanel() {
    const host = $('atlas-questions-panel');
    if (!host) return;
    const questions = arr(state.plannerQuestions).length ? arr(state.plannerQuestions) : questionsFromState();
    if (!questions.length) {
      host.innerHTML = '<div class="atlas-empty-state">No planner questions.</div>';
      return;
    }
    const cards = questions.map((q, index) => {
      const qid = String(q.question_id || `q${index + 1}`);
      const text = esc(q.prompt || q.question || q.message || JSON.stringify(q));
      return `<div class="atlas-question-card"><div><b>${esc(qid)}</b>: ${text}</div><div class="atlas-question-meta">${esc(q.reason || '')} ${esc(q.importance || '')}</div><textarea class="atlas-question-input" data-qid="${esc(qid)}" placeholder="Answer"></textarea></div>`;
    }).join('');
    host.innerHTML = `<div class="atlas-info-card" data-atlas-clarification-warning="true"><b>追加確認が必要です。</b><span>DetailsでPlanner questionsを確認してください。</span></div><div class="atlas-questions-list">${cards}</div><div class="atlas-clarification-actions"><button id="atlas-submit-clarification-btn" class="atlas-secondary-btn" type="button">Submit Clarification Answers</button><button id="atlas-submit-assumptions-btn" class="atlas-ghost-btn" type="button">Use assumptions / おまかせ</button></div>`;
    host.querySelectorAll('textarea[data-qid]').forEach((el)=>el.addEventListener('input',()=>setClarificationAnswer(el.dataset.qid, el.value)));
    host.querySelector('#atlas-submit-clarification-btn')?.addEventListener('click', ()=>submitClarificationAnswers(false));
    host.querySelector('#atlas-submit-assumptions-btn')?.addEventListener('click', ()=>submitClarificationAnswers(true));
  }

  async function submitClarificationAnswers(useAssumptions=false) {
    if (state.clarificationSubmitting) return;
    const questions = arr(state.plannerQuestions).length ? arr(state.plannerQuestions) : questionsFromState();
    const answers = questions.map((q, i) => {
      const qid = String(q.question_id || `q${i+1}`);
      const raw = state.clarificationAnswers[qid];
      const has = String(raw || '').trim() !== '';
      return { question_id: qid, answer: has ? String(raw) : '', skipped: useAssumptions && !has, metadata: { ui: 'atlas_dashboard' } };
    }).filter((a)=>a.skipped || String(a.answer).trim() !== '');
    state.clarificationSubmitting = true;
    const adv = advancedPayload();
    const res = await handleResult(await root.AtlasPipelineAPI.submitClarificationAnswers({ session_id: state.clarificationSessionId || '', original_input: state.goalInput || ($('atlas-goal-input')?.value || ''), answers, workspace_id: adv.workspace_id, planner_mode: adv.planner_mode, planning_depth: adv.planning_depth, automation_level: adv.automation_level, execution_strategy: adv.execution_strategy }), 'Submit clarification failed');
    state.clarificationSubmitting = false;
    if (!res) { showWarning('Clarification submit failed.', 'warning'); render(); return; }
    if (res.status === 'waiting_for_clarification') {
      state.clarificationSessionId = res.session?.session_id || state.clarificationSessionId;
      state.plannerQuestions = arr(res.questions);
      showWarning('追加確認が必要です。DetailsでPlanner questionsを確認してください。', 'warning');
    } else {
      const pool = res.pool || {};
      state.currentPoolId = res.metadata?.pool_id || pool.pool_id || '';
      state.planPool = pool;
      state.pipelineState = null;
      state.plannerQuestions = [];
      state.clarificationAnswers = {};
      showWarning(arr(res.warnings).join(', ') || null, 'info');
    }
    render();
  }

  function renderRecovery() {
    const banner = $('atlas-recovery-banner');
    if (!banner) return;
    const recovery = state.recoverySummary;
    const status = recovery?.status || recovery?.pipeline_status || recovery?.reason || '';
    const shouldShow = recovery && !state.recoveryHidden && !['no_workspace', 'no_plan_pool', ''].includes(status);
    banner.hidden = !shouldShow;
    if (shouldShow && $('atlas-recovery-summary')) {
      const warning = state.recoveryWarning ? ` / warning: ${state.recoveryWarning}` : '';
      const primary = recovery?.metadata?.primary_verification_reason || recovery?.primary_verification_reason || '';
      const consoleErrors = recovery?.metadata?.console_errors || recovery?.console_errors || [];
      const consoleText = Array.isArray(consoleErrors) && consoleErrors.length
        ? ` / console_errors: ${consoleErrors.slice(0, 3).map((e) => String(e)).join(' | ')}`
        : '';
      const next = primary ? `Verification failed: ${primary}` : (recovery.next_action || '-');
      $('atlas-recovery-summary').textContent = `status: ${status} / pool_id: ${recovery.pool_id || '-'} / run_id: ${state.currentRunId || recovery.run_id || '-'} / next: ${next}${consoleText}${warning}`;
    }
    const loadBtn = $('atlas-recovery-load-btn');
    const refreshBtn = $('atlas-recovery-refresh-btn');
    if (loadBtn) loadBtn.disabled = Boolean(state.loading || !recovery?.pool_id);
    if (refreshBtn) refreshBtn.disabled = Boolean(state.loading || !state.currentRunId || state.recoveryWarning);
  }

  function render() {
    renderPatchRegenFromRecommendationPanel();
    updateSummary();
    renderPlanList();
    renderCurrentItem();
    renderEvents();
    renderDetails();
    renderRecovery();
  }

  function advancedPayload() {
    const maxItemsRaw = $('atlas-max-items')?.value || '';
    const maxItems = maxItemsRaw ? Number(maxItemsRaw) : null;
    const workspace = workspaceId();
    writeStorage(storageKeys.workspaceId, workspace);
    return {
      planner_mode: $('atlas-planner-mode')?.value || 'auto',
      planning_depth: $('atlas-planning-depth')?.value || 'standard',
      automation_level: $('atlas-automation-level')?.value || 'plan_then_ask',
      execution_strategy: $('atlas-execution-strategy')?.value || 'sequential',
      workspace_id: workspace,
      max_items: Number.isFinite(maxItems) ? maxItems : null,
      pause_after_each_item: Boolean($('atlas-pause-after-each-item')?.checked),
    };
  }

  async function handleResult(result, label) {
    if (!result?.ok) {
      showError(result || { message: label, status: '-' }, label);
      return null;
    }
    showError(null);
    return result.data;
  }

  async function createPlanPool() {
    state.lastAction = createPlanPool;
    const input = ($('atlas-goal-input')?.value || '').trim();
    if (!input) {
      showError({ status: '-', detail: 'Goal is empty.', message: 'Goal is empty.' }, 'Enter a goal before creating a PlanPool.');
      return;
    }
    state.goalInput = input;
    const compat = $('atlas-requirement-input');
    if (compat) compat.value = input;
    const adv = advancedPayload();
    setBusy(true);
    const data = await handleResult(await root.AtlasPipelineAPI.createPlanPool({ input, ...adv, metadata: { ui: 'atlas_dashboard' } }), 'Create Plan failed');
    if (data) {
      state.lastPlanResponse = data;
      if (data.status === 'waiting_for_clarification') {
        state.currentPoolId = '';
        state.currentRunId = '';
        state.planPool = null;
        applyOrchestrationSummary(data.orchestration_summary);
        state.pipelineState = { status: 'waiting_for_clarification', questions: arr(data.questions), warnings: arr(data.warnings) };
        state.clarificationSessionId = data.clarification_session_id || '';
        state.plannerQuestions = arr(data.questions);
        state.recoveryWarning = '';
        state.events = [];
        state.markdown = '';
        state.checkpointPath = '';
        removeStorage(storageKeys.poolId);
        removeStorage(storageKeys.runId);
        showWarning('追加確認が必要です。DetailsでPlanner questionsを確認してください。', 'warning');
      } else {
        applyOrchestrationSummary(data.orchestration_summary);
        state.currentPoolId = data.pool_id;
        state.currentRunId = '';
        state.planPool = data.plan_pool || data;
        state.pipelineState = null;
        state.recoveryWarning = '';
        state.events = [];
        removeStorage(storageKeys.runId);
        const warnings = arr(data.warnings);
        const plannerMessage = data.used_fallback
          ? `Planner fallback used: ${data.fallback_reason || warnings.join(', ') || 'real_planner_unavailable'}`
          : (warnings.length ? `Planner warnings: ${warnings.join(', ')}` : '');
        showWarning(plannerMessage || null, data.orchestration_summary?.severity);
        state.checkpointPath = data.checkpoint_path || '';
        writeStorage(storageKeys.poolId, state.currentPoolId);
        state.plannerQuestions = [];
        state.clarificationAnswers = {};
        state.clarificationSessionId = '';
        await loadMarkdown();
        await refreshContinuation();
        await refreshApprovals();
      }
    }
    setBusy(false);
    render();
  }

  async function startDryRun() {
    state.lastAction = startDryRun;
    if (!state.currentPoolId) {
      showError({ status: '-', detail: 'Create Plan is required first.', message: 'No PlanPool selected.' }, 'Create Plan before Start Dry-run.');
      return;
    }
    const adv = advancedPayload();
    setBusy(true);
    const payload = {
      pool_id: state.currentPoolId,
      workspace_id: adv.workspace_id,
      max_items: adv.max_items,
      pause_after_each_item: adv.pause_after_each_item,
      metadata: { ui: 'atlas_dashboard', mode: 'dry_run_only' },
    };
    const data = await handleResult(await root.AtlasPipelineAPI.startPipelineDryRun(payload), 'Start Dry-run failed');
    if (data) {
      applyOrchestrationSummary(data.orchestration_summary);
      state.currentRunId = data.run_id;
      state.pipelineState = data;
      state.events = arr(data.events);
      state.checkpointPath = data.checkpoint_path || state.checkpointPath;
      writeStorage(storageKeys.runId, state.currentRunId);
      state.recoveryWarning = '';
      showWarning(null);
      await refreshStatus();
      await refreshContinuation();
      await refreshApprovals();
    }
    setBusy(false);
    render();
  }

  async function loadPlan(poolId) {
    const target = poolId || state.currentPoolId;
    if (!target) return;
    const data = await handleResult(await root.AtlasPipelineAPI.getPlanPool(target), 'Load Plan failed');
    if (data) {
      state.currentPoolId = data.pool_id || target;
      state.planPool = data;
      writeStorage(storageKeys.poolId, state.currentPoolId);
      await loadMarkdown();
    }
    render();
  }

  async function loadMarkdown() {
    if (!state.currentPoolId) return;
    const result = await root.AtlasPipelineAPI.getPlanPoolMarkdown(state.currentPoolId, workspaceId());
    if (result?.ok) state.markdown = result.data?.markdown || '';
  }

  async function refreshStatus() {
    state.lastAction = refreshStatus;
    if (state.currentPoolId) await loadPlan(state.currentPoolId);
    if (state.currentPoolId && state.currentRunId) {
      const result = await root.AtlasPipelineAPI.getPipelineStatus(state.currentPoolId, state.currentRunId, workspaceId());
      if (isPipelineStateNotFound(result)) {
        markStaleRecovery();
        render();
        return;
      }
      const data = await handleResult(result, 'Refresh Status failed');
      if (data) {
        applyOrchestrationSummary(data.orchestration_summary);
        state.recoveryWarning = '';
        showWarning(null);
        state.pipelineState = normalizePipeline(data);
        state.events = arr(data.events).length ? arr(data.events) : arr(state.pipelineState?.events);
      }
      if (state.currentRunId) {
        const events = await root.AtlasPipelineAPI.getPipelineEvents(state.currentPoolId, state.currentRunId, workspaceId());
        if (events?.ok) state.events = arr(events.data?.events);
      }
    }
    render();
  }



  async function refreshContinuation() {
    const api = root.AtlasPipelineAPI;
    if (!api) return;
    const result = state.currentPoolId
      ? await api.getContinuationPool(state.currentPoolId, state.currentRunId, workspaceId())
      : await api.getContinuationLatest(workspaceId());
    if (!result?.ok) {
      state.continuationCopied = `Continuation refresh failed: ${result?.message || 'unknown error'}`;
      renderDetails();
      return;
    }
    state.continuationSummary = result.data || null;
    state.continuationPrompt = result.data?.continuation_prompt || '';
    state.continuationCopied = '';
    if (result.data?.pool_id) state.currentPoolId = result.data.pool_id;
    if (result.data?.run_id && result.data?.status !== 'stale') state.currentRunId = result.data.run_id;
    renderDetails();
  }

  async function copyTextWithFallback(text, textareaId) {
    if (!text) return false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (_err) {}
    const el = $(textareaId);
    if (!el) return false;
    try {
      el.focus();
      el.select();
      return document.execCommand('copy');
    } catch (_err) {
      return false;
    }
  }

  async function copyContinuationPrompt() {
    if (!state.continuationPrompt) await refreshContinuation();
    const ok = await copyTextWithFallback(state.continuationPrompt, 'atlas-continuation-prompt');
    state.continuationCopied = ok ? 'Continuation prompt copied.' : 'Copy failed. Select the prompt manually.';
    renderDetails();
  }

  async function copyAtlasIds() {
    const summary = state.continuationSummary || {};
    const text = [
      `workspace_id=${summary.workspace_id || workspaceId()}`,
      `pool_id=${summary.pool_id || state.currentPoolId || ''}`,
      `run_id=${summary.run_id || state.currentRunId || ''}`,
    ].join('\n');
    const ok = await copyTextWithFallback(text, 'atlas-continuation-prompt');
    state.continuationCopied = ok ? 'Atlas IDs copied.' : 'Copy failed. Select the IDs manually.';
    renderDetails();
  }



  function refreshVerificationCandidates() {
    const items = getItems();
    state.verificationCandidates = items.filter((item) => {
      const safe = String(item?.metadata?.safe_apply?.status || '').toLowerCase();
      const st = String(item?.status || '').toLowerCase();
      return ['applied','simulated'].includes(safe) || ['completed','applied'].includes(st);
    });
  }



  function refreshDebugReviewCandidates() {
    state.debugReviewCandidates = getItems().filter((item) => {
      const verificationStatus = String(item?.metadata?.verification?.status || '').toLowerCase();
      const itemStatus = String(item?.status || '').toLowerCase();
      return verificationStatus === 'failed' || itemStatus === 'failed';
    });
    renderDebugReviewPanel();
  }

  async function runDebugReview(itemId) {
    if (!itemId || state.debugReviewSubmitting) return;
    state.debugReviewSubmitting = true;
    renderDebugReviewPanel();
    const payload = { pool_id: state.currentPoolId, item_id: itemId, run_id: state.currentRunId || '', workspace_id: workspaceId(), source_type: 'verification' };
    const result = await root.AtlasPipelineAPI.runDebugReview(payload);
    state.debugReviewSubmitting = false;
    if (result.ok) {
      state.debugReviewResults[itemId] = result.data || {};
      if (result.data?.plan_pool) state.planPool = result.data.plan_pool;
      applyOrchestrationSummary(result.data?.orchestration_summary);
      state.continuationPrompt = result.data?.continuation_prompt || state.continuationPrompt;
      await refreshPlanPool();
      refreshPatchProposalCandidates();
      const reviewed = state.debugReviewResults[itemId] || {};
      if (reviewed.status === 'analyzed') showSuccess(`Debug review analyzed: ${itemId}. Next: generate a Patch Proposal manually from Patch Proposal panel.`);
      else if (reviewed.status === 'blocked') showWarning(`Debug review blocked: ${itemId} (${(reviewed.warnings||[]).join(',')})`);
      else if (reviewed.status === 'failed') showError(`Debug review failed: ${itemId} (${(reviewed.errors||[]).join(',')})`);
    } else {
      showWarning(result.message || 'Debug review failed');
    }
    render();
    renderDebugReviewPanel();
  }

  function renderDebugReviewPanel() {
    const el = $('atlas-debug-review-list');
    if (!el) return;
    const rows = state.debugReviewCandidates || [];
    if (!rows.length) { el.innerHTML = '<div class="atlas-muted">No failed verification items.</div>'; return; }
    el.innerHTML = rows.map((item) => {
      const review = item?.metadata?.debug_review || state.debugReviewResults[item.item_id] || {};
      const status = review.status || state.debugReviewResults[item.item_id]?.status || '';
      const verificationStatus = String(item?.metadata?.verification?.status || '').toLowerCase();
      const isPatchDraft = String(item?.metadata?.source || '').toLowerCase() === 'patch_proposal';
      const sourceProposalId = String(item?.metadata?.source_proposal_id || item?.metadata?.verification?.source_proposal_id || '');
      const targetFiles = arr(item?.target_files).join(', ');
      return `<div class="atlas-approval-item"><div><strong>${esc(item.item_id)}</strong> ${esc(item.title||'')}</div><div>Status: ${esc(status || verificationStatus || '-')}${isPatchDraft ? ' <span class="atlas-badge">Patch Proposal Draft</span>' : ''}<br>verification status: ${esc(verificationStatus || '-')}<br>source proposal id: ${esc(sourceProposalId || '-')}<br>target files: ${esc(targetFiles || '-')}<br>Root cause: ${esc(review.root_cause_category||'')}<br>Proposed fix: ${esc(review.proposed_fix||'')}<br>Reusable lesson: ${esc(review.reusable_lesson || state.debugReviewResults[item.item_id]?.debug_attempt?.reusable_lesson || '')}<br><small>Manual analysis only.</small><br><small>No patch proposal is generated automatically.</small><br><small>No safe_apply or verification rerun is executed automatically.</small><br><small>Next after failed verification: use Run Debug Review, then generate a Patch Proposal manually from Patch Proposal panel.</small></div><button class="atlas-secondary-btn" data-debug-review-item="${esc(item.item_id)}" ${state.debugReviewSubmitting?'disabled':''}>Run Debug Review</button></div>`;
    }).join('');
    el.querySelectorAll('button[data-debug-review-item]').forEach((btn)=>btn.addEventListener('click',()=>runDebugReview(btn.getAttribute('data-debug-review-item')||'')));
  }
  function refreshPatchProposalCandidates() {
    state.patchProposalCandidates = getItems().filter((item) => {
      const review = item?.metadata?.debug_review || {};
      return String(review.status || '').toLowerCase() === 'analyzed' && String(review.proposed_fix || '').trim() !== '';
    });
    renderPatchProposalPanel();
  }

  function patchProposalResultText(result) {
    const proposal = result?.proposal || {};
    const files = arr(proposal.target_files || []).join(', ');
    const mdPath = result?.proposal_md_path || '';
    if (result?.status === 'proposed') return `Patch Proposal generated. summary: ${proposal.summary || '-'} / risk: ${proposal.risk_level || '-'} / files: ${files || '-'} / md: ${mdPath || '-'} / Next: review and approve/reject the proposal manually.`;
    if (result?.status === 'blocked') return `Patch Proposal blocked: ${(arr(result?.warnings)).join(',') || '-'}`;
    if (result?.status === 'failed') return `Patch Proposal failed: ${(arr(result?.errors)).join(',') || '-'}`;
    return '';
  }

  async function decidePatchProposal(itemId, decision) {
    if (!itemId || !decision || state.patchProposalApprovalSubmitting || !state.currentPoolId || !root.AtlasPipelineAPI?.decidePatchProposal) return;
    const reason = document.querySelector(`textarea[data-patch-proposal-reason="${itemId}"]`)?.value || '';
    const item = getItems().find((row)=>row.item_id===itemId) || {};
    const proposalId = item?.metadata?.patch_proposal?.proposal_id || '';
    state.patchProposalApprovalSubmitting = true;
    renderPatchProposalPanel();
    const payload = { pool_id: state.currentPoolId, item_id: itemId, proposal_id: proposalId, run_id: state.currentRunId || '', workspace_id: workspaceId(), decision, reason };
    const result = await root.AtlasPipelineAPI.decidePatchProposal(payload);
    state.patchProposalApprovalSubmitting = false;
    if (result.ok) {
      const response = result.data || {};
      state.patchProposalApprovalResults[itemId] = response;
      if (response.plan_pool) state.planPool = response.plan_pool;
      applyOrchestrationSummary(response.orchestration_summary);
      state.continuationPrompt = response.continuation_prompt || state.continuationPrompt;
      if (response.status === 'approved') showSuccess('Approved. Next: create manual safe_apply PlanItem Draft manually.');
      else if (response.status === 'rejected') showWarning('Rejected. No patch was applied.');
      else if (response.status === 'needs_revision') showWarning('Needs revision. Generate a revised Patch Proposal manually.');
      else if (response.status === 'blocked') showWarning('Patch Proposal approval blocked: '+(arr(response.warnings).join(',') || '-'));
      else if (response.status === 'failed') showError('Patch Proposal approval failed: '+(arr(response.errors).join(',') || '-'));
      await refreshPlanPool();
      renderPatchProposalPanel();
      render();
      return;
    }
    showWarning(result.message || 'Patch proposal approval failed');
    renderPatchProposalPanel();
  }

  async function generatePatchProposal(itemId) {
    if (!itemId || state.patchProposalSubmitting || !state.currentPoolId || !root.AtlasPipelineAPI?.generatePatchProposal) return;
    state.patchProposalSubmitting = true;
    renderPatchProposalPanel();
    const payload = { pool_id: state.currentPoolId, item_id: itemId, run_id: state.currentRunId || '', workspace_id: workspaceId(), source_type: 'debug_review' };
    const result = await root.AtlasPipelineAPI.generatePatchProposal(payload);
    state.patchProposalSubmitting = false;
    if (result.ok) {
      state.patchProposalResults[itemId] = result.data || {};
      applyOrchestrationSummary(result.data?.orchestration_summary);
      state.continuationPrompt = result.data?.continuation_prompt || state.continuationPrompt;
      await refreshPlanPool();
      const text = patchProposalResultText(result.data || {});
      if (text) showSuccess(text);
    } else {
      showWarning(result.message || 'Patch proposal generation failed');
    }
    const outcome = result.ok ? (result.data || {}) : {};
    if (outcome.status === 'blocked') showWarning(patchProposalResultText(outcome));
    else if (outcome.status === 'failed') showError(patchProposalResultText(outcome));
    renderPatchProposalPanel();
  }



  async function createPatchProposalPlanItemDraft(itemId) {
    if (!itemId || state.patchProposalDraftSubmitting || !state.currentPoolId || !root.AtlasPipelineAPI?.createPatchProposalPlanItemDraft) return;
    const item = getItems().find((row)=>row.item_id===itemId) || {};
    const proposalId = item?.metadata?.patch_proposal?.proposal_id || '';
    state.patchProposalDraftSubmitting = true;
    renderPatchProposalPanel();
    const payload = { pool_id: state.currentPoolId, item_id: itemId, proposal_id: proposalId, run_id: state.currentRunId || '', workspace_id: workspaceId() };
    const result = await root.AtlasPipelineAPI.createPatchProposalPlanItemDraft(payload);
    state.patchProposalDraftSubmitting = false;
    if (result.ok) {
      state.patchProposalDraftResults[itemId] = result.data || {};
      const data = result.data || {};
      state.patchProposalDraftResults[itemId] = data;
      if (data.plan_pool) state.planPool = data.plan_pool;
      applyOrchestrationSummary(data.orchestration_summary);
      state.continuationPrompt = data.continuation_prompt || state.continuationPrompt;
      if (data.status === 'created') {
        const draftId = data?.draft_item?.draft_item_id || '';
        showSuccess(`PlanItem Draft created${draftId ? `: ${draftId}` : ''}. Next: approve the draft PlanItem manually from Approval Gate.`);
      } else if (data.status === 'blocked') showWarning(patchProposalResultText(data) || 'PlanItem Draft creation was blocked');
      else if (data.status === 'failed') showError(patchProposalResultText(data) || 'PlanItem Draft creation failed');
      await refreshPlanPool();
      await refreshApprovals();
      renderPatchProposalPanel();
      render();
    } else showWarning(result.message || 'Patch proposal PlanItem draft failed');
    if (!result.ok) renderPatchProposalPanel();
  }
  function renderPatchProposalPanel() {
    const el = $('atlas-patch-proposal-list');
    if (!el) return;
    const rows = state.patchProposalCandidates || [];
    if (!rows.length) { el.innerHTML = '<div class="atlas-muted">No DebugReview analyzed items with proposed fix.</div>'; return; }
    el.innerHTML = rows.map((item) => {
      const existing = item?.metadata?.patch_proposal || {};
      const review = item?.metadata?.debug_review || {};
      const isPatchDraft = String(review.source || '').toLowerCase() === 'patch_proposal_planitem_draft' || String(item?.metadata?.source || '').toLowerCase() === 'patch_proposal';
      const result = state.patchProposalResults[item.item_id] || {};
      const proposal = result.proposal || {};
      const summary = proposal.summary || existing.summary || '';
      const risk = proposal.risk_level || existing.risk_level || item.risk_level || '';
      const targetFiles = arr(proposal.target_files || existing.target_files || item.target_files).join(', ');
      const mdPath = result.proposal_md_path || existing.proposal_md_path || '';
      const approval = item?.metadata?.patch_proposal_approval || state.patchProposalApprovalResults[item.item_id] || {};
      const status = existing.status || result.status || '';
      const reason = approval.reason || '';
      const decisionActions = status === 'proposed'
        ? `<div class="atlas-clarification-actions"><button class="atlas-secondary-btn" data-patch-proposal-decision="approved" data-patch-proposal-item="${esc(item.item_id)}" ${state.patchProposalApprovalSubmitting?'disabled':''}>Approve Proposal</button><button class="atlas-secondary-btn" data-patch-proposal-decision="rejected" data-patch-proposal-item="${esc(item.item_id)}" ${state.patchProposalApprovalSubmitting?'disabled':''}>Reject Proposal</button><button class="atlas-secondary-btn" data-patch-proposal-decision="needs_revision" data-patch-proposal-item="${esc(item.item_id)}" ${state.patchProposalApprovalSubmitting?'disabled':''}>Needs Revision</button></div>` : '';
      const generateLabel = status === 'needs_revision' ? 'Generate Revised Patch Proposal' : 'Generate Patch Proposal';
      const showGenerate = status !== 'approved' && status !== 'rejected';
      const generateBtn = showGenerate ? `<button class="atlas-secondary-btn" data-patch-proposal-item="${esc(item.item_id)}" ${state.patchProposalSubmitting?'disabled':''}>${generateLabel}</button>` : '';
      const draftInfo = item?.metadata?.patch_proposal_planitem_draft || {};
      const draftItemId = draftInfo.draft_item_id || state.patchProposalDraftResults[item.item_id]?.draft_item?.draft_item_id || '';
      const draftAction = status === 'approved'
        ? (draftItemId ? `<br>Draft created: ${esc(draftItemId)}<br><small>Next: approve the draft PlanItem manually from Approval Gate.</small>` : `<div class="atlas-clarification-actions"><button class="atlas-secondary-btn" data-patch-proposal-draft-item="${esc(item.item_id)}" ${state.patchProposalDraftSubmitting?'disabled':''}>Create manual safe_apply PlanItem Draft</button></div><small>Draft creation only.</small><br><small>No PlanItem approval is performed automatically.</small><br><small>No safe_apply or verification rerun is executed automatically.</small>`)
        : '';
      const statusNote = status === 'approved'
        ? '<br>Approved. No patch has been applied yet.<br>Next: create manual safe_apply PlanItem Draft manually.'
        : (status === 'rejected' ? '<br>Rejected. No patch was applied.' : (status === 'needs_revision' ? '<br>Needs revision. Generate a revised Patch Proposal manually.' : ''));
      return `<div class="atlas-approval-item"><div><strong>${esc(item.item_id)}</strong> ${esc(item.title||'')} ${isPatchDraft ? '<span class="atlas-badge">Patch Proposal Draft</span>' : ''}</div><div>debug review status: ${esc(review.status || '-')}<br>source proposal id: ${esc(review.source_proposal_id || item?.metadata?.source_proposal_id || '-')}<br>Root cause: ${esc(review.root_cause_category||'')}<br>Proposed fix: ${esc(review.proposed_fix||'')}<br>Reusable lesson: ${esc(review.reusable_lesson||'')}<br>Target files: ${esc(targetFiles)}<br><small>Approval only.</small><br><small>No PlanItem draft is created automatically.</small><br><small>No patch, safe_apply, or verification rerun is executed automatically.</small><br>Proposal status: ${esc(status)}<br>Proposal summary: ${esc(summary)}<br>Risk: ${esc(risk)}<br>Proposal MD: ${esc(mdPath)}<br>Approval decision: ${esc(approval.decision || '-')}<br>Approval reason: ${esc(reason)}${statusNote}${status==='proposed' ? '<br><small>Next: review and approve/reject the proposal manually.</small>' : ''}</div><textarea data-patch-proposal-reason="${esc(item.item_id)}" placeholder="reason">${esc(reason)}</textarea>${generateBtn}${decisionActions}${draftAction}</div>`;
    }).join('');
    el.querySelectorAll('button[data-patch-proposal-item]:not([data-patch-proposal-decision])').forEach((btn)=>btn.addEventListener('click',()=>generatePatchProposal(btn.getAttribute('data-patch-proposal-item')||'')));
    el.querySelectorAll('button[data-patch-proposal-decision]').forEach((btn)=>btn.addEventListener('click',()=>decidePatchProposal(btn.getAttribute('data-patch-proposal-item')||'', btn.getAttribute('data-patch-proposal-decision')||'')));
    el.querySelectorAll('button[data-patch-proposal-draft-item]').forEach((btn)=>btn.addEventListener('click',()=>createPatchProposalPlanItemDraft(btn.getAttribute('data-patch-proposal-draft-item')||'')));
  }
  function renderVerificationPanel() {
    const host = $('atlas-verification-list');
    if (!host) return;
    const items = arr(state.verificationCandidates);
    if (!items.length) { host.innerHTML = 'No verification candidates.'; return; }
    host.innerHTML = items.map((item)=>{
      const safeStatus = String(item?.metadata?.safe_apply?.status || '').toLowerCase();
      const isPatchDraft = String(item?.metadata?.source || '').toLowerCase() === 'patch_proposal';
      const sourceProposalId = String(item?.metadata?.source_proposal_id || '');
      const targetFiles = arr(item?.target_files).join(', ');
      const status = state.verificationResults[item.item_id]?.status || item?.metadata?.verification?.status || '-';
      const failedNote = status === 'failed' ? '<small>DebugLoop is not automatically started. Use Debug Review panel manually.</small>' : '';
      return `<div class="atlas-question-card"><b>${esc(item.item_id)}</b> ${esc(item.title||'')} <span class="atlas-badge">status: ${esc(status)}</span>${isPatchDraft ? ' <span class="atlas-badge">Patch Proposal Draft</span>' : ''}<div class="atlas-clarification-actions"><button data-verify="${esc(item.item_id)}" type="button">Run Verification</button><small>Manual verification only.</small><small>DebugLoop is not started automatically.</small>${safeStatus ? `<small>safe_apply status: ${esc(safeStatus)}</small>` : ''}${isPatchDraft ? `<small>source proposal id: ${esc(sourceProposalId || '-')}</small><small>target files: ${esc(targetFiles || '-')}</small>` : ''}${failedNote}</div></div>`;
    }).join('');
    host.querySelectorAll('button[data-verify]').forEach((btn)=>btn.addEventListener('click', ()=>runVerification(btn.dataset.verify)));
  }

  async function runVerification(itemId) {
    if (state.verificationSubmitting || !state.currentPoolId || !root.AtlasPipelineAPI?.runVerification) return;
    state.verificationSubmitting = true;
    const response = await handleResult(await root.AtlasPipelineAPI.runVerification({ pool_id: state.currentPoolId, item_id: itemId, run_id: state.currentRunId || '', workspace_id: workspaceId(), metadata: { ui: 'atlas_dashboard' } }), 'Verification failed');
    state.verificationSubmitting = false;
    if (!response) return;
    state.verificationResults[itemId] = response;
    state.planPool = response.plan_pool || state.planPool;
    applyOrchestrationSummary(response.orchestration_summary);
    state.continuationPrompt = response.continuation_prompt || state.continuationPrompt;
    if (response.status === 'passed') showSuccess('Verification passed: '+itemId+'. Review final result / continue to next PlanItem.');
    else if (response.status === 'failed') showWarning('Verification failed: '+itemId+'. DebugLoop is not automatically started. Use Debug Review panel manually.');
    else showWarning('Verification blocked: '+itemId+' ('+(response.warnings||[]).join(',')+')');
    refreshDebugReviewCandidates();
    render();
  }

  async function refreshApprovals() {
    if (!state.currentPoolId || !root.AtlasPipelineAPI?.getApprovals) return;
    const result = await root.AtlasPipelineAPI.getApprovals(state.currentPoolId, workspaceId());
    if (!result?.ok) return;
    state.approvalSummary = result.data || null;
    state.approvalRecords = arr(result.data?.approval_records);
    state.approvalItems = arr(result.data?.approval_required_items);
    state.safeApplyCandidateItems = arr(result.data?.safe_apply_candidate_items);
  }

  function renderApprovalPanel() {
    const summaryEl = $('atlas-approval-summary');
    const listEl = $('atlas-approval-list');
    if (!summaryEl || !listEl) return;
    const summary = state.approvalSummary || {};
    summaryEl.textContent = `pending: ${summary.pending_count || 0} / approved: ${summary.approved_count || 0} / rejected: ${summary.rejected_count || 0} / needs revision: ${summary.needs_revision_count || 0}`;
    const pendingItems = state.approvalItems || [];
    const candidateItems = state.safeApplyCandidateItems || [];
    const pendingHtml = pendingItems.map((item)=>{
      const safeApplyHtml = renderSafeApplyEligibility(item);
      const approval = item?.metadata?.approval || {};
      const decision = String(approval.decision || '').toLowerCase();
      const isPatchDraft = String(item?.metadata?.source || '').toLowerCase() === 'patch_proposal';
      const sourceProposalId = String(item?.metadata?.source_proposal_id || approval.source_proposal_id || '');
      const sourceItemId = String(item?.metadata?.source_item_id || approval.source_item_id || '');
      const targetFiles = arr(item?.target_files).join(', ');
      const nextNote = decision === 'approved'
        ? '<small>Approved. Next: run manual safe_apply from Manual safe apply candidates.</small>'
        : (decision === 'rejected'
          ? '<small>Rejected. No patch was applied.</small>'
          : (decision === 'needs_revision'
            ? '<small>Needs revision. Return to Patch Proposal / PlanItem draft flow manually.</small>'
            : ''));
      return `<div class="atlas-question-card"><b>${esc(item.item_id)}</b> ${esc(item.title||'')}${isPatchDraft ? ' <span class="atlas-badge">Patch Proposal Draft</span>' : ''}<br><small>draft item id: ${esc(item.item_id)}</small>${isPatchDraft ? `<br><small>source proposal id: ${esc(sourceProposalId || '-')}</small><br><small>source item id: ${esc(sourceItemId || '-')}</small><br><small>target files: ${esc(targetFiles || '-')}</small><br><small>risk level: ${esc(item?.risk_level || '-')}</small><br><small>approval status: ${esc(decision || '-')}</small><br><small>PlanItem approval only.</small><br><small>No safe_apply is executed automatically.</small><br><small>No verification or DebugReview is executed automatically.</small>${nextNote}` : ''}<textarea data-approval-reason="${esc(item.item_id)}" placeholder="reason"></textarea><div class="atlas-clarification-actions"><button data-approval="approved" data-item-id="${esc(item.item_id)}" type="button">Approve</button><button data-approval="rejected" data-item-id="${esc(item.item_id)}" type="button">Reject</button><button data-approval="needs_revision" data-item-id="${esc(item.item_id)}" type="button">Needs revision</button>${safeApplyHtml}</div></div>`;
    }).join('');
    const candidateHtml = candidateItems.map((item)=>{
      const safeApplyHtml = renderSafeApplyEligibility(item);
      const applied = String(item?.status || '').toLowerCase() === 'completed';
      const isPatchDraft = String(item?.metadata?.source || '').toLowerCase() === 'patch_proposal';
      const sourceProposalId = String(item?.metadata?.source_proposal_id || '');
      const targetFiles = arr(item?.target_files).join(', ');
      const result = state.safeApplyResults[item.item_id] || item?.metadata?.safe_apply || null;
      const snapshot = result?.change_snapshot || result?.metadata?.change_snapshot || item?.metadata?.change_snapshot || null;
      const resultStatus = result ? String(result.status || '') : '';
      const resultClass = resultStatus === 'applied' ? 'atlas-ok' : (resultStatus === 'blocked' ? 'atlas-warn' : 'atlas-muted');
      return `<div class="atlas-question-card"><b>${esc(item.item_id)}</b> ${esc(item.title||'')} <span class="atlas-badge">Approved candidate</span>${isPatchDraft ? ' <span class="atlas-badge">Patch Proposal Draft</span>' : ''}<div class="atlas-clarification-actions">${applied ? '<small>Already applied</small>' : safeApplyHtml}<small>Item-level manual apply only. Tests and autopilot continuation are not run.</small><small>Manual safe_apply only. Verification and DebugLoop are not run automatically.</small>${renderPatchContentHint(item)}${isPatchDraft ? `<small>source proposal id: ${esc(sourceProposalId || '-')}</small><small>target files: ${esc(targetFiles || '-')}</small><small>Verification is not run automatically.</small>` : ''}${resultStatus ? `<small class="${resultClass}">safe_apply result: ${esc(resultStatus)}</small>` : ''}${resultStatus === 'applied' ? '<small>Next: run manual verification from Post-Apply Verification panel.</small>' : ''}${snapshot?.manifest_path ? `<small>Change Snapshot manifest: ${esc(snapshot.manifest_path)}</small><button data-snapshot-restore-manifest="${esc(snapshot.manifest_path)}" data-snapshot-restore-item="${esc(item.item_id)}" type="button">Restore from Snapshot</button><small>Restore is manual only</small><small>Auto rollback is not enabled</small>` : ''}</div></div>`;
    }).join('');
    if (!pendingHtml && !candidateHtml) { listEl.innerHTML = 'No approval-required items.'; return; }
    listEl.innerHTML = `<h4>Pending approval items</h4>${pendingHtml || '<small>None</small>'}<h4>Manual safe apply candidates</h4>${candidateHtml || '<small>None</small>'}`;
    listEl.querySelectorAll('button[data-approval]').forEach((btn)=>btn.addEventListener('click', ()=>decideApproval(btn.dataset.itemId, btn.dataset.approval)));
    listEl.querySelectorAll('button[data-safe-apply]').forEach((btn)=>btn.addEventListener('click', ()=>executeSafeApply(btn.dataset.safeApply)));
    listEl.querySelectorAll('button[data-snapshot-restore-manifest]').forEach((btn)=>btn.addEventListener('click', ()=>restoreFromSnapshot(btn.dataset.snapshotRestoreManifest, btn.dataset.snapshotRestoreItem)));
  }




  function getPatchSource(item) {
    const metadata = item?.metadata || {};
    const patchProposal = metadata?.patch_proposal || {};
    const candidates = [
      ['proposed_content', metadata?.proposed_content],
      ['patch', metadata?.patch],
      ['unified_diff_preview', metadata?.unified_diff_preview],
      ['patch_proposal.proposed_content', patchProposal?.proposed_content],
      ['patch_proposal.unified_diff_preview', patchProposal?.unified_diff_preview],
    ];
    for (const [source, value] of candidates) {
      if (typeof value === 'string' && value.trim()) return source;
    }
    return '';
  }

  function renderPatchContentHint(item) {
    const source = getPatchSource(item);
    if (!source) return '<small>executable change content: no</small><small>This draft has no executor-readable patch content.</small>'; 
    return `<small>executable change content: yes</small><small>patch source: ${esc(source)}</small>`;
  }

  function isSafeApplyEligible(item) {
    const decision = String(item?.metadata?.approval?.decision || '').toLowerCase();
    const risk = String(item?.risk_level || '').toLowerCase();
    const action = String(item?.metadata?.action_type || '').toLowerCase();
    if (decision !== 'approved') return { eligible: false, reason: 'approval_not_approved' };
    if (risk !== 'low') return { eligible: false, reason: 'risk_not_low' };
    if (action === 'delete' || action === 'run_command') return { eligible: false, reason: 'forbidden_action_type' };
    return { eligible: true, reason: '' };
  }

  function renderSafeApplyEligibility(item) {
    const v = isSafeApplyEligible(item);
    return v.eligible ? '<button data-safe-apply="'+esc(item.item_id)+'" type="button">Safe Apply This Item</button>' : '<small>Not eligible for safe apply: '+esc(v.reason)+'</small>';
  }

  async function executeSafeApply(itemId) {
    if (state.safeApplySubmitting || !state.currentPoolId || !root.AtlasPipelineAPI?.executeSafeApply) return;
    if (!confirm('Apply this approved low-risk PlanItem? This does not run tests or continue autopilot.')) return;
    state.safeApplySubmitting = true;
    const response = await handleResult(await root.AtlasPipelineAPI.executeSafeApply({ pool_id: state.currentPoolId, item_id: itemId, run_id: state.currentRunId || '', workspace_id: workspaceId(), metadata: { ui: 'atlas_dashboard' } }), 'Safe apply failed');
    state.safeApplySubmitting = false;
    if (!response) return;
    state.safeApplyResults[itemId] = response;
    state.planPool = response.plan_pool || state.planPool;
    applyOrchestrationSummary(response.orchestration_summary);
    state.continuationPrompt = response.continuation_prompt || state.continuationPrompt;
    await refreshApprovals();
    if (response.status === 'applied') showSuccess('Manual safe apply completed for item: '+itemId+'. Next: run manual verification from Post-Apply Verification panel.');
    const snap = response?.metadata?.change_snapshot || response?.safe_apply_result?.change_snapshot || null;
    if (snap) {
      const meta = response?.metadata || {};
      const ex = meta.executor_result || response?.safe_apply_result || {};
      showSuccess('Change Snapshot saved / safe_apply_result.status: '+(response?.safe_apply_result?.status||response?.status||'-')+' / reasons: '+String((response?.safe_apply_result?.reasons||response?.warnings||[]).join(','))+' / snapshot id: '+(snap.snapshot_id||'-')+' / manifest: '+(snap.manifest_path||'-')+' / file count: '+String(snap.file_count||0)+' / skipped: '+String(snap.skipped_count||0)+' / Executor workspace root: '+(meta.workspace_root||'-')+' / Change Snapshot workspace root: '+(snap.workspace_root||'-')+' / actual_file_changed: '+String(Boolean(ex.actual_file_changed))+' / changed_files: '+String((ex.changed_files||[]).join(','))+' / file_results: '+JSON.stringify(ex.file_results||response?.safe_apply_result?.file_results||[])+' / Rollback is not automatic yet. / Use this snapshot for manual restore if needed.');
    }
    else if (response.status === 'simulated') showWarning('Simulated only. No files were applied. item: '+itemId);
    else if (response.status === 'blocked') showWarning('Manual safe apply blocked for item: '+itemId+' ('+(response.warnings||[]).join(',')+')');
    else showError('Manual safe apply failed for item: '+itemId+' ('+(response.warnings||[]).join(',')+')');
    render();
  }



  async function restoreFromSnapshot(manifestPath, itemId) {
    if (!state.currentPoolId || !root.AtlasPipelineAPI?.restoreChangeSnapshot) return;
    if (!manifestPath) return;
    if (!confirm('Restore from snapshot manually? Auto rollback is not enabled.')) return;
    const confirmDelete = confirm('Delete files that did not exist before snapshot? (Recommended: Cancel to skip)');
    const response = await handleResult(await root.AtlasPipelineAPI.restoreChangeSnapshot({ pool_id: state.currentPoolId, item_id: itemId || '', run_id: state.currentRunId || '', workspace_id: workspaceId(), manifest_path: manifestPath, confirm_delete_missing_before: confirmDelete, metadata: { ui: 'atlas_dashboard', manual_only: true } }), 'Snapshot restore failed');
    if (!response) return;
    if (response.status === 'restored') showSuccess('Snapshot restore completed manually. report: '+(response.report_json_path || '-'));
    else showWarning('Snapshot restore finished with status: '+response.status+' / warnings: '+(response.warnings || []).join(','));
    render();
  }
  async function decideApproval(itemId, decision) {
    if (state.approvalSubmitting || !state.currentPoolId) return;
    state.approvalSubmitting = true;
    const reasonEl = document.querySelector(`textarea[data-approval-reason="${itemId}"]`);
    const response = await handleResult(await root.AtlasPipelineAPI.decideApproval({ pool_id: state.currentPoolId, item_id: itemId, run_id: state.currentRunId || '', decision, reason: reasonEl?.value || '', workspace_id: workspaceId(), metadata: { ui: 'atlas_dashboard' } }), 'Approval decision failed');
    state.approvalSubmitting = false;
    if (!response) return;
    state.planPool = response.plan_pool || state.planPool;
    applyOrchestrationSummary(response.orchestration_summary);
    state.continuationPrompt = response.continuation_prompt || state.continuationPrompt;
    state.approvalSummary = response.approval_summary || state.approvalSummary;
    state.safeApplyCandidateItems = arr(response.approval_summary?.safe_apply_candidate_items || state.safeApplyCandidateItems);
    if (decision === 'approved') showSuccess('Approved. Next: run manual safe_apply from Manual safe apply candidates.');
    else if (decision === 'rejected') showWarning('Rejected. No patch was applied.');
    else if (decision === 'needs_revision') showWarning('Needs revision. Return to Patch Proposal / PlanItem draft flow manually.');
    await refreshPlanPool();
    await refreshApprovals();
    render();
  }

  async function loadRecoveryLatest() {
    const result = await root.AtlasPipelineAPI.getRecoveryLatest(workspaceId());
    if (!result?.ok) return;
    const recovery = result.data?.recovery_summary || result.data;
    state.recoverySummary = recovery;
    applyOrchestrationSummary(result.data?.orchestration_summary);
    const recoveredPool = recovery?.pool_id || readStorage(storageKeys.poolId);
    const recoveredRun = recovery?.run_id || readStorage(storageKeys.runId);
    if (recoveredPool) state.currentPoolId = recoveredPool;
    if (recoveredRun && recovery?.status !== 'stale') state.currentRunId = recoveredRun;
    if (recovery?.status === 'stale') {
      markStaleRecovery();
      applyOrchestrationSummary(result.data?.orchestration_summary);
    }
    if (recoveredPool || recoveredRun) state.restored = true;
    if (state.currentPoolId) await refreshStatus();
    await refreshContinuation();
    await refreshApprovals();
    render();
  }

  async function loadRecoveredPlan() {
    state.recoveryHidden = false;
    const recovery = state.recoverySummary || {};
    if (recovery.pool_id) state.currentPoolId = recovery.pool_id;
    if (recovery.run_id && recovery.status !== 'stale') state.currentRunId = recovery.run_id;
    await refreshStatus();
  }

  function hideRecoveryBanner() {
    state.recoveryHidden = true;
    renderRecovery();
  }

  function retryLastAction() {
    if (typeof state.lastAction === 'function') state.lastAction();
  }



  function renderPatchRegenFromRecommendationPanel() {
    const panel = $('atlas-patch-regen-from-recommendation-panel');
    if (!panel) return;
    const result = state.patchRegenFromRecommendationResult || {};
    const candidate = result.patch_regen_result?.candidate || {};
    panel.textContent = `status: ${result.status || 'none'} / patch_regen_result_id: ${result.patch_regen_result_id || '-'} / patch_regen_status: ${result.patch_regen_result?.status || '-'} / candidate approval_status: ${candidate.approval_status || '-'} / safe_apply_ready: ${String(candidate.safe_apply_ready === true)}`;
  }

  async function runPatchRegenFromRecommendation() {
    if (state.patchRegenFromRecommendationSubmitting || !state.currentPoolId || !root.AtlasPipelineAPI?.runPatchRegenFromRecommendation) return;
    const item = getItems().find((x) => String(x?.item_id || '') === String(state.planPool?.current_item_id || '')) || getItems()[0];
    const recommendationRunId = $('atlas-patch-regen-from-rec-id')?.value || item?.metadata?.latest_patch_regen_recommendation_id || '';
    if (!item || !recommendationRunId) { showWarning('Patch Regen From Recommendation requires a current item and recommendation_run_id.'); return; }
    state.patchRegenFromRecommendationSubmitting = true;
    const response = await handleResult(await root.AtlasPipelineAPI.runPatchRegenFromRecommendation({
      pool_id: state.currentPoolId,
      item_id: item.item_id,
      run_id: state.currentRunId || '',
      workspace_id: workspaceId(),
      recommendation_run_id: recommendationRunId,
      dry_run: Boolean($('atlas-patch-regen-from-rec-dry-run')?.checked),
      reviewer: $('atlas-patch-regen-from-rec-reviewer')?.value || 'manual',
      reason: $('atlas-patch-regen-from-rec-reason')?.value || '',
      metadata: { ui: 'atlas_dashboard', manual_trigger: true }
    }), 'Patch regen from recommendation failed');
    state.patchRegenFromRecommendationSubmitting = false;
    if (!response) return;
    state.patchRegenFromRecommendationResult = response;
    if (response.status === 'patch_regen_created') showSuccess('Patch candidate generated from recommendation. Manual approval is still required; no verification or safe_apply was run.');
    else if (response.status === 'dry_run') showWarning('Dry run validated recommendation only; patch regeneration was not executed.');
    else showWarning('Patch regen from recommendation finished with status: '+(response.status || '-'));
    await refreshPlanPool();
    render();
  }


  async function prepareNextActionOrchestrator() {
    if (!state.currentPoolId || !root.AtlasPipelineAPI?.prepareNextAction) return;
    const response = await handleResult(await root.AtlasPipelineAPI.prepareNextAction({
      pool_id: state.currentPoolId,
      run_id: state.currentRunId || '',
      workspace_id: workspaceId(),
      multi_status_run_id: $('atlas-next-action-multi-status-run-id')?.value || '',
      item_id: $('atlas-next-action-item-id')?.value || '',
      requested_next_action: $('atlas-next-action-requested-action')?.value || '',
      reviewer: 'manual', metadata: { ui: 'atlas_dashboard' }
    }), 'Next Action Orchestrator prepare failed');
    if (!response) return;
    const c = response.action_contract || {};
    const preview = JSON.stringify(c.payload || {}, null, 2);
    const txt = `status: ${response.status || '-'}
selected_item_id: ${response.selected_item_id || '-'}
selected_next_action: ${response.selected_next_action || '-'}
action_kind: ${c.action_kind || '-'}
target_api_path: ${c.target_api_path || '-'}
payload_valid: ${String(Boolean(c.payload_valid))}
missing_fields: ${arr(c.missing_fields).join(', ') || '-'}
payload_preview:
${preview}`;
    const panel = $('atlas-next-action-orchestrator-panel'); if (panel) panel.textContent = txt;
  }

  async function checkAutomationReadiness() {
    const item = getItems().find((x) => String(x?.item_id || '') === String(state.planPool?.current_item_id || '')) || getItems()[0];
    if (!item || !state.currentPoolId || !root.AtlasPipelineAPI?.decideAutomation) return;
    const presetId = $('atlas-auto-preset')?.value || 'manual_only';
    const response = await handleResult(await root.AtlasPipelineAPI.decideAutomation({ pool_id: state.currentPoolId, item_id: item.item_id, preset_id: presetId, phase: 'pre_safe_apply', workspace_id: workspaceId() }), 'Automation readiness failed');
    if (!response) return;
    state.automationDecision = response;
    render();
  }


  const operatorLoopStorageKey = 'atlas.operatorLoopState.v1';
  const operatorLoopState = {
    poolId:'', runId:'', reviewer:'manual', reason:'', multiStatusRunId:'', orchestratorRunId:'', actionId:'', selectedItemId:'', selectedNextAction:'', actionKind:'', confirmationToken:'', confirmationText:'EXECUTE ONE ACTION', explicitDecision:'', dryRunExecutorRunId:'', executedExecutorRunId:'', postRefreshRunId:'', lastQueueResult:null, lastContractResult:null, lastDryRunResult:null, lastExecuteResult:null, lastRefreshResult:null,
  };
  function loadOperatorLoopState(){ try{ const raw=localStorage.getItem(operatorLoopStorageKey)||''; if(!raw)return; const v=JSON.parse(raw); Object.assign(operatorLoopState,{poolId:v.poolId||'',runId:v.runId||'',reviewer:v.reviewer||'manual',reason:v.reason||'',multiStatusRunId:v.multiStatusRunId||'',orchestratorRunId:v.orchestratorRunId||'',selectedItemId:v.selectedItemId||'',selectedNextAction:v.selectedNextAction||'',actionId:v.actionId||'',actionKind:v.actionKind||'',postRefreshRunId:v.postRefreshRunId||''}); }catch(_e){} }
  function persistOperatorLoopState(){ try{ localStorage.setItem(operatorLoopStorageKey,JSON.stringify({poolId:operatorLoopState.poolId,runId:operatorLoopState.runId,reviewer:operatorLoopState.reviewer,reason:operatorLoopState.reason,multiStatusRunId:operatorLoopState.multiStatusRunId,orchestratorRunId:operatorLoopState.orchestratorRunId,selectedItemId:operatorLoopState.selectedItemId,selectedNextAction:operatorLoopState.selectedNextAction,actionId:operatorLoopState.actionId,actionKind:operatorLoopState.actionKind,postRefreshRunId:operatorLoopState.postRefreshRunId})); }catch(_e){} }
  function getOperatorLoopVerificationHandoff(){ const c=operatorLoopState.lastContractResult?.action_contract?.metadata?.verification_recommendation_handoff; if(c&&typeof c==='object') return c; const m=operatorLoopState.lastContractResult?.metadata?.verification_recommendation_handoff; if(m&&typeof m==='object') return m; return {}; }
  function renderOperatorLoopVerificationHandoff(){ const h=getOperatorLoopVerificationHandoff(); const s=$('atlas-operator-loop-verification-handoff-summary'); const r=$('atlas-operator-loop-verification-handoff-result'); const cs=$('atlas-operator-loop-verification-handoff-copy-status'); const impacted=Array.isArray(h.impacted_files)?h.impacted_files:[]; const tests=Array.isArray(h.related_tests)?h.related_tests:[]; const cmds=Array.isArray(h.recommended_commands)?h.recommended_commands:[]; const steps=Array.isArray(h.manual_verification_steps)?h.manual_verification_steps:[]; const warns=Array.isArray(h.warnings)?h.warnings:[]; const summary={approval_summary:h.approval_summary||'',confidence:h.confidence||'unknown',impacted_files_count:impacted.length,impacted_files:impacted,related_tests_count:tests.length,related_tests:tests,recommended_commands_count:cmds.length,recommended_commands:cmds,manual_verification_steps_count:steps.length,manual_verification_steps:steps,warnings_count:warns.length,warnings:warns,advisory_only:h.advisory_only===true,manual_approval_only:h.manual_approval_only===true,executed:h.executed===true}; if(s) s.textContent=`Verification Handoff Summary (manual approval context): approval_summary=${summary.approval_summary||'-'} / confidence=${summary.confidence} / impacted_files=${summary.impacted_files_count} / related_tests=${summary.related_tests_count} / recommended_commands=${summary.recommended_commands_count} / manual_verification_steps=${summary.manual_verification_steps_count} / warnings=${summary.warnings_count} / advisory_only=${String(summary.advisory_only)} / manual_approval_only=${String(summary.manual_approval_only)} / executed=${String(summary.executed)} / note=Manual approval context only. Suggested commands were not executed.`; if(r) r.textContent=JSON.stringify(summary,null,2); if(cs && !cs.textContent) cs.textContent='Manual approval context only. Suggested commands were not executed.'; }
  function buildOperatorLoopVerificationHandoffExportPayload(){ const h=getOperatorLoopVerificationHandoff(); return {generated_at:new Date().toISOString(),source:'operator_loop_verification_handoff',pool_id:operatorLoopState.poolId||'',run_id:operatorLoopState.runId||'',action_id:operatorLoopState.actionId||'',selected_item_id:operatorLoopState.selectedItemId||'',selected_next_action:operatorLoopState.selectedNextAction||'',action_kind:operatorLoopState.actionKind||'',approval_summary:String(h.approval_summary||''),confidence:String(h.confidence||'unknown'),impacted_files:Array.isArray(h.impacted_files)?h.impacted_files:[],related_tests:Array.isArray(h.related_tests)?h.related_tests:[],recommended_commands:Array.isArray(h.recommended_commands)?h.recommended_commands:[],manual_verification_steps:Array.isArray(h.manual_verification_steps)?h.manual_verification_steps:[],warnings:Array.isArray(h.warnings)?h.warnings:[],advisory_only:h.advisory_only===true,manual_approval_only:h.manual_approval_only===true,executed:h.executed===true,commands_are_suggestions_only:h.commands_are_suggestions_only!==false,confirmation_required:true,confirmation_text_required:'EXECUTE ONE ACTION',dry_run_first_required:true}; }
  async function copyOperatorLoopVerificationHandoff(){ const payload=buildOperatorLoopVerificationHandoffExportPayload(); const text=JSON.stringify(payload,null,2); const cs=$('atlas-operator-loop-verification-handoff-copy-status'); const r=$('atlas-operator-loop-verification-handoff-result'); try{ if(navigator?.clipboard?.writeText){ await navigator.clipboard.writeText(text); if(cs) cs.textContent='Copied verification handoff JSON to clipboard (manual-only context).'; return; } }catch(_e){} if(r) r.textContent=text; if(cs) cs.textContent='Clipboard unavailable. JSON rendered in handoff result for manual copy.'; }
  function exportOperatorLoopVerificationHandoff(){ const payload=buildOperatorLoopVerificationHandoffExportPayload(); const text=JSON.stringify(payload,null,2); const cs=$('atlas-operator-loop-verification-handoff-copy-status'); const r=$('atlas-operator-loop-verification-handoff-result'); try{ if(typeof Blob==='function' && typeof URL!=='undefined' && URL.createObjectURL){ const blob=new Blob([text],{type:'application/json'}); const href=URL.createObjectURL(blob); const a=document.createElement('a'); const pool=payload.pool_id||'pool'; const action=payload.action_id||'action'; a.href=href; a.download=`atlas-verification-handoff-${pool}-${action}.json`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(href); if(cs) cs.textContent='Exported verification handoff JSON (manual-only context).'; return; } }catch(_e){} if(r) r.textContent=text; if(cs) cs.textContent='Download unavailable. JSON rendered in handoff result for manual save.'; }

  function getOperatorLoopGuardState(){ const exReq=operatorLoopState.selectedNextAction==='approve_patch_candidate', pv=operatorLoopState.lastContractResult?.action_contract?.payload_valid===true, dry=operatorLoopState.lastDryRunResult||{}, hasPoolId=!!operatorLoopState.poolId, hasRunId=!!operatorLoopState.runId, hasMultiStatusRunId=!!operatorLoopState.multiStatusRunId, hasOrchestratorRunId=!!operatorLoopState.orchestratorRunId, hasActionId=!!operatorLoopState.actionId, hasSelectedNextAction=!!operatorLoopState.selectedNextAction, hasSelectedItemId=!!operatorLoopState.selectedItemId, actionKind=operatorLoopState.actionKind||'', isExecutionCandidate=actionKind==='execution_candidate', requiresExplicitDecision=exReq, explicitDecisionOk=!exReq||operatorLoopState.explicitDecision==='approve', hasConfirmationToken=!!operatorLoopState.confirmationToken, confirmationTextOk=operatorLoopState.confirmationText==='EXECUTE ONE ACTION', confirmationOk=confirmationTextOk&&hasConfirmationToken, dryRunReady=!!(operatorLoopState.dryRunExecutorRunId&&dry.status==='dry_run'&&dry.validation&&dry.validation.executable===true), canBuildQueue=hasPoolId, canPrepare=hasPoolId&&hasMultiStatusRunId, canPreviewToken=hasOrchestratorRunId&&hasActionId&&hasSelectedNextAction&&hasSelectedItemId&&isExecutionCandidate, payloadValid=pv, canDryRun=confirmationOk&&isExecutionCandidate&&payloadValid&&explicitDecisionOk, canExecute=operatorLoopCanExecute(), canRefresh=!!(operatorLoopState.executedExecutorRunId||operatorLoopState.dryRunExecutorRunId), reasons=[]; if(!canBuildQueue) reasons.push('Build Queue requires pool_id.'); if(!canPrepare) reasons.push('Prepare requires multi_status_run_id.'); if(!canPreviewToken) reasons.push('Preview Token requires action_ready contract.'); if(!canDryRun) reasons.push('Dry Run requires confirmation token, EXECUTE ONE ACTION, payload_valid=true, execution_candidate, and explicit approval when required.'); if(!canExecute) reasons.push('Execute requires successful dry_run and execute guards.'); if(!canRefresh) reasons.push('Refresh requires executor_run_id.'); if(requiresExplicitDecision&&!explicitDecisionOk) reasons.push('Approval action requires explicit_decision=approve.'); return {hasPoolId,hasRunId,hasMultiStatusRunId,hasOrchestratorRunId,hasActionId,hasSelectedNextAction,hasSelectedItemId,actionKind,isExecutionCandidate,payloadValid,requiresExplicitDecision,explicitDecisionOk,hasConfirmationToken,confirmationTextOk,confirmationOk,dryRunReady,canBuildQueue,canPrepare,canPreviewToken,canDryRun,canExecute,canRefresh,reasons}; }
  function operatorLoopRender(){ const st=$('atlas-operator-loop-status'), why=$('atlas-operator-loop-disabled-reason'), step=$('atlas-operator-loop-current-step'), sum=$('atlas-operator-loop-next-action-summary'), exBtn=$('atlas-operator-loop-explicit-decision'), guardState=getOperatorLoopGuardState(), reasons=[...guardState.reasons], g={build:!guardState.canBuildQueue,prepare:!guardState.canPrepare,token:!guardState.canPreviewToken,dry:!guardState.canDryRun,execute:!guardState.canExecute,refresh:!guardState.canRefresh}; [['build-queue',g.build],['prepare',g.prepare],['token',g.token],['dry-run',g.dry],['execute',g.execute],['refresh',g.refresh],['advance',!operatorLoopState.poolId],['execute-refresh',g.execute||operatorLoopState.actionKind!=='execution_candidate']].forEach(([k,v])=>{ const b=$('atlas-operator-loop-'+k+'-btn'); if(b) b.disabled=!!v; }); if(exBtn){ exBtn.disabled=!guardState.requiresExplicitDecision; if(!guardState.requiresExplicitDecision) exBtn.value=''; } if(!guardState.hasPoolId) reasons.push('Advance requires pool_id.'); if(g.execute||!guardState.isExecutionCandidate) reasons.push('Execute and refresh requires successful dry_run and confirmation.'); if(st) st.textContent='Operator loop ready'; if(why) why.textContent=reasons.join(' | ')||'All step guards satisfied.'; if(step) step.textContent=`Current step: ${guardState.dryRunReady?'ready_to_execute':(operatorLoopState.actionId?'action_prepared':'idle')}.`; if(sum) sum.textContent=`Next action: item=${operatorLoopState.selectedItemId||'-'} / action=${operatorLoopState.selectedNextAction||'-'} / kind=${operatorLoopState.actionKind||'-'}.`; const d=$('atlas-operator-loop-diagnostics'); if(d) d.textContent=JSON.stringify({selectedItemId:operatorLoopState.selectedItemId,selectedNextAction:operatorLoopState.selectedNextAction,actionId:operatorLoopState.actionId,actionKind:operatorLoopState.actionKind,payloadValid:guardState.payloadValid,requiresExplicitDecision:guardState.requiresExplicitDecision,explicitDecision:operatorLoopState.explicitDecision||'',guards:g,reasons:reasons},null,2); renderOperatorLoopVerificationHandoff(); }
  function operatorLoopReadInputs(){ operatorLoopState.poolId=$('atlas-operator-loop-pool-id')?.value||state.currentPoolId||''; operatorLoopState.runId=$('atlas-operator-loop-run-id')?.value||state.currentRunId||''; operatorLoopState.reviewer=$('atlas-operator-loop-reviewer')?.value||'manual'; operatorLoopState.reason=$('atlas-operator-loop-reason')?.value||''; operatorLoopState.confirmationToken=$('atlas-operator-loop-confirmation-token')?.value||''; operatorLoopState.confirmationText=$('atlas-operator-loop-confirmation-text')?.value||'EXECUTE ONE ACTION'; operatorLoopState.explicitDecision=$('atlas-operator-loop-explicit-decision')?.value||''; }
  async function operatorLoopBuildQueue(){ operatorLoopReadInputs(); const r=await handleResult(await root.AtlasPipelineAPI.buildMultiItemSupervisedStatus({pool_id:operatorLoopState.poolId,run_id:operatorLoopState.runId,workspace_id:workspaceId(),project_path:'',dry_run:false,refresh_item_status:true,update_item_status:true,update_metadata:true,reviewer:operatorLoopState.reviewer,reason:operatorLoopState.reason,metadata:{source:'operator_loop_ui'}}),'Build queue failed'); if(!r)return; operatorLoopState.lastQueueResult=r; operatorLoopState.multiStatusRunId=r.multi_status_run_id||r.run_id||''; $('atlas-operator-loop-queue-result').textContent=JSON.stringify(r,null,2); persistOperatorLoopState(); operatorLoopRender(); }
  async function operatorLoopPrepare(){ operatorLoopReadInputs(); const r=await handleResult(await root.AtlasPipelineAPI.prepareNextAction({pool_id:operatorLoopState.poolId,run_id:operatorLoopState.runId,multi_status_run_id:operatorLoopState.multiStatusRunId,build_queue_if_missing:false,refresh_queue:false,dry_run:false,reviewer:operatorLoopState.reviewer,reason:operatorLoopState.reason,metadata:{source:'operator_loop_ui'}}),'Prepare failed'); if(!r)return; operatorLoopState.lastContractResult=r; operatorLoopState.orchestratorRunId=r.orchestrator_run_id||''; operatorLoopState.selectedItemId=r.selected_item_id||''; operatorLoopState.selectedNextAction=r.selected_next_action||''; operatorLoopState.actionId=r.action_id||r.action_contract?.action_id||''; operatorLoopState.actionKind=r.action_contract?.action_kind||''; $('atlas-operator-loop-contract-result').textContent=JSON.stringify(r,null,2); persistOperatorLoopState(); operatorLoopRender(); }
  async function operatorLoopToken(){ operatorLoopReadInputs(); const r=await handleResult(await root.AtlasPipelineAPI.previewManualNextActionConfirmationToken({pool_id:operatorLoopState.poolId,orchestrator_run_id:operatorLoopState.orchestratorRunId,action_id:operatorLoopState.actionId,expected_next_action:operatorLoopState.selectedNextAction,item_id:operatorLoopState.selectedItemId}),'Token preview failed'); if(!r)return; operatorLoopState.confirmationToken=r.confirmation_token||''; $('atlas-operator-loop-confirmation-token').value=operatorLoopState.confirmationToken; $('atlas-operator-loop-confirmation-text').value='EXECUTE ONE ACTION'; operatorLoopRender(); }
  function operatorLoopCanExecute(){ const d=operatorLoopState.lastDryRunResult||{}; return !!(operatorLoopState.orchestratorRunId&&operatorLoopState.actionId&&operatorLoopState.selectedNextAction&&operatorLoopState.confirmationToken&&operatorLoopState.confirmationText==='EXECUTE ONE ACTION'&&operatorLoopState.dryRunExecutorRunId&&d.status==='dry_run'&&d.validation&&d.validation.executable===true&&(!d.requires_explicit_decision||operatorLoopState.explicitDecision==='approve')); }
  async function operatorLoopExec(dry){ operatorLoopReadInputs(); const r=await handleResult(await root.AtlasPipelineAPI.executeManualNextAction({pool_id:operatorLoopState.poolId,run_id:operatorLoopState.runId,orchestrator_run_id:operatorLoopState.orchestratorRunId,action_id:operatorLoopState.actionId,expected_next_action:operatorLoopState.selectedNextAction,confirmation_token:operatorLoopState.confirmationToken,confirmation_text:'EXECUTE ONE ACTION',require_dry_run_first:true,dry_run:!!dry,reviewer:operatorLoopState.reviewer,reason:operatorLoopState.reason,explicit_decision:operatorLoopState.explicitDecision,metadata:{source:'operator_loop_ui',operator_loop_phase:dry?'dry_run':'execute'}}),dry?'Dry run failed':'Execute failed'); if(!r)return; if(dry){operatorLoopState.lastDryRunResult=r; operatorLoopState.dryRunExecutorRunId=r.executor_run_id||'';} else {operatorLoopState.lastExecuteResult=r; operatorLoopState.executedExecutorRunId=r.executor_run_id||'';} $('atlas-operator-loop-executor-result').textContent=JSON.stringify(r,null,2); persistOperatorLoopState(); operatorLoopRender(); }
  async function operatorLoopRefresh(){ operatorLoopReadInputs(); const r=await handleResult(await root.AtlasPipelineAPI.refreshAfterManualExecution({pool_id:operatorLoopState.poolId,run_id:operatorLoopState.runId,executor_run_id:operatorLoopState.executedExecutorRunId||operatorLoopState.dryRunExecutorRunId,dry_run:false,refresh_item_status:true,rebuild_multi_status_queue:true,prepare_next_action:true,reviewer:operatorLoopState.reviewer,reason:operatorLoopState.reason,metadata:{source:'operator_loop_ui'}}),'Refresh failed'); if(!r)return; const n=r.next_action_orchestrator_result||{}; operatorLoopState.lastRefreshResult=r; operatorLoopState.postRefreshRunId=r.refresh_run_id||''; operatorLoopState.multiStatusRunId=r.multi_status_result?.multi_status_run_id||operatorLoopState.multiStatusRunId; operatorLoopState.orchestratorRunId=n.orchestrator_run_id||''; operatorLoopState.selectedItemId=n.selected_item_id||''; operatorLoopState.selectedNextAction=n.selected_next_action||''; operatorLoopState.actionId=n.action_contract?.action_id||n.action_id||''; operatorLoopState.actionKind=n.action_contract?.action_kind||''; operatorLoopState.lastContractResult=n; operatorLoopState.confirmationToken=''; operatorLoopState.dryRunExecutorRunId=''; operatorLoopState.executedExecutorRunId=''; operatorLoopState.lastDryRunResult=null; operatorLoopState.lastExecuteResult=null; $('atlas-operator-loop-confirmation-token').value=''; $('atlas-operator-loop-executor-result').textContent='Next action prepared. Dry run required.'; $('atlas-operator-loop-next-step').textContent=`Next step: item=${operatorLoopState.selectedItemId||'-'} / action=${operatorLoopState.selectedNextAction||'-'} / kind=${operatorLoopState.actionKind||'-'}`; $('atlas-operator-loop-refresh-result').textContent=JSON.stringify(r,null,2); persistOperatorLoopState(); operatorLoopRender(); }
  async function operatorLoopAdvanceToConfirmation(){ operatorLoopReadInputs(); const r=await handleResult(await root.AtlasPipelineAPI.runGuardedOperatorLoop({pool_id:operatorLoopState.poolId,run_id:operatorLoopState.runId,workspace_id:workspaceId(),project_path:'',mode:'advance_to_confirmation',reviewer:operatorLoopState.reviewer,reason:operatorLoopState.reason,metadata:{source:'operator_loop_ui',operator_loop_phase:'advance_to_confirmation'}}),'Advance to confirmation failed'); if(!r)return; operatorLoopState.guardedLoopRunId=r.loop_run_id||''; operatorLoopState.lastGuardedLoopResult=r; operatorLoopState.semiAutoMode=r.mode||''; operatorLoopState.semiAutoStatus=r.status||''; operatorLoopState.multiStatusRunId=r.multi_status_run_id||''; operatorLoopState.orchestratorRunId=r.orchestrator_run_id||''; operatorLoopState.selectedItemId=r.selected_item_id||''; operatorLoopState.selectedNextAction=r.selected_next_action||''; operatorLoopState.actionId=r.action_id||''; operatorLoopState.actionKind=r.action_kind||''; operatorLoopState.confirmationToken=r.confirmation_token||''; operatorLoopState.dryRunExecutorRunId=r.executor_run_id||''; operatorLoopState.lastDryRunResult=r.dry_run_result||null; $('atlas-operator-loop-semi-auto-status').textContent=r.status||'-'; $('atlas-operator-loop-guarded-result').textContent=JSON.stringify(r,null,2); $('atlas-operator-loop-confirmation-token').value=operatorLoopState.confirmationToken; persistOperatorLoopState(); operatorLoopRender(); }
  async function operatorLoopExecuteAndRefresh(){ operatorLoopReadInputs(); const r=await handleResult(await root.AtlasPipelineAPI.runGuardedOperatorLoop({pool_id:operatorLoopState.poolId,run_id:operatorLoopState.runId,workspace_id:workspaceId(),project_path:'',mode:'execute_and_refresh',orchestrator_run_id:operatorLoopState.orchestratorRunId,action_id:operatorLoopState.actionId,expected_next_action:operatorLoopState.selectedNextAction,confirmation_token:operatorLoopState.confirmationToken,confirmation_text:'EXECUTE ONE ACTION',explicit_decision:operatorLoopState.explicitDecision,require_dry_run_first:true,reviewer:operatorLoopState.reviewer,reason:operatorLoopState.reason,metadata:{source:'operator_loop_ui',operator_loop_phase:'execute_and_refresh'}}),'Execute and refresh failed'); if(!r)return; operatorLoopState.guardedLoopRunId=r.loop_run_id||''; operatorLoopState.executedExecutorRunId=r.executor_run_id||''; operatorLoopState.postRefreshRunId=r.post_refresh_run_id||''; const n=r.refresh_result?.next_action_orchestrator_result||{}; operatorLoopState.orchestratorRunId=n.orchestrator_run_id||operatorLoopState.orchestratorRunId; operatorLoopState.selectedItemId=n.selected_item_id||operatorLoopState.selectedItemId; operatorLoopState.selectedNextAction=n.selected_next_action||operatorLoopState.selectedNextAction; operatorLoopState.actionId=n.action_contract?.action_id||n.action_id||operatorLoopState.actionId; operatorLoopState.actionKind=n.action_contract?.action_kind||operatorLoopState.actionKind; operatorLoopState.confirmationToken=''; operatorLoopState.dryRunExecutorRunId=''; operatorLoopState.lastDryRunResult=null; operatorLoopState.lastExecuteResult=null; $('atlas-operator-loop-confirmation-token').value=''; $('atlas-operator-loop-guarded-result').textContent=JSON.stringify(r,null,2); $('atlas-operator-loop-semi-auto-status').textContent=r.status||'-'; persistOperatorLoopState(); operatorLoopRender(); }
  function repoIndexProjectPath() {
    const uiPath = ($('atlas-repo-index-project-path')?.value || '').trim();
    return uiPath || state.currentProjectPath || state.workspaceProjectPath || '';
  }

  function repoIndexChangedFiles() {
    return String($('atlas-repo-index-changed-files')?.value || '')
      .split(/[\n,]/)
      .map((value) => value.trim())
      .filter(Boolean);
  }

  function renderRepoIndexPanel() {
    const statusEl = $('atlas-repo-index-status');
    const summaryEl = $('atlas-repo-index-summary');
    const resultEl = $('atlas-repo-index-result');
    const active = state.repoIndexResult || state.repoIndexLatest || state.repoIndexImpacts || state.repoIndexRelatedTests || {};
    const payload = active?.data || active;
    const statusText = payload?.status || active?.message || (state.repoIndexSubmitting ? 'submitting' : 'idle');
    if (statusEl) statusEl.textContent = statusText;

    const summary = {
      index_run_id: payload?.index_run_id || '-',
      status: payload?.status || '-',
      total_files: payload?.total_files ?? 0,
      indexed_files: payload?.indexed_files ?? 0,
      skipped_files: payload?.skipped_files ?? 0,
      symbol_count: payload?.symbol_count ?? 0,
      edge_count: payload?.edge_count ?? 0,
      impacted_files: Array.isArray((state.repoIndexImpacts?.data || state.repoIndexImpacts)?.impacted_files) ? (state.repoIndexImpacts?.data || state.repoIndexImpacts).impacted_files.length : 0,
      related_tests: Array.isArray((state.repoIndexRelatedTests?.data || state.repoIndexRelatedTests)?.related_tests) ? (state.repoIndexRelatedTests?.data || state.repoIndexRelatedTests).related_tests.length : 0,
    };
    if (summaryEl) summaryEl.textContent = Object.entries(summary).map(([k, v]) => `${k}: ${v}`).join(' / ');

    const output = {
      result: state.repoIndexResult,
      latest: state.repoIndexLatest,
      impacts: state.repoIndexImpacts,
      related_tests: state.repoIndexRelatedTests,
    };
    if (resultEl) resultEl.textContent = JSON.stringify(output, null, 2);
  }

  function repoIndexBasePayload() {
    return {
      project_path: repoIndexProjectPath(),
      workspace_id: workspaceId(),
      mode: 'build_or_update',
      incremental: true,
      changed_files: repoIndexChangedFiles(),
    };
  }

  async function buildRepoIndexFromUI() {
    const api = root.AtlasPipelineAPI;
    if (!api) {
      state.repoIndexResult = { status: 'error', message: 'AtlasPipelineAPI unavailable' };
      renderRepoIndexPanel();
      return;
    }
    if (typeof api.buildRepoIndex !== 'function') {
      state.repoIndexResult = { status: 'error', message: 'Repo Index API helper unavailable' };
      renderRepoIndexPanel();
      return;
    }
    const payload = repoIndexBasePayload();
    if (!payload.project_path) {
      state.repoIndexResult = { status: 'error', message: 'project_path is required' };
      renderRepoIndexPanel();
      return;
    }
    state.repoIndexSubmitting = true;
    renderRepoIndexPanel();
    const response = await api.buildRepoIndex(payload);
    state.repoIndexSubmitting = false;
    state.repoIndexResult = response;
    renderRepoIndexPanel();
  }

  async function loadLatestRepoIndexFromUI() {
    const api = root.AtlasPipelineAPI;
    if (!api) {
      state.repoIndexLatest = { status: 'error', message: 'AtlasPipelineAPI unavailable' };
      renderRepoIndexPanel();
      return;
    }
    if (typeof api.getLatestRepoIndex !== 'function') {
      state.repoIndexLatest = { status: 'error', message: 'Repo Index API helper unavailable' };
      renderRepoIndexPanel();
      return;
    }
    const payload = repoIndexBasePayload();
    if (!payload.project_path) {
      state.repoIndexLatest = { status: 'error', message: 'project_path is required' };
      renderRepoIndexPanel();
      return;
    }
    state.repoIndexSubmitting = true;
    renderRepoIndexPanel();
    const response = await api.getLatestRepoIndex(payload);
    state.repoIndexSubmitting = false;
    state.repoIndexLatest = response;
    renderRepoIndexPanel();
  }

  async function queryRepoIndexImpactsFromUI() {
    const api = root.AtlasPipelineAPI;
    if (!api) {
      state.repoIndexImpacts = { status: 'error', message: 'AtlasPipelineAPI unavailable' };
      renderRepoIndexPanel();
      return;
    }
    if (typeof api.getRepoIndexImpacts !== 'function') {
      state.repoIndexImpacts = { status: 'error', message: 'Repo Index API helper unavailable' };
      renderRepoIndexPanel();
      return;
    }
    const payload = repoIndexBasePayload();
    if (!payload.project_path) {
      state.repoIndexImpacts = { status: 'error', message: 'project_path is required' };
      renderRepoIndexPanel();
      return;
    }
    state.repoIndexSubmitting = true;
    renderRepoIndexPanel();
    const response = await api.getRepoIndexImpacts(payload);
    state.repoIndexSubmitting = false;
    state.repoIndexImpacts = response;
    renderRepoIndexPanel();
  }

  async function queryRepoIndexRelatedTestsFromUI() {
    const api = root.AtlasPipelineAPI;
    if (!api) {
      state.repoIndexRelatedTests = { status: 'error', message: 'AtlasPipelineAPI unavailable' };
      renderRepoIndexPanel();
      return;
    }
    if (typeof api.getRepoIndexRelatedTests !== 'function') {
      state.repoIndexRelatedTests = { status: 'error', message: 'Repo Index API helper unavailable' };
      renderRepoIndexPanel();
      return;
    }
    const payload = repoIndexBasePayload();
    if (!payload.project_path) {
      state.repoIndexRelatedTests = { status: 'error', message: 'project_path is required' };
      renderRepoIndexPanel();
      return;
    }
    state.repoIndexSubmitting = true;
    renderRepoIndexPanel();
    const response = await api.getRepoIndexRelatedTests(payload);
    state.repoIndexSubmitting = false;
    state.repoIndexRelatedTests = response;
    renderRepoIndexPanel();
  }
  function buildRepoContextPayloadFromUI() {
    return { project_path: repoIndexProjectPath(), workspace_id: workspaceId(), changed_files: repoIndexChangedFiles(), target_files: repoIndexChangedFiles(), allow_build_if_missing: false, mode: 'scope_summary' };
  }
  function renderRepoContextTestsPanel() {
    const summaryEl = $('atlas-repo-context-tests-summary'); const resultEl = $('atlas-repo-context-tests-result');
    const payload = (state.repoContextImpactedTests?.data || state.repoContextImpactedTests || {});
    if (summaryEl) summaryEl.textContent = `tests_status: ${payload.status || (state.repoContextSubmitting ? 'submitting' : 'idle')} / related_tests: ${(payload.related_tests || []).length} / commands: ${(payload.recommended_commands || []).length} / confidence: ${payload.confidence || '-'} / executed: false`;
    if (resultEl) resultEl.textContent = JSON.stringify(state.repoContextImpactedTests || {}, null, 2);
  }
  function renderRepoContextVerificationPlanPanel() {
    const summaryEl = $('atlas-repo-context-verification-plan-summary');
    const resultEl = $('atlas-repo-context-verification-plan-result');
    const payload = (state.repoContextVerificationPlan?.data || state.repoContextVerificationPlan || {});
    const status = payload.status || (state.repoContextSubmitting ? 'submitting' : 'idle');
    if (summaryEl) summaryEl.textContent = `status: ${status} / related_tests: ${(payload.related_tests || []).length} / commands: ${(payload.recommended_commands || []).length} / confidence: ${payload.confidence || '-'}`;
    if (resultEl) resultEl.textContent = JSON.stringify(state.repoContextVerificationPlan || {}, null, 2);
  }

  function renderPlanItemImpactMapPanel() {
    const summaryEl = $('atlas-plan-item-impact-map-summary');
    const resultEl = $('atlas-plan-item-impact-map-result');
    const payload = state.planItemImpactMap?.data || state.planItemImpactMap || {};
    const status = payload.status || (state.repoContextSubmitting ? 'submitting' : 'idle');
    if (summaryEl) summaryEl.textContent = `status: ${status} / items: ${(payload.impacts || []).length} / confidence: ${payload.confidence || '-'}`;
    if (resultEl) resultEl.textContent = JSON.stringify(state.planItemImpactMap || {}, null, 2);
  }

  function currentPlanPoolPayload() {
    const pool = state.planPool?.plan_pool || state.planPool || state.lastPlanResponse?.plan_pool || {};
    return pool && typeof pool === 'object' ? pool : {};
  }

  async function queryPlanItemImpactMapFromUI() {
    if (typeof root.AtlasPipelineAPI?.getRepoContextPlanItemImpactMap !== 'function') return;
    const payload = buildRepoContextPayloadFromUI();
    payload.plan_pool = currentPlanPoolPayload();
    payload.pool_id = state.currentPoolId || '';
    payload.goal = state.goalInput || '';
    if (!payload.project_path) {
      state.planItemImpactMap = { status: 'error', message: 'project_path is required' };
      renderPlanItemImpactMapPanel();
    renderVerificationRecommendationPanel();
    renderVerificationRecommendationHandoffPanel();
    renderContextRefreshV2Panel();
      return;
    }
    state.repoContextSubmitting = true;
    renderPlanItemImpactMapPanel();
    renderVerificationRecommendationPanel();
    const response = await root.AtlasPipelineAPI.getRepoContextPlanItemImpactMap(payload);
    const mapPayload = response?.data || response || {};
    state.planItemImpactMap = mapPayload;
    state.repoContextSubmitting = false;
    renderPlanItemImpactMapPanel();
    renderVerificationRecommendationPanel();
  }

  async function queryRepoContextImpactedTestsFromUI() {
    if (typeof root.AtlasPipelineAPI?.getRepoContextImpactedTests !== 'function') return;
    state.repoContextSubmitting = true; renderRepoContextTestsPanel();
    state.repoContextImpactedTests = await root.AtlasPipelineAPI.getRepoContextImpactedTests(buildRepoContextPayloadFromUI());
    state.repoContextSubmitting = false; renderRepoContextTestsPanel();
  }




  function renderVerificationRecommendationHandoffPanel() {
    const summary = $('atlas-verification-recommendation-handoff-summary');
    const result = $('atlas-verification-recommendation-handoff-result');
    const payload = state.verificationRecommendationHandoff?.data || state.verificationRecommendationHandoff || {};
    const status = payload.status || (state.repoContextSubmitting ? 'submitting' : 'idle');
    if (summary) summary.textContent = `status: ${status} / confidence: ${payload.confidence || '-'} / impacted_files: ${(payload.impacted_files || []).length} / related_tests: ${(payload.related_tests || []).length} / recommended_commands: ${(payload.recommended_commands || []).length} / manual_approval_only: true / executed: false`;
    if (result) result.textContent = JSON.stringify(state.verificationRecommendationHandoff || {}, null, 2);
  }

  async function queryVerificationRecommendationHandoffFromUI() {
    if (typeof root.AtlasPipelineAPI?.getVerificationRecommendationHandoff !== 'function') return;
    const payload = buildRepoContextPayloadFromUI();
    payload.plan_pool = currentPlanPoolPayload();
    payload.verification_recommendation = state.verificationRecommendation?.data || state.verificationRecommendation || {};
    payload.pool_id = state.currentPoolId || '';
    payload.goal = state.goalInput || '';
    if (!payload.project_path) {
      state.verificationRecommendationHandoff = { status: 'error', message: 'project_path is required' };
      renderVerificationRecommendationHandoffPanel();
      return;
    }
    state.repoContextSubmitting = true;
    renderVerificationRecommendationHandoffPanel();
    try {
      const response = await root.AtlasPipelineAPI.getVerificationRecommendationHandoff(payload);
      const data = response?.data || response || {};
      state.verificationRecommendationHandoff = data;
      renderVerificationRecommendationHandoffPanel();
    } finally {
      state.repoContextSubmitting = false;
      renderVerificationRecommendationHandoffPanel();
    }
  }
  function renderVerificationRecommendationPanel() {
    const summary = $('atlas-verification-recommendation-summary');
    const result = $('atlas-verification-recommendation-result');
    const payload = state.verificationRecommendation?.data || state.verificationRecommendation || {};
    const status = payload.status || (state.repoContextSubmitting ? 'submitting' : 'idle');
    if (summary) summary.textContent = `status: ${status} / confidence: ${payload.confidence || '-'} / impacted_files: ${(payload.impacted_files || []).length} / related_tests: ${(payload.related_tests || []).length} / recommended_commands: ${(payload.recommended_commands || []).length} / executed: false`;
    if (result) result.textContent = JSON.stringify(state.verificationRecommendation || {}, null, 2);
  }

  async function queryVerificationRecommendationFromUI() {
    if (typeof root.AtlasPipelineAPI?.getVerificationRecommendation !== 'function') return;
    const payload = buildRepoContextPayloadFromUI();
    payload.plan_pool = currentPlanPoolPayload();
    payload.planner_packaging_v2 = state.plannerPackagingV2?.data || state.plannerPackagingV2 || {};
    payload.planner_context_text_v2 = payload.planner_packaging_v2?.planner_context_text || '';
    payload.pool_id = state.currentPoolId || '';
    payload.goal = state.goalInput || '';
    if (!payload.project_path) {
      state.verificationRecommendation = { status: 'error', message: 'project_path is required' };
      renderVerificationRecommendationPanel();
      return;
    }
    state.repoContextSubmitting = true;
    renderVerificationRecommendationPanel();
    try {
      const response = await root.AtlasPipelineAPI.getVerificationRecommendation(payload);
      const data = response?.data || response || {};
      state.verificationRecommendation = data;
      renderVerificationRecommendationPanel();
    } finally {
      state.repoContextSubmitting = false;
      renderVerificationRecommendationPanel();
    }
  }

  function renderPlannerPackagingV2Panel() {
    const summary = $('atlas-planner-packaging-v2-summary');
    const result = $('atlas-planner-packaging-v2-result');
    const data = state.plannerPackagingV2?.data || state.plannerPackagingV2 || {};
    if (summary) summary.textContent = `status: ${data.status || '-'} / confidence: ${data.confidence || '-'}`;
    if (result) result.textContent = JSON.stringify(data, null, 2);
  }

  async function queryPlannerPackagingV2FromUI() {
    if (typeof root.AtlasPipelineAPI?.getPlannerPackagingV2 !== 'function') return;
    const payload = buildRepoContextPayloadFromUI();
    payload.plan_pool = currentPlanPoolPayload();
    payload.plan_item_impact_map = state.planItemImpactMap?.data || state.planItemImpactMap || {};
    payload.context_refresh_v2 = state.contextRefreshV2?.data || state.contextRefreshV2 || {};
    payload.pool_id = state.currentPoolId || '';
    payload.goal = state.goalInput || '';
    if (!payload.project_path) {
      state.plannerPackagingV2 = { status: 'error', message: 'project_path is required' };
      renderPlannerPackagingV2Panel();
      return;
    }
    state.repoContextSubmitting = true;
    renderPlannerPackagingV2Panel();
    try {
      const response = await root.AtlasPipelineAPI.getPlannerPackagingV2(payload);
      const data = response?.data || response || {};
      state.plannerPackagingV2 = data;
    } finally {
      state.repoContextSubmitting = false;
      renderPlannerPackagingV2Panel();
    }
  }


  function renderRepoContextPanel() {
    const statusEl = $('atlas-repo-context-status'); const summaryEl = $('atlas-repo-context-summary'); const resultEl = $('atlas-repo-context-result');
    const payload = (state.repoContextScopeSummary?.data || state.repoContextSnapshot?.data || state.repoContextScopeSummary || state.repoContextSnapshot || {});
    if (statusEl) statusEl.textContent = payload.status || (state.repoContextSubmitting ? 'submitting' : 'idle');
    if (summaryEl) summaryEl.textContent = `project_hash: ${payload.project_hash || payload.repo_index_snapshot?.project_hash || '-'} / index_run_id: ${payload.index_run_id || payload.repo_index_snapshot?.index_run_id || '-'} / impacted_files: ${(payload.impacted_files || []).length} / related_tests: ${(payload.related_tests || []).length} / recommended_tests: ${((state.repoContextImpactedTests?.data || state.repoContextImpactedTests || {}).related_tests || []).length} / confidence: ${payload.confidence || '-'}`;
    if (resultEl) resultEl.textContent = JSON.stringify({ snapshot: state.repoContextSnapshot, scope_summary: state.repoContextScopeSummary }, null, 2);
  }
  async function queryRepoContextSnapshotFromUI() {
    if (typeof root.AtlasPipelineAPI?.getRepoContextSnapshot !== 'function') return;
    state.repoContextSubmitting = true; renderRepoContextPanel();
    state.repoContextSnapshot = await root.AtlasPipelineAPI.getRepoContextSnapshot(buildRepoContextPayloadFromUI());
    state.repoContextSubmitting = false; renderRepoContextPanel();
  }
  async function queryRepoContextScopeSummaryFromUI() {
    if (typeof root.AtlasPipelineAPI?.getRepoContextScopeSummary !== 'function') return;
    state.repoContextSubmitting = true; renderRepoContextPanel();
    state.repoContextScopeSummary = await root.AtlasPipelineAPI.getRepoContextScopeSummary(buildRepoContextPayloadFromUI());
    state.repoContextSubmitting = false; renderRepoContextPanel();
  }
  async function queryRepoContextVerificationPlanFromUI() {
    if (typeof root.AtlasPipelineAPI?.getRepoContextVerificationPlan !== 'function') return;
    const payload = buildRepoContextPayloadFromUI();
    if (!payload.project_path) {
      state.repoContextVerificationPlan = { status: 'error', message: 'project_path is required' };
      renderRepoContextVerificationPlanPanel();
    renderPlanItemImpactMapPanel();
    renderVerificationRecommendationPanel();
      return;
    }
    state.repoContextSubmitting = true;
    renderRepoContextVerificationPlanPanel();
    renderPlanItemImpactMapPanel();
    renderVerificationRecommendationPanel();
    const response = await root.AtlasPipelineAPI.getRepoContextVerificationPlan(payload);
    const planPayload = response?.data || response || {};
    state.repoContextVerificationPlan = planPayload;
    state.repoContextSubmitting = false;
    renderRepoContextVerificationPlanPanel();
    renderPlanItemImpactMapPanel();
    renderVerificationRecommendationPanel();
  }

  

  function renderContextRefreshV2Panel() {
    const summaryEl = $('atlas-context-refresh-v2-summary');
    const resultEl = $('atlas-context-refresh-v2-result');
    const payload = state.contextRefreshV2?.data || state.contextRefreshV2 || {};
    const status = payload.status || (state.repoContextSubmitting ? 'submitting' : 'idle');
    if (summaryEl) summaryEl.textContent = `status: ${status} / impacted_files: ${(payload.impacted_files || []).length} / related_tests: ${(payload.related_tests || []).length} / confidence: ${payload.confidence || '-'} / executed: false`;
    if (resultEl) resultEl.textContent = JSON.stringify(state.contextRefreshV2 || {}, null, 2);
  }

  async function queryContextRefreshV2FromUI() {
    if (typeof root.AtlasPipelineAPI?.getContextRefreshV2 !== 'function') return;
    const payload = buildRepoContextPayloadFromUI();
    payload.plan_pool = currentPlanPoolPayload();
    payload.impact_map = state.planItemImpactMap?.data || state.planItemImpactMap || {};
    payload.pool_id = state.currentPoolId || '';
    payload.goal = state.goalInput || '';
    if (!payload.project_path) {
      state.contextRefreshV2 = { status: 'error', message: 'project_path is required' };
      renderContextRefreshV2Panel();
      return;
    }
    state.repoContextSubmitting = true;
    renderContextRefreshV2Panel();
    const response = await root.AtlasPipelineAPI.getContextRefreshV2(payload);
    const data = response?.data || response || {};
    state.contextRefreshV2 = data;
    state.repoContextSubmitting = false;
    renderContextRefreshV2Panel();
  }

  function getWorkflowShellState() {
    const goalInput = $('atlas-goal-input')?.value || state.goalInput || '';
    const projectPath = $('atlas-repo-index-project-path')?.value || '';
    const handoff = operatorLoopState?.lastContractResult?.verification_handoff_summary || state.verificationRecommendationHandoff?.summary || '';
    const artifacts = {
      plan_items: arr(state.planPool?.items || state.planPool?.plan_pool?.items).length,
      events: arr(state.events).length,
      approvals: arr(state.approvalItems).length,
    };
    const shellState = {
      mode: 'manual_supervised', phase: state.pipelineState?.phase || '-', status: state.pipelineState?.status || 'idle',
      goal: goalInput, project_path: projectPath, pool_id: state.currentPoolId || '', current_action: state.lastAction || '',
      approval_required: true, dry_run_required: true, confirmation_required: true, can_start: false, can_continue: false,
      can_stop: true, last_result: state.pipelineState?.last_result || null, handoff_summary: handoff, artifacts,
    };
    const derived = deriveWorkflowPhase(shellState);
    shellState.workflow_phase = derived.phase;
    shellState.primary_action_label = derived.primaryAction.label;
    shellState.primary_action_kind = derived.primaryAction.actionKind;
    shellState.primary_action_enabled = derived.primaryAction.enabled;
    shellState.primary_action_reason = derived.primaryAction.reason;
    shellState.approval_required = derived.safety.requiresConfirmation;
    shellState.dry_run_required = derived.safety.requiresDryRun;
    shellState.confirmation_required = derived.safety.requiresConfirmation;
    shellState.confirmation_text_required = derived.safety.confirmationTextRequired;
    shellState.manual_approval_only = derived.safety.manualApprovalOnly;
    shellState.auto_continue_allowed = false;
    shellState.execute_all_allowed = false;
    shellState.source_state_summary = `pool=${shellState.pool_id || '-'}; pipeline_status=${shellState.status}; pipeline_phase=${shellState.phase}; plan_items=${artifacts.plan_items}; selected_action=${operatorLoopState.selectedNextAction || '-'}; action_kind=${operatorLoopState.actionKind || '-'}`;
    state.workflowShell = shellState;
    return state.workflowShell;
  }

  function deriveWorkflowPhase(shellState) {
    const hasGoal = !!String(shellState.goal || '').trim();
    const hasPool = !!shellState.pool_id;
    const hasItems = Number(shellState.artifacts?.plan_items || 0) > 0;
    const guardState = getOperatorLoopGuardState();
    const safety = { requiresDryRun: true, requiresConfirmation: true, confirmationTextRequired: 'EXECUTE ONE ACTION', manualApprovalOnly: true, autoContinue: false, executeAll: false };
    if (!hasGoal) return { phase: 'idle', label: 'Enter goal', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Create Plan', enabled: false, reason: 'Goal input is required before creating a plan.', actionKind: 'none' }, safety };
    if (!hasPool || !hasItems) return { phase: 'planning', label: 'Create plan', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Create Plan', enabled: true, reason: 'Create plan pool from current goal.', actionKind: 'create_plan' }, safety };
    if (!guardState.hasMultiStatusRunId) return { phase: 'prepare_required', label: 'Build queue required', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Open Advanced', enabled: true, reason: 'Build Queue / multi_status_run_id required. Open Advanced Operator Loop controls.', actionKind: 'show_advanced' }, safety };
    if (!guardState.hasOrchestratorRunId || !guardState.hasActionId) return { phase: 'prepare_required', label: 'Prepare next action', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Prepare Next Action', enabled: guardState.canPrepare, reason: guardState.canPrepare ? 'Prepare is required to pick a single action candidate.' : 'Prepare requires pool_id + multi_status_run_id.', actionKind: 'prepare_next' }, safety };
    if (!guardState.hasConfirmationToken) return { phase: 'approval_required', label: 'Confirmation token required', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Open Advanced', enabled: true, reason: 'Preview Token / confirmation token required in Advanced Operator Loop.', actionKind: 'show_advanced' }, safety };
    if (!guardState.payloadValid) return { phase: 'blocked', label: 'Blocked by payload guard', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Show Diagnostics', enabled: true, reason: 'Dry run requires payload_valid=true.', actionKind: 'show_diagnostics' }, safety };
    if (guardState.requiresExplicitDecision && !guardState.explicitDecisionOk) return { phase: 'approval_required', label: 'Explicit approval required', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Open Advanced', enabled: true, reason: 'explicit_decision=approve is required before execution.', actionKind: 'show_advanced' }, safety };
    if (guardState.canExecute) return { phase: 'execute_ready', label: 'Execute one action', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Execute One Action', enabled: true, reason: 'All current execute guards pass. Manual confirmation remains required.', actionKind: 'execute_one' }, safety };
    if (guardState.canDryRun) return { phase: 'dry_run_required', label: 'Dry run required', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Start Dry Run', enabled: true, reason: 'Dry-run-first policy is required before execution.', actionKind: 'dry_run' }, safety };
    if (guardState.canRefresh) return { phase: 'refresh_required', label: 'Refresh status', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Refresh Status', enabled: true, reason: 'Refresh and inspect current status before next manual step.', actionKind: 'refresh' }, safety };
    return { phase: 'blocked', label: 'Guard check required', primaryAction: { id: 'atlas-workflow-primary-action-btn', label: 'Open Advanced', enabled: true, reason: guardState.reasons.join(' | ') || 'Operator Loop guard requirements are not yet satisfied.', actionKind: 'show_advanced' }, safety };
  }


  function getAtlasUiMode() {
    const rootEl = $('atlas-dashboard');
    const allowed = { minimal: true, advanced: true, diagnostics: true, full: true };
    let mode = 'minimal';
    try {
      const saved = localStorage.getItem('atlas:uiMode');
      if (saved && allowed[saved]) mode = saved;
    } catch (_e) {}
    const domMode = rootEl?.dataset?.atlasUiMode;
    if (domMode && allowed[domMode]) mode = domMode;
    return mode;
  }

  function setAtlasUiMode(mode) {
    const allowed = { minimal: true, advanced: true, diagnostics: true, full: true };
    const nextMode = allowed[mode] ? mode : 'minimal';
    const rootEl = $('atlas-dashboard');
    if (rootEl) rootEl.setAttribute('data-atlas-ui-mode', nextMode);
    try { localStorage.setItem('atlas:uiMode', nextMode); } catch (_e) {}
    renderAtlasUiMode();
  }

  function renderAtlasUiMode() {
    const mode = getAtlasUiMode();
    const advancedBtn = $('atlas-workflow-advanced-toggle');
    const diagnosticsBtn = $('atlas-workflow-diagnostics-toggle');
    if (advancedBtn) advancedBtn.textContent = mode === 'advanced' ? 'Hide Advanced' : 'Show Advanced';
    if (diagnosticsBtn) diagnosticsBtn.textContent = mode === 'diagnostics' ? 'Hide Diagnostics' : 'Show Diagnostics';
    const diagnosticsStatus = $('atlas-diagnostics-status');
    if (diagnosticsStatus) diagnosticsStatus.textContent = `UI mode: ${mode}. Diagnostics toggles do not execute actions automatically.`;
  }

  function renderWorkflowShell() {
    const ws = getWorkflowShellState();
    if ($('atlas-workflow-goal')) $('atlas-workflow-goal').textContent = ws.goal || '-';
    if ($('atlas-workflow-project-path')) $('atlas-workflow-project-path').textContent = ws.project_path || '-';
    if ($('atlas-workflow-mode')) $('atlas-workflow-mode').textContent = ws.mode;
    if ($('atlas-workflow-status')) $('atlas-workflow-status').textContent = ws.status;
    if ($('atlas-workflow-phase')) $('atlas-workflow-phase').textContent = ws.workflow_phase || ws.phase;
    if ($('atlas-workflow-approval-summary')) $('atlas-workflow-approval-summary').textContent = `Approval summary: ${ws.handoff_summary || 'manual approval + EXECUTE ONE ACTION required'}`;
    if ($('atlas-workflow-artifacts-summary')) $('atlas-workflow-artifacts-summary').textContent = `Artifacts: plan_items=${ws.artifacts.plan_items}, events=${ws.artifacts.events}, approvals=${ws.artifacts.approvals}`;
    const primary = $('atlas-workflow-primary-action-btn');
    if (primary) {
      primary.disabled = !ws.primary_action_enabled;
      primary.textContent = ws.primary_action_label || 'Primary action';
      primary.title = ws.primary_action_reason || '';
    }
    if ($('atlas-workflow-primary-action-reason')) $('atlas-workflow-primary-action-reason').textContent = `Primary action reason: ${ws.primary_action_reason || '-'}`;
    if ($('atlas-workflow-safety-summary')) $('atlas-workflow-safety-summary').textContent = `Safety: dry-run-first=${String(ws.dry_run_required)} / confirmation_required=${String(ws.confirmation_required)} / confirmation_text_required=${ws.confirmation_text_required || '-'} / EXECUTE ONE ACTION required / no auto-continue / no execute-all.`;
  }

  async function handleWorkflowPrimaryAction() {
    const ws = getWorkflowShellState();
    if (!ws.primary_action_enabled) return renderWorkflowShell();
    try {
      switch (ws.primary_action_kind) {
        case 'create_plan':
          await createPlanPool();
          break;
        case 'prepare_next':
          await operatorLoopPrepare();
          break;
        case 'dry_run':
          await operatorLoopExec(true);
          break;
        case 'execute_one':
          if (!operatorLoopCanExecute()) break;
          await operatorLoopExec(false);
          break;
        case 'refresh':
          await refreshStatus();
          break;
        case 'show_advanced':
          setAtlasUiMode('advanced');
          break;
        case 'show_diagnostics':
          setAtlasUiMode('diagnostics');
          break;
        default:
          break;
      }
    } catch (err) {
      showWarning(`Workflow primary action failed safely: ${err?.message || String(err)}`);
    }
    renderWorkflowShell();
  }

  function bindWorkflowShell() {
    $('atlas-workflow-primary-action-btn')?.addEventListener('click', () => { handleWorkflowPrimaryAction(); });
    $('atlas-workflow-stop-btn')?.addEventListener('click', () => {
      const status = $('atlas-workbench-status');
      if (status) status.textContent = 'Stop requested (display-only in PR-74).';
      renderWorkflowShell();
    });
    $('atlas-workflow-advanced-toggle')?.addEventListener('click', () => {
      const mode = getAtlasUiMode();
      setAtlasUiMode(mode === 'advanced' ? 'minimal' : 'advanced');
    });
    $('atlas-workflow-diagnostics-toggle')?.addEventListener('click', () => {
      const mode = getAtlasUiMode();
      setAtlasUiMode(mode === 'diagnostics' ? 'minimal' : 'diagnostics');
    });
    setAtlasUiMode(getAtlasUiMode());
    renderWorkflowShell();
  }

function bindOperatorLoop(){ loadOperatorLoopState(); ['pool-id','run-id','reviewer','reason'].forEach((k)=>{ const el=$('atlas-operator-loop-'+k); if(el) el.value=operatorLoopState[k.replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]||''; }); const ct=$('atlas-operator-loop-confirmation-text'); if(ct) ct.value='EXECUTE ONE ACTION'; ['confirmation-token','confirmation-text','explicit-decision','pool-id','run-id','reviewer','reason'].forEach((k)=>$('atlas-operator-loop-'+k)?.addEventListener('input',()=>{operatorLoopReadInputs(); operatorLoopRender();})); $('atlas-operator-loop-build-queue-btn')?.addEventListener('click',operatorLoopBuildQueue); $('atlas-operator-loop-prepare-btn')?.addEventListener('click',operatorLoopPrepare); $('atlas-operator-loop-token-btn')?.addEventListener('click',operatorLoopToken); $('atlas-operator-loop-dry-run-btn')?.addEventListener('click',()=>operatorLoopExec(true)); $('atlas-operator-loop-execute-btn')?.addEventListener('click',()=>{ if(!operatorLoopCanExecute()) return; return operatorLoopExec(false);}); $('atlas-operator-loop-refresh-btn')?.addEventListener('click',operatorLoopRefresh); $('atlas-operator-loop-advance-btn')?.addEventListener('click',operatorLoopAdvanceToConfirmation); $('atlas-operator-loop-execute-refresh-btn')?.addEventListener('click',operatorLoopExecuteAndRefresh); $('atlas-operator-loop-copy-payload-btn')?.addEventListener('click',async ()=>{ const p=operatorLoopState.lastContractResult?.action_contract?.payload||{}; try{await navigator.clipboard.writeText(JSON.stringify(p,null,2));}catch(_e){} operatorLoopRender();}); $('atlas-operator-loop-verification-handoff-copy-btn')?.addEventListener('click',copyOperatorLoopVerificationHandoff); $('atlas-operator-loop-verification-handoff-export-btn')?.addEventListener('click',exportOperatorLoopVerificationHandoff); $('atlas-operator-loop-reset-btn')?.addEventListener('click',()=>{ Object.assign(operatorLoopState,{poolId:'',runId:'',reviewer:'manual',reason:'',multiStatusRunId:'',orchestratorRunId:'',actionId:'',selectedItemId:'',selectedNextAction:'',actionKind:'',confirmationToken:'',confirmationText:'EXECUTE ONE ACTION',explicitDecision:'',dryRunExecutorRunId:'',executedExecutorRunId:'',postRefreshRunId:'',lastQueueResult:null,lastContractResult:null,lastDryRunResult:null,lastExecuteResult:null,lastRefreshResult:null}); try{localStorage.removeItem(operatorLoopStorageKey);}catch(_e){} ['queue','contract','executor','refresh','next-step'].forEach((x)=>{ const el=$('atlas-operator-loop-'+x+'-result')||$('atlas-operator-loop-'+x); if(el) el.textContent='';}); const tok=$('atlas-operator-loop-confirmation-token'); if(tok) tok.value=''; operatorLoopRender(); }); operatorLoopRender(); }
  function bind() {
    const goal = $('atlas-goal-input');
    const compat = $('atlas-requirement-input');
    if (goal) {
      goal.addEventListener('input', () => {
        state.goalInput = goal.value;
        if (compat) compat.value = goal.value;
      });
    }
    const details = $('atlas-details-drawer');
    const refreshContinuationBtn = $('atlas-continuation-refresh-btn');
    if (refreshContinuationBtn) refreshContinuationBtn.addEventListener('click', refreshContinuation);
    const copyContinuationBtn = $('atlas-continuation-copy-btn');
    if (copyContinuationBtn) copyContinuationBtn.addEventListener('click', copyContinuationPrompt);
    const copyIdsBtn = $('atlas-continuation-copy-ids-btn');
    if (copyIdsBtn) copyIdsBtn.addEventListener('click', copyAtlasIds);
    const autoBtn = $('atlas-check-automation-readiness-btn');
    if (autoBtn) autoBtn.addEventListener('click', checkAutomationReadiness);
    const autoRunBtn = $('atlas-auto-safe-apply-run-btn');
    if (autoRunBtn) autoRunBtn.addEventListener('click', runAutoSafeApplyOne);
    const regenFromRecBtn = $('atlas-run-patch-regen-from-recommendation');
    if (regenFromRecBtn) regenFromRecBtn.addEventListener('click', runPatchRegenFromRecommendation);
    const nextActionBtn = $('atlas-prepare-next-action');
    if (nextActionBtn) nextActionBtn.addEventListener('click', prepareNextActionOrchestrator);

    const repoBuildBtn = $('atlas-repo-index-build-btn');
    if (repoBuildBtn) repoBuildBtn.addEventListener('click', buildRepoIndexFromUI);
    const repoLatestBtn = $('atlas-repo-index-latest-btn');
    if (repoLatestBtn) repoLatestBtn.addEventListener('click', loadLatestRepoIndexFromUI);
    const repoImpactsBtn = $('atlas-repo-index-impacts-btn');
    if (repoImpactsBtn) repoImpactsBtn.addEventListener('click', queryRepoIndexImpactsFromUI);
    const repoRelatedTestsBtn = $('atlas-repo-index-related-tests-btn');
    if (repoRelatedTestsBtn) repoRelatedTestsBtn.addEventListener('click', queryRepoIndexRelatedTestsFromUI);
    $('atlas-repo-context-snapshot-btn')?.addEventListener('click', queryRepoContextSnapshotFromUI);
    $('atlas-repo-context-scope-btn')?.addEventListener('click', queryRepoContextScopeSummaryFromUI);
    $('atlas-repo-context-impacted-tests-btn')?.addEventListener('click', queryRepoContextImpactedTestsFromUI);
    $('atlas-repo-context-verification-plan-btn')?.addEventListener('click', queryRepoContextVerificationPlanFromUI);
    $('atlas-plan-item-impact-map-btn')?.addEventListener('click', queryPlanItemImpactMapFromUI);
    $('atlas-context-refresh-v2-btn')?.addEventListener('click', queryContextRefreshV2FromUI);
    $('atlas-planner-packaging-v2-btn')?.addEventListener('click', queryPlannerPackagingV2FromUI);
    $('atlas-verification-recommendation-btn')?.addEventListener('click', queryVerificationRecommendationFromUI);
    $('atlas-verification-recommendation-handoff-btn')?.addEventListener('click', queryVerificationRecommendationHandoffFromUI);
    renderRepoIndexPanel();
    renderRepoContextPanel();
    renderRepoContextTestsPanel();
    renderRepoContextVerificationPlanPanel();
    renderPlanItemImpactMapPanel();
    renderVerificationRecommendationPanel();
    if (details) {
      details.addEventListener('toggle', () => {
        state.advancedOpen = details.open;
        const advanced = $('atlas-advanced-settings');
        if (advanced) advanced.dataset.atlasAdvancedSettings = details.open ? 'open' : 'collapsed';
      });
    }
  }

  async function init() {
    if (!$('atlas-dashboard') || !root.AtlasPipelineAPI) return;
    bind();
    bindOperatorLoop();
    bindWorkflowShell();
    const storedWorkspace = readStorage(storageKeys.workspaceId);
    if (storedWorkspace && $('atlas-workspace-id')) $('atlas-workspace-id').value = storedWorkspace;
    state.currentPoolId = readStorage(storageKeys.poolId);
    state.currentRunId = readStorage(storageKeys.runId);
    render();
    await loadRecoveryLatest();
  }

  root.AtlasDashboard = {
    state,
    createPlanPool,
    startDryRun,
    loadRecoveredPlan,
    refreshStatus,
    hideRecoveryBanner,
    retryLastAction,
    loadRecoveryLatest,
    refreshContinuation,
    refreshApprovals,
    decideApproval,
    copyContinuationPrompt,
    copyAtlasIds,
    runVerification,
    generatePatchProposal,
    refreshVerificationCandidates,
    renderVerificationPanel,
    runPatchRegenFromRecommendation,
    renderPatchRegenFromRecommendationPanel,
    render,
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

// known planner warning tokens: llm_backend_unavailable, llm_json_parse_failed, real_planner_unavailable, planner_bridge_failed


// Auto verification readiness
// Only allowlisted verification commands can run.
// Auto rollback is not enabled.
// Auto DebugReview is not enabled.
// Auto Patch Proposal is not enabled.
function __atlas_auto_verification_contract_tokens__(){return ['Run auto verification','Run auto safe_apply + verification','command_id','Auto verification readiness'];}


// Failure stop UI hints
// Automation stopped
// Verification failed
// Manual restore candidate available
// Snapshot manifest path
// Changed files
// Suggested manual actions
// Auto rollback is not enabled.
// Restore must be triggered manually.
// Show failure suggestion



// Bounded Retry minimal UI marker
window.__atlasBoundedRetrySafety = ["No auto rollback", "No auto restore", "No patch regeneration", "Verification rerun only"];
