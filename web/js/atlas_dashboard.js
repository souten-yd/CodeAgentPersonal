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
    advancedOpen: false,
    logsOpen: false,
    markdownOpen: false,
    jsonOpen: false,
    lastAction: null,
    recoveryHidden: false,
    restored: false,
    checkpointPath: '',
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

  function statusClass(status) {
    const s = String(status || '').toLowerCase();
    if (s === 'completed' || s === 'success') return 'success';
    if (['ready', 'running', 'researching', 'executing', 'testing', 'created'].includes(s)) return 'active';
    if (s === 'queued' || s === 'idle' || !s) return 'muted';
    if (s === 'approval_required' || s === 'paused') return 'warning';
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
    ['atlas-create-plan-btn', 'atlas-start-dry-run-btn', 'atlas-recovery-load-btn', 'atlas-recovery-refresh-btn'].forEach((id) => {
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

  function updateSummary() {
    const pool = normalizePool(state.planPool);
    const pipeline = normalizePipeline(state.pipelineState);
    const items = getItems();
    const event = lastEvent();
    const completed = arr(pipeline?.completed_item_ids).length || arr(pool?.completed_item_ids).length;
    const total = items.length;
    const status = pipeline?.status || pool?.status || 'Ready';
    const fill = total ? Math.round((completed / total) * 100) : 0;
    const failed = arr(pipeline?.failed_item_ids).length || arr(pool?.failed_item_ids).length;
    const blocked = arr(pipeline?.blocked_item_ids).length || arr(pool?.blocked_item_ids).length;

    if ($('atlas-workbench-summary-last-run')) $('atlas-workbench-summary-last-run').textContent = state.currentRunId || '-';
    if ($('atlas-workbench-summary-status')) $('atlas-workbench-summary-status').textContent = status;
    if ($('atlas-workbench-status')) $('atlas-workbench-status').textContent = state.loading ? 'Atlas is working...' : `PlanPool: ${pool?.status || 'not created'} / Pipeline: ${pipeline?.status || 'idle'}`;
    if ($('atlas-status-planpool')) $('atlas-status-planpool').textContent = pool?.status || 'not created';
    if ($('atlas-status-items')) $('atlas-status-items').textContent = String(total);
    if ($('atlas-status-pipeline')) $('atlas-status-pipeline').textContent = pipeline?.status || 'idle';
    if ($('atlas-status-last-event')) $('atlas-status-last-event').textContent = eventLabel(event);
    if ($('atlas-planpool-id')) $('atlas-planpool-id').textContent = state.currentPoolId || 'No pool';
    if ($('atlas-pipeline-run-id')) $('atlas-pipeline-run-id').textContent = state.currentRunId || 'No run';
    if ($('atlas-progress-fill')) $('atlas-progress-fill').style.width = `${fill}%`;
    if ($('atlas-progress-text')) $('atlas-progress-text').textContent = `${completed} / ${total} completed`;
    if ($('atlas-failed-count')) $('atlas-failed-count').textContent = String(failed);
    if ($('atlas-blocked-count')) $('atlas-blocked-count').textContent = String(blocked);
    if ($('atlas-current-item-id')) $('atlas-current-item-id').textContent = pipeline?.current_item_id || pool?.current_item_id || '-';
    if ($('atlas-next-action')) $('atlas-next-action').textContent = deriveNextAction(pool, pipeline);
    renderPipelineStatusBadge(pipeline?.status || 'idle');
  }

  function deriveNextAction(pool, pipeline) {
    const recoveryNext = state.recoverySummary?.next_action;
    if (recoveryNext) return recoveryNext;
    const status = pipeline?.status || '';
    if (status === 'completed') return 'Review final report or start next plan.';
    if (status === 'failed') return 'Inspect failed items in Details and prepare a follow-up plan.';
    if (status === 'paused') return 'Review paused item before continuing.';
    if (state.currentPoolId && !state.currentRunId) return 'Start Dry-run to validate the PlanPool.';
    if (!pool) return 'Create a PlanPool to begin.';
    return 'Review PlanItem cards and dry-run status.';
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
    const json = { planPool: normalizePool(state.planPool), pipelineState: normalizePipeline(state.pipelineState), recoverySummary: state.recoverySummary };
    if ($('atlas-json-panel')) $('atlas-json-panel').textContent = JSON.stringify(json, null, 2);
    if ($('atlas-markdown-panel')) $('atlas-markdown-panel').textContent = state.markdown || 'No markdown loaded.';
    if ($('atlas-checkpoint-path')) $('atlas-checkpoint-path').textContent = state.checkpointPath || 'No checkpoint yet.';
  }

  function renderRecovery() {
    const banner = $('atlas-recovery-banner');
    if (!banner) return;
    const recovery = state.recoverySummary;
    const status = recovery?.status || recovery?.pipeline_status || recovery?.reason || '';
    const shouldShow = recovery && !state.recoveryHidden && !['no_workspace', 'no_plan_pool', ''].includes(status);
    banner.hidden = !shouldShow;
    if (shouldShow && $('atlas-recovery-summary')) {
      $('atlas-recovery-summary').textContent = `status: ${status} / pool_id: ${recovery.pool_id || '-'} / run_id: ${recovery.run_id || '-'} / next: ${recovery.next_action || '-'}`;
    }
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
      state.currentPoolId = data.pool_id;
      state.currentRunId = '';
      state.planPool = data.plan_pool || data;
      state.pipelineState = null;
      state.events = [];
      state.checkpointPath = data.checkpoint_path || '';
      writeStorage(storageKeys.poolId, state.currentPoolId);
      await loadMarkdown();
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
      state.currentRunId = data.run_id;
      state.pipelineState = data;
      state.events = arr(data.events);
      state.checkpointPath = data.checkpoint_path || state.checkpointPath;
      writeStorage(storageKeys.runId, state.currentRunId);
      await refreshStatus();
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
      const data = await handleResult(await root.AtlasPipelineAPI.getPipelineStatus(state.currentPoolId, state.currentRunId, workspaceId()), 'Refresh Status failed');
      if (data) {
        state.pipelineState = normalizePipeline(data);
        state.events = arr(data.events).length ? arr(data.events) : arr(state.pipelineState?.events);
      }
      const events = await root.AtlasPipelineAPI.getPipelineEvents(state.currentPoolId, state.currentRunId, workspaceId());
      if (events?.ok) state.events = arr(events.data?.events);
    }
    render();
  }

  async function loadRecoveryLatest() {
    const result = await root.AtlasPipelineAPI.getRecoveryLatest(workspaceId());
    if (!result?.ok) return;
    const recovery = result.data?.recovery_summary || result.data;
    state.recoverySummary = recovery;
    const recoveredPool = recovery?.pool_id || readStorage(storageKeys.poolId);
    const recoveredRun = recovery?.run_id || readStorage(storageKeys.runId);
    if (recoveredPool) state.currentPoolId = recoveredPool;
    if (recoveredRun) state.currentRunId = recoveredRun;
    if (recoveredPool || recoveredRun) state.restored = true;
    if (state.currentPoolId) await refreshStatus();
    render();
  }

  async function loadRecoveredPlan() {
    state.recoveryHidden = false;
    const recovery = state.recoverySummary || {};
    if (recovery.pool_id) state.currentPoolId = recovery.pool_id;
    if (recovery.run_id) state.currentRunId = recovery.run_id;
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
    render,
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
