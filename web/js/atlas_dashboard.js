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
  };

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const arr = (value) => Array.isArray(value) ? value : [];

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
    if ($('atlas-progress-text')) $('atlas-progress-text').textContent = `${completed} / ${total} completed`;
    if ($('atlas-failed-count')) $('atlas-failed-count').textContent = String(failed);
    if ($('atlas-blocked-count')) $('atlas-blocked-count').textContent = String(blocked);
    if ($('atlas-current-item-id')) $('atlas-current-item-id').textContent = pipeline?.current_item_id || pool?.current_item_id || '-';
    if ($('atlas-next-action')) $('atlas-next-action').textContent = deriveNextAction(pool, pipeline);
    updateActionButtons();
    renderPipelineStatusBadge(status || (state.recoveryWarning ? 'stale' : 'idle'));
  }

  function deriveNextAction(pool, pipeline) {
    if (state.orchestrationSummary?.next_action) return state.orchestrationSummary.next_action;
    const recoveryNext = state.recoverySummary?.next_action;
    if (state.recoveryWarning) return 'Start a new dry-run from the recovered PlanPool.';
    if (recoveryNext) return recoveryNext;
    const status = pipeline?.status || '';
    if (status === 'completed') return 'Review final report or start next plan.';
    if (status === 'failed') return 'Inspect failed items in Details and prepare a follow-up plan.';
    if (status === 'paused' || status === 'approval_required') return 'Review approval-required items before continuing.';
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
      $('atlas-recovery-summary').textContent = `status: ${status} / pool_id: ${recovery.pool_id || '-'} / run_id: ${state.currentRunId || recovery.run_id || '-'} / next: ${recovery.next_action || '-'}${warning}`;
    }
    const loadBtn = $('atlas-recovery-load-btn');
    const refreshBtn = $('atlas-recovery-refresh-btn');
    if (loadBtn) loadBtn.disabled = Boolean(state.loading || !recovery?.pool_id);
    if (refreshBtn) refreshBtn.disabled = Boolean(state.loading || !state.currentRunId || state.recoveryWarning);
  }

  function render() {
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
      applyOrchestrationSummary(result.data?.orchestration_summary);
      state.continuationPrompt = result.data?.continuation_prompt || state.continuationPrompt;
      await refreshPlanPool();
    } else {
      showWarning(result.message || 'Debug review failed');
    }
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
      return `<div class="atlas-approval-item"><div><strong>${esc(item.item_id)}</strong> ${esc(item.title||'')}</div><div>Status: ${esc(status)} / Root cause: ${esc(review.root_cause_category||'')}<br>Proposed fix: ${esc(review.proposed_fix||'')}</div><button class="atlas-secondary-btn" data-debug-review-item="${esc(item.item_id)}" ${state.debugReviewSubmitting?'disabled':''}>Run Debug Review</button></div>`;
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
      state.patchProposalApprovalResults[itemId] = result.data || {};
      applyOrchestrationSummary(result.data?.orchestration_summary);
      state.continuationPrompt = result.data?.continuation_prompt || state.continuationPrompt;
      await refreshPlanPool();
    } else showWarning(result.message || 'Patch proposal approval failed');
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
    } else {
      showWarning(result.message || 'Patch proposal generation failed');
    }
    renderPatchProposalPanel();
  }

  function renderPatchProposalPanel() {
    const el = $('atlas-patch-proposal-list');
    if (!el) return;
    const rows = state.patchProposalCandidates || [];
    if (!rows.length) { el.innerHTML = '<div class="atlas-muted">No DebugReview analyzed items with proposed fix.</div>'; return; }
    el.innerHTML = rows.map((item) => {
      const existing = item?.metadata?.patch_proposal || {};
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
      const statusNote = status === 'approved'
        ? '<br>Approved. No patch has been applied yet. Next step: convert to manual safe_apply PlanItem draft.'
        : (status === 'rejected' ? '<br>Rejected. No patch has been applied.' : '');
      return `<div class="atlas-approval-item"><div><strong>${esc(item.item_id)}</strong> ${esc(item.title||'')}</div><div>Proposed fix: ${esc(item?.metadata?.debug_review?.proposed_fix||'')}<br>Proposal status: ${esc(status)}<br>Proposal summary: ${esc(summary)}<br>Target files: ${esc(targetFiles)}<br>Risk: ${esc(risk)}<br>Proposal MD: ${esc(mdPath)}<br>Approval reason: ${esc(reason)}${statusNote}</div><textarea data-patch-proposal-reason="${esc(item.item_id)}" placeholder="reason">${esc(reason)}</textarea>${generateBtn}${decisionActions}</div>`;
    }).join('');
    el.querySelectorAll('button[data-patch-proposal-item]:not([data-patch-proposal-decision])').forEach((btn)=>btn.addEventListener('click',()=>generatePatchProposal(btn.getAttribute('data-patch-proposal-item')||'')));
    el.querySelectorAll('button[data-patch-proposal-decision]').forEach((btn)=>btn.addEventListener('click',()=>decidePatchProposal(btn.getAttribute('data-patch-proposal-item')||'', btn.getAttribute('data-patch-proposal-decision')||'')));
  }
  function renderVerificationPanel() {
    const host = $('atlas-verification-list');
    if (!host) return;
    const items = arr(state.verificationCandidates);
    if (!items.length) { host.innerHTML = 'No verification candidates.'; return; }
    host.innerHTML = items.map((item)=>{
      const status = state.verificationResults[item.item_id]?.status || item?.metadata?.verification?.status || '-';
      return `<div class="atlas-question-card"><b>${esc(item.item_id)}</b> ${esc(item.title||'')} <span class="atlas-badge">status: ${esc(status)}</span><div class="atlas-clarification-actions"><button data-verify="${esc(item.item_id)}" type="button">Run Verification</button></div></div>`;
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
    if (response.status === 'passed') showSuccess('Verification passed: '+itemId);
    else if (response.status === 'failed') showWarning('Verification failed: '+itemId+' (DebugLoop is not automatically started.)');
    else showWarning('Verification blocked: '+itemId+' ('+(response.warnings||[]).join(',')+')');
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
      return `<div class="atlas-question-card"><b>${esc(item.item_id)}</b> ${esc(item.title||'')}<textarea data-approval-reason="${esc(item.item_id)}" placeholder="reason"></textarea><div class="atlas-clarification-actions"><button data-approval="approved" data-item-id="${esc(item.item_id)}" type="button">Approve</button><button data-approval="rejected" data-item-id="${esc(item.item_id)}" type="button">Reject</button><button data-approval="needs_revision" data-item-id="${esc(item.item_id)}" type="button">Needs revision</button>${safeApplyHtml}</div></div>`;
    }).join('');
    const candidateHtml = candidateItems.map((item)=>{
      const safeApplyHtml = renderSafeApplyEligibility(item);
      const applied = String(item?.status || '').toLowerCase() === 'completed';
      return `<div class="atlas-question-card"><b>${esc(item.item_id)}</b> ${esc(item.title||'')} <span class="atlas-badge">Approved candidate</span><div class="atlas-clarification-actions">${applied ? '<small>Already applied</small>' : safeApplyHtml}<small>Item-level manual apply only. Tests and autopilot continuation are not run. If no implementation executor is connected, Atlas will block normal apply or simulate only in dry-run mode.</small></div></div>`;
    }).join('');
    if (!pendingHtml && !candidateHtml) { listEl.innerHTML = 'No approval-required items.'; return; }
    listEl.innerHTML = `<h4>Pending approval items</h4>${pendingHtml || '<small>None</small>'}<h4>Manual safe apply candidates</h4>${candidateHtml || '<small>None</small>'}`;
    listEl.querySelectorAll('button[data-approval]').forEach((btn)=>btn.addEventListener('click', ()=>decideApproval(btn.dataset.itemId, btn.dataset.approval)));
    listEl.querySelectorAll('button[data-safe-apply]').forEach((btn)=>btn.addEventListener('click', ()=>executeSafeApply(btn.dataset.safeApply)));
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
    if (response.status === 'applied') showSuccess('Manual safe apply completed for item: '+itemId);
    else if (response.status === 'simulated') showWarning('Simulated only. No files were applied. item: '+itemId);
    else if (response.status === 'blocked') showWarning('Manual safe apply blocked for item: '+itemId+' ('+(response.warnings||[]).join(',')+')');
    else showError('Manual safe apply failed for item: '+itemId+' ('+(response.warnings||[]).join(',')+')');
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
    render,
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

// known planner warning tokens: llm_backend_unavailable, llm_json_parse_failed, real_planner_unavailable, planner_bridge_failed
