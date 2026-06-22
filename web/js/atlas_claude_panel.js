/* eslint-disable no-undef */
/**
 * Atlas Claude-Code-style buildless conversational panel.
 *
 * Exposes window.AtlasClaudePanel. The shell renders inside #atlas-claude-col
 * which is the only user-visible Atlas shell after POST-SCALE-160-UI-DEFAULT
 * -RECONFIRM. The legacy #atlas-panel-col stays in DOM (hidden) so
 * AtlasDashboard JS lookups still resolve.
 *
 * Backend authority is preserved: every action maps to an existing
 * AtlasPipelineAPI method or to a backend route. Profile selection alone never
 * starts or pre-authorizes an autonomous loop; bounded autonomous execution
 * requires backend workflow state, an active bounded envelope, and gates.
 */
(function () {
  'use strict';
  const root = (typeof window !== 'undefined' ? window : globalThis);
  const STORAGE_LAST_GOAL_KEY = 'atlas_claude_last_goal';
  const STORAGE_LAST_POOL_ID_KEY = 'atlas_claude_last_pool_id';
  const STORAGE_LAST_RUN_ID_KEY = 'atlas_claude_last_run_id';
  const STORAGE_LAST_EVENT_SEQUENCE_KEY = 'atlas_claude_last_event_sequence';
  const TRANSCRIPT_MAX_MESSAGES = 200;
  const POLL_INTERVAL_MS = 8000;
  const PROGRESS_STALE_AFTER_SECONDS = 30;
  const CONFIRM_TEXT = 'SELECT AUTOMATION PROFILE';

  const state = {
    initialized: false,
    active: false,
    pollTimer: null,
    transcript: [],
    presets: [],
    envelopes: [],
    selectedPresetId: 'autonomous_bounded_dev',
    workTarget: 'software_development_or_repair',
    latestSafetyProfile: null,
    latestEnvelope: null,
    workflowState: null,
    dismissedApprovalPlanKeys: new Set(),
    activePresetActive: false,
    // Active Atlas project. name doubles as the workspace_id; projectPath is the
    // working dir the autopilot operates on. Set by app.js's project picker.
    activeProject: { name: '', projectPath: '', workspaceId: 'default' },
    provisional: false,
    loadedProject: '',
    // True while loadProject() re-renders persisted/server state on reload. Render-time status
    // messages (e.g. "Plan was created…", approval prompts) must NOT be re-persisted during a
    // restore, or every reload appends another copy to the conversation log forever.
    restoring: false,
  };

  const dom = {};

  function $(id) {
    return document.getElementById(id);
  }

  // ── Project / persistence helpers ──
  function workspaceId() {
    return (state.activeProject && state.activeProject.workspaceId) || 'default';
  }

  // The selected project's working directory. Threaded into plan creation so generated files land in
  // the project the user sees (and downloads), not a divergent fallback workspace.
  function projectPath() {
    return (state.activeProject && state.activeProject.projectPath) || '';
  }

  function projectName() {
    return (state.activeProject && state.activeProject.name) || '';
  }

  // Called by app.js's picker when a project is selected / created / renamed.
  function setActiveProject(project) {
    if (!project) return;
    const name = project.name || '';
    state.activeProject = {
      name,
      projectPath: project.projectPath || project.project_path || state.activeProject.projectPath || '',
      workspaceId: project.workspaceId || project.workspace_id || name || 'default',
    };
    if (Object.prototype.hasOwnProperty.call(project, 'provisional')) {
      state.provisional = !!project.provisional;
    }
  }

  async function persistMessage(role, text, meta) {
    const name = projectName();
    if (!name) return;
    try {
      await fetch('/api/atlas/projects/' + encodeURIComponent(name) + '/conversation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, text: String(text == null ? '' : text), meta: meta || null }),
      });
    } catch (_err) { /* persistence is best-effort */ }
  }

  function persistMeta(meta) {
    // Update server-side meta (active_pool_id / latest_autopilot_run_id) without
    // a visible transcript line. Empty-text messages are skipped on reload.
    if (!meta) return;
    persistMessage('system', '', meta);
  }

  function slugifyGoal(text) {
    let s = String(text || '').trim().toLowerCase();
    // Keep unicode letters/digits (so Japanese goals stay identifiable),
    // collapse everything else to '-'. Mirrors the backend _normalize_name.
    s = s.replace(/[^\p{L}\p{N}_-]+/gu, '-').replace(/-{2,}/g, '-').replace(/^[-_]+|[-_]+$/g, '');
    if (s.length > 16) s = s.slice(0, 16).replace(/[-_]+$/, '');
    return s || 'task';
  }

  // B: rename the provisional project to a short slug derived from the first
  // real instruction. Runs once (while provisional), retries on name conflict.
  async function maybeAutoRename(text) {
    if (!state.provisional) return;
    const current = projectName();
    if (!current) return;
    const slug = slugifyGoal(text);
    if (!slug || slug === current) { state.provisional = false; return; }
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const target = attempt === 0 ? slug : `${slug}-${attempt + 1}`;
      try {
        const resp = await fetch('/api/atlas/projects/' + encodeURIComponent(current) + '/rename', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_name: target }),
        });
        if (resp.ok) {
          const data = await resp.json();
          state.provisional = false;
          setActiveProject(data);
          try { root.KASANE_ATLAS_PROJECT_PATH?.applyRenamed?.(data); } catch (_err) {}
          return;
        }
        if (resp.status === 409) continue;
        return;
      } catch (_err) { return; }
    }
  }

  // C: thin-client restore — fetch the persisted transcript + meta for a project
  // and re-render plan/run state so a browser reload loses nothing.
  async function loadProject(name) {
    const target = name || projectName();
    if (!target) return;
    state.loadedProject = target;
    state.activeProject.name = target;
    if (!state.activeProject.workspaceId) state.activeProject.workspaceId = target;
    if (dom.transcript) dom.transcript.innerHTML = '';
    state.transcript = [];
    let restored = false;
    let poolRestored = false;
    state.restoring = true;
    try {
    try {
      const resp = await fetch('/api/atlas/projects/' + encodeURIComponent(target) + '/conversation', { headers: { 'Content-Type': 'application/json' } });
      if (resp.ok) {
        const data = await resp.json();
        state.provisional = !!(data.meta && data.meta.provisional);
        (data.messages || []).forEach((m) => {
          if (!m || !m.text) return;
          // Skip legacy render-time status lines that an earlier bug persisted on every reload
          // (e.g. "Plan was created. Use Recover to view it."). They are not real conversation; the
          // plan/progress is re-rendered from authoritative server state below.
          if (isTransientStatusMessage(m)) return;
          appendMessage(m.role, m.text, false);
          restored = true;
        });
        const poolId = data.meta && data.meta.active_pool_id;
        if (poolId) {
          await renderPlanPoolMarkdown(poolId);
          await restoreLatestRun(poolId);
          // appendStageBlock auto-scrolled to the stage block; scroll back so the plan card
          // is visible — user can scroll down to reach failure recovery and execution details.
          if (dom.transcript) dom.transcript.scrollTop = 0;
          restored = true;
          poolRestored = true;
        }
      }
    } catch (err) {
      console.warn('Atlas project restore failed', err);
    }
    // The conversation may not carry an active_pool_id (never persisted, or the run was started in a
    // prior session) even when chat messages exist. Ask the SERVER for THIS project's latest pool/run,
    // scoped by workspace, so an in-progress *or* finished run still restores its progress indicator
    // on reload. This is project-scoped and server-authoritative — it never resurrects another (e.g.
    // deleted) project's pool the way the old global localStorage hint did, and it is the natural
    // extension point for fetching multiple parallel pools per project later.
    if (!poolRestored) {
      try {
        const wsId = state.activeProject.workspaceId || target;
        if (root.AtlasPipelineAPI && root.AtlasPipelineAPI.getContinuationLatest) {
          const latest = await root.AtlasPipelineAPI.getContinuationLatest(wsId);
          const latestPoolId = latest && latest.ok && latest.data ? String(latest.data.pool_id || '') : '';
          if (latestPoolId) {
            await renderPlanPoolMarkdown(latestPoolId);
            await restoreLatestRun(latestPoolId);
            if (dom.transcript) dom.transcript.scrollTop = 0;
            restored = true;
            poolRestored = true;
          }
        }
      } catch (err) {
        console.warn('Atlas latest-pool restore failed', err);
      }
    }
    if (!poolRestored) {
      // No server-side pool for this project: drop any stale global hints so a later no-project
      // reload cannot resurrect a deleted pool, then fall through to the empty prompt.
      try {
        localStorage.removeItem(STORAGE_LAST_POOL_ID_KEY);
        localStorage.removeItem(STORAGE_LAST_RUN_ID_KEY);
        localStorage.removeItem(STORAGE_LAST_EVENT_SEQUENCE_KEY);
      } catch (_) {}
    }
    if (!restored) pushSystemMessage('指示を入力してください');
    } finally {
      state.restoring = false;
    }
  }

  async function restoreLatestRun(poolId) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.getLatestMultiItemAutopilotResult) return;
    let runtime = null;
    try {
      runtime = await loadRuntimeStatus(poolId);
      if (runtime) renderRuntimeStatusPanel(runtime);
      try {
        await restoreRuntimeProgressReplay(poolId, runtime);
      } catch (replayErr) {
        console.warn('Atlas runtime progress replay failed', replayErr);
        renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
          run_id: progressRunIdFromRuntime(runtime),
          phase: (runtime && runtime.phase) || 'patch_generation',
          status: 'running',
          message: 'Progress replay unavailable; showing latest runtime snapshot',
          runtime_connection_state: 'stale',
          next_actions: ['wait', 'refresh'],
          authoritative_source: 'PlanPool runtime-status endpoint',
        }));
      }
    } catch (err) {
      console.warn('Atlas runtime status restore failed', err);
      renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
        phase: 'failed',
        status: 'failed',
        message: 'Run status unavailable',
        error: `endpoint=/api/atlas/plan-pools/${poolId}/runtime-status`,
        requires_user_action: true,
        next_actions: ['retry', 'revise plan', 'cancel'],
      }));
    }
    try {
      const peek = await root.AtlasPipelineAPI.getLatestMultiItemAutopilotResult({ pool_id: poolId });
      const hasAutopilotResult = peek && peek.ok && peek.data && (
        peek.data.autopilot_run_id || peek.data.run_id
        || Number.isFinite(Number(peek.data.processed_count))
        || Number.isFinite(Number(peek.data.completed_count))
        || Number.isFinite(Number(peek.data.failed_count))
      );
      if (hasAutopilotResult) {
        const d = peek.data;
        const stages = appendStageBlock(poolId);
        if (stages) {
          ['plan', 'patch', 'approve'].forEach((s) => updateStage(stages, s, 'done', ''));
          updateStage(stages, 'apply', 'done', `${d.processed_count || 0} processed`);
          const verifyStatus = (d.failed_count || 0) === 0 ? 'done' : 'failed';
          updateStage(stages, 'verify', verifyStatus, `pass ${d.completed_count || 0} / fail ${d.failed_count || 0}`);
          renderPipelineSummary(stages, d);
        }
      }
    } catch (err) {
      console.warn('Atlas latest autopilot restore failed', err);
    }
    await restoreLatestAutonomousRun(poolId);
  }

  function progressRunIdFromRuntime(runtime) {
    const patch = (runtime && runtime.patch_generation) || {};
    return String(patch.run_id || (runtime && runtime.run_id) || '');
  }

  function progressPhaseForRuntime(event) {
    const phase = String((event && event.phase) || '').toLowerCase();
    const eventType = String((event && event.event_type) || '').toLowerCase();
    const status = String((event && event.status) || '').toLowerCase();
    if (eventType === 'atlas_run_completed') return 'completed';
    if (eventType === 'atlas_run_failed' || status === 'failed') return 'failed';
    if (phase.includes('verif')) return 'verifying';
    if (phase.includes('apply')) return 'applying';
    if (phase.includes('plan')) return 'planning';
    if (status === 'completed' && !phase.includes('patch')) return 'completed';
    return phase || 'patch_generation';
  }

  function lc(value) {
    return String(value || '').toLowerCase();
  }

  function progressAgeSeconds(timestamp, fallback) {
    if (timestamp) {
      const parsed = Date.parse(timestamp);
      if (Number.isFinite(parsed)) return Math.max(0, Math.round((Date.now() - parsed) / 1000));
    }
    const direct = Number(fallback);
    return Number.isFinite(direct) ? Math.max(0, Math.round(direct)) : null;
  }

  function classifyRuntimeConnectionState(detail) {
    const explicit = lc(detail && (detail.connectionState || detail.runtime_connection_state || detail.progress_state));
    if (['live', 'reconnecting', 'stale', 'stalled', 'terminal', 'unknown'].includes(explicit)) return explicit;
    const status = lc(detail && (detail.status || detail.state));
    const phase = lc(detail && detail.phase);
    const eventType = lc(detail && (detail.event_type || detail.eventType));
    if (['completed', 'failed', 'cancelled', 'canceled'].includes(status)
      || ['completed', 'failed', 'cancelled', 'canceled'].includes(phase)
      || eventType.endsWith('_completed') || eventType.endsWith('_failed') || eventType.endsWith('_cancelled')) {
      return 'terminal';
    }
    if ((detail && detail.is_stalled === true) || status === 'stalled' || eventType.includes('stalled') || !!(detail && (detail.stalled_reason || detail.stalledReason))) {
      return 'stalled';
    }
    if ((detail && detail.reconnecting === true) || status === 'reconnecting' || eventType.includes('reconnect')) return 'reconnecting';
    const sec = Number(detail && (detail.secondsSince ?? detail.seconds_since_progress ?? detail.progress_age_seconds));
    if (Number.isFinite(sec) && sec >= PROGRESS_STALE_AFTER_SECONDS) return 'stale';
    if (!status && !phase && !eventType) return 'unknown';
    return 'live';
  }

  function runtimeConnectionLabel(state, detail) {
    const sec = Number(detail && (detail.secondsSince ?? detail.seconds_since_progress ?? detail.progress_age_seconds));
    const age = Number.isFinite(sec) ? ` / last progress ${Math.max(0, Math.round(sec))}s ago` : '';
    const reason = String((detail && (detail.stalled_reason || detail.stalledReason || detail.message)) || '').trim();
    if (state === 'reconnecting') return `reconnecting${age}`;
    if (state === 'stale') return `stale${age}`;
    if (state === 'stalled') return reason ? `stalled: ${reason}` : `stalled${age}`;
    if (state === 'terminal') return 'terminal';
    if (state === 'unknown') return 'unknown progress state';
    return `live${age}`;
  }

  function applyRuntimeProgressEvent(event, poolId) {
    if (!event) return false;
    const effectivePoolId = String(event.pool_id || poolId || '');
    const runId = String(event.run_id || '');
    const sequence = Number(event.sequence || 0);
    const tokens = Number(event.tokens_total || event.tokens || 0);
    const latestAt = event.last_progress_at || event.timestamp || '';
    const secondsSince = progressAgeSeconds(latestAt, event.seconds_since_progress);
    const connectionState = classifyRuntimeConnectionState({
      ...event,
      secondsSince,
      stalledReason: event.stalled_reason,
    });
    try {
      if (effectivePoolId) localStorage.setItem(STORAGE_LAST_POOL_ID_KEY, effectivePoolId);
      if (runId) localStorage.setItem(STORAGE_LAST_RUN_ID_KEY, runId);
      if (sequence > 0) localStorage.setItem(STORAGE_LAST_EVENT_SEQUENCE_KEY, String(sequence));
    } catch (_) {}
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('atlas:llm-progress', {
        detail: {
          phase: event.phase || event.message || event.event_type || 'runtime_progress',
          tokens,
          maxCtx: Number(event.max_ctx || (event.metadata && event.metadata.max_ctx) || 0),
          tps: Number(event.tokens_per_second || 0),
          secondsSince,
          connectionState,
          status: event.status || '',
          eventType: event.event_type || '',
          stalledReason: event.stalled_reason || '',
          poolId: effectivePoolId,
          runId,
        },
      }));
    }
    renderRuntimeStatusPanel(runtimeStatusPayload(effectivePoolId, {
      run_id: runId,
      phase: progressPhaseForRuntime(event),
      status: event.status || 'running',
      current_item_title: event.item_id || '',
      message: event.message || event.event_type || 'Runtime progress restored',
      authoritative_source: 'server progress replay',
      restored_progress: true,
      runtime_connection_state: connectionState,
      progress_age_seconds: secondsSince,
      last_progress_at: latestAt,
      stalled_reason: event.stalled_reason || '',
      event_type: event.event_type || '',
      latest_progress_sequence: sequence,
      patch_generation: String(event.phase || '').toLowerCase().includes('patch')
        ? { run_id: runId, state: event.status || 'running', updated_at: latestAt }
        : {},
    }));
    return true;
  }

  async function restoreRuntimeProgressReplay(poolId, runtime) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.getPipelineEvents) return false;
    let runId = progressRunIdFromRuntime(runtime);
    if (!runId) {
      try { runId = localStorage.getItem(STORAGE_LAST_RUN_ID_KEY) || ''; } catch (_) { runId = ''; }
    }
    if (!runId && root.AtlasPipelineAPI.getContinuationPool) {
      try {
        const cont = await root.AtlasPipelineAPI.getContinuationPool(poolId, '', workspaceId());
        if (cont && cont.ok && cont.data) runId = String(cont.data.run_id || '');
      } catch (_) {}
    }
    if (!runId) return false;
    let afterSequence = 0;
    try { afterSequence = Number(localStorage.getItem(STORAGE_LAST_EVENT_SEQUENCE_KEY) || 0) || 0; } catch (_) {}
    renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
      run_id: runId,
      phase: 'patch_generation',
      status: 'reconnecting',
      message: 'Reconnecting to server progress replay',
      runtime_connection_state: 'reconnecting',
      next_actions: ['wait'],
      authoritative_source: 'server progress replay',
    }));
    const replay = await root.AtlasPipelineAPI.getPipelineEvents(poolId, runId, workspaceId(), afterSequence);
    if (!replay || !replay.ok || !replay.data) return false;
    const events = Array.isArray(replay.data.progress_events) ? replay.data.progress_events : [];
    let restored = false;
    events.forEach((event) => { restored = applyRuntimeProgressEvent(event, poolId) || restored; });
    if (!restored && replay.data.latest_progress) {
      restored = applyRuntimeProgressEvent(replay.data.latest_progress, poolId) || restored;
    }
    if (!restored) {
      renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
        run_id: runId,
        phase: 'patch_generation',
        status: 'unknown',
        message: 'No replay progress event was returned for this run',
        runtime_connection_state: 'unknown',
        next_actions: ['wait', 'refresh'],
        authoritative_source: 'server progress replay',
      }));
    }
    return restored;
  }

  async function restoreLatestAutonomousRun(poolId) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.getLatestAutonomousCodegen || !root.AtlasPipelineAPI.getAutonomousCodegenStatus) return;
    try {
      const latest = await root.AtlasPipelineAPI.getLatestAutonomousCodegen(poolId);
      if (!latest || !latest.ok || !latest.data || !latest.data.orchestrator_run_id) return;
      const status = await root.AtlasPipelineAPI.getAutonomousCodegenStatus(poolId, latest.data.orchestrator_run_id);
      if (status && status.ok && status.data) {
        renderAutonomousWorkflowState(status.data);
      }
    } catch (err) {
      console.warn('Atlas latest autonomous run restore failed', err);
    }
  }

  function init() {
    if (state.initialized) return;
    state.initialized = true;

    dom.col = $('atlas-claude-col');
    if (!dom.col) return;

    dom.transcript = $('atlas-claude-transcript');
    dom.input = $('atlas-claude-input');
    dom.sendBtn = $('atlas-claude-send-btn');
    dom.stopBtn = $('atlas-claude-stop-btn');
    dom.featuresDrawer = $('atlas-claude-features-drawer');
    dom.profileResult = $('atlas-claude-profile-result');
    dom.selectBtn = $('atlas-claude-select-profile-btn');
    dom.recoveryBtn = $('atlas-claude-recovery-btn');
    dom.badges = {
      safety: dom.col.querySelector('.atlas-claude-badge.safety'),
      phase: dom.col.querySelector('.atlas-claude-badge.phase'),
      changedFiles: dom.col.querySelector('.atlas-claude-badge.changed-files'),
    };

    bindInputs();
    appendMessage('system', '指示を入力してください', false);
    refreshPolicies();
    loadAtlasCapabilityPreferences();
    loadAtlasAutomationFeatures();
    window.addEventListener('atlas:llm-progress', (ev) => updateLlmProgressLine(ev.detail));
  }

  function updateLlmProgressLine(detail) {
    if (!dom.transcript) return;
    let line = dom.transcript.querySelector('#atlas-llm-progress-line');
    if (!line) {
      line = document.createElement('div');
      line.id = 'atlas-llm-progress-line';
      line.className = 'atlas-claude-msg atlas-claude-llm-progress';
      line.dataset.role = 'system';
      // Theme-colored animated indicator (three pulsing dots) signals live
      // generation; followed by a text node for the phase + token counter.
      const spinner = document.createElement('span');
      spinner.className = 'atlas-llm-spinner';
      spinner.setAttribute('aria-hidden', 'true');
      spinner.innerHTML = '<i></i><i></i><i></i>';
      const text = document.createElement('span');
      text.className = 'atlas-llm-progress-text';
      line.appendChild(spinner);
      line.appendChild(text);
      dom.transcript.appendChild(line);
    }
    const phase = detail.phase || '';
    const tokens = Number(detail.tokens) || 0;
    const maxCtx = Number(detail.maxCtx) || 0;
    const tps = Number(detail.tps || detail.tokensPerSecond || detail.tokens_per_second) || 0;
    const sec = Number(detail.secondsSince);
    const connectionState = classifyRuntimeConnectionState(detail || {});
    ['live', 'reconnecting', 'stale', 'stalled', 'terminal', 'unknown'].forEach((state) => line.classList.remove(state));
    line.classList.add(connectionState);
    line.classList.toggle('stalled', connectionState === 'stalled');
    line.dataset.connectionState = connectionState;
    const previousTokens = Number(line.dataset.tokens || 0) || 0;
    // Indicator: 表示(status) · token生成数 · <last progress>s ago. Non-live states
    // (stalled/reconnecting/terminal) keep the descriptive connection label instead of "Ns ago".
    const ageSec = Number.isFinite(sec) ? Math.max(0, Math.round(sec)) : 0;
    const progressPart = (connectionState === 'live' || connectionState === 'unknown')
      ? `${ageSec}s ago`
      : runtimeConnectionLabel(connectionState, detail || {});
    const parts = [
      phase || 'generating',                                            // 表示 (status/phase)
      maxCtx > 0 ? `tokens ${tokens} / ${maxCtx}` : `tokens ${tokens}`,  // token生成数
      progressPart,                                                     // 進捗 (Ns ago)
    ];
    const tokenDelta = Math.max(0, tokens - previousTokens);
    if (tokenDelta > 0 && typeof root.updateTokenDisplay === 'function') {
      root.updateTokenDisplay(tokenDelta, tps);
    }
    line.dataset.tokens = String(Math.max(previousTokens, tokens));
    const textEl = line.querySelector('.atlas-llm-progress-text');
    if (textEl) textEl.textContent = parts.join('  ·  ');
    // Only follow the stream to the bottom when the user is already near it — never yank them down
    // mid-scroll on every token update.
    scrollTranscriptIfAtBottom();
  }

  // True auto-scroll: stick to the bottom only when the user hasn't scrolled up. This keeps the
  // high-frequency generation updates from fighting manual scrolling.
  function scrollTranscriptIfAtBottom() {
    const t = dom.transcript;
    if (!t) return;
    const distanceFromBottom = t.scrollHeight - t.scrollTop - t.clientHeight;
    if (distanceFromBottom <= 80) t.scrollTop = t.scrollHeight;
  }

  function clearLlmProgressLine() {
    if (!dom.transcript) return;
    const line = dom.transcript.querySelector('#atlas-llm-progress-line');
    if (line) line.remove();
  }

  function bindInputs() {
    if (dom.input) {
      dom.input.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' && !ev.shiftKey) {
          ev.preventDefault();
          sendChatMessage();
        }
      });
      dom.input.addEventListener('input', () => autoResizeInput(dom.input));
    }
    if (dom.sendBtn) dom.sendBtn.addEventListener('click', () => sendChatMessage());
    if (dom.stopBtn) dom.stopBtn.addEventListener('click', () => onStop());
    if (dom.selectBtn) dom.selectBtn.addEventListener('click', () => selectProfile());
    if (dom.recoveryBtn) dom.recoveryBtn.addEventListener('click', () => delegateRecover());

    document.querySelectorAll('input[name="atlas-claude-preset"]').forEach((radio) => {
      radio.addEventListener('change', (ev) => {
        const value = ev.target.value;
        state.selectedPresetId = value;
        renderPresetSummary();
        updateSelectButtonState();
        persistAtlasAutomationFeatures();
      });
    });
    document.querySelectorAll('input[name="atlas-claude-work-target"]').forEach((radio) => {
      radio.addEventListener('change', (ev) => {
        state.workTarget = ev.target.value;
        renderBadges();
        renderPresetSummary();
        updateSelectButtonState();
        if (ev.target.value === 'platform_self_improvement') {
          pushSystemMessage('自己改修ターゲット: 影響範囲は app/atlas/, docs/, tests/ のみ。strict gate と Level-4 checkpoint が必須です。Features ドロワーで Apply を再実行してください。');
        }
      });
    });
  }

  function autoResizeInput(el) {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }

  function activate() {
    if (!state.initialized) init();
    if (!dom.col) return;
    state.active = true;
    dom.col.style.display = '';
    refreshLatestProfile();
    refreshWorkflowState();
    startPolling();
    // The picker (app.js) may have resolved the active project before this panel
    // initialized, so pull it on activation if our own state is still empty.
    if (!projectName()) {
      try {
        const ap = root.KASANE_ATLAS_PROJECT_PATH && root.KASANE_ATLAS_PROJECT_PATH.getActive();
        if (ap && ap.name) setActiveProject(ap);
      } catch (_err) { /* picker not ready yet */ }
    }
    // Thin client: re-fetch the active project's persisted transcript + state so
    // entering Atlas (or reloading the page) restores everything.
    if (projectName()) {
      loadProject(projectName());
    } else {
      // No project selected: fall back to the last pool ID stored in localStorage.
      try {
        const lastPoolId = localStorage.getItem(STORAGE_LAST_POOL_ID_KEY);
        if (lastPoolId) {
          state.dismissedApprovalPlanKeys.delete(lastPoolId);
          renderPlanPoolMarkdown(lastPoolId).catch((_) => {});
          restoreLatestRun(lastPoolId).catch((_) => {});
        }
      } catch (_) {}
    }
  }

  function deactivate() {
    state.active = false;
    if (dom.col) dom.col.style.display = 'none';
    stopPolling();
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(() => {
      if (state.active) refreshWorkflowState();
    }, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  async function refreshPolicies() {
    if (!root.AtlasPipelineAPI) return;
    const resp = await root.AtlasPipelineAPI.getAutomationProfilePolicies();
    if (resp.ok) {
      state.presets = resp.data.automation_profile_presets || [];
      renderPresetSummary();
    }
    const envResp = await root.AtlasPipelineAPI.getPreAuthorizedEnvelopes();
    if (envResp.ok) {
      state.envelopes = envResp.data.envelopes || [];
      renderPresetSummary();
    }
    updateSelectButtonState();
  }

  async function refreshLatestProfile() {
    if (!root.AtlasPipelineAPI) return;
    const resp = await root.AtlasPipelineAPI.getLatestAutomationProfile();
    if (resp.ok && resp.data && resp.data.available) {
      state.latestSafetyProfile = resp.data.safety_profile;
      state.latestEnvelope = resp.data.envelope;
      state.activePresetActive = !!(resp.data.envelope && resp.data.envelope.status === 'active');
    }
    renderBadges();
  }

  async function refreshWorkflowState() {
    if (!root.AtlasPipelineAPI) return;
    try {
      const resp = await fetch('/api/atlas/workflow-state/read-only', { headers: { 'Content-Type': 'application/json' } });
      if (!resp.ok) return;
      state.workflowState = await resp.json();
      renderBadges();
    } catch (_err) {
      // network errors are non-fatal for the read-only shell
    }
  }

  function renderBadges() {
    if (!dom.badges) return;
    const safety = state.latestSafetyProfile;
    const envelope = state.latestEnvelope;
    const wf = state.workflowState || {};
    const meta = wf.workflow_metadata || {};

    if (dom.badges.safety) {
      const profileName = (safety && safety.automation_safety_profile) || 'review_only';
      const rank = safety ? safety.profile_rank : 0;
      const envelopeId = (envelope && envelope.envelope_id) || 'none';
      const automation = envelopeId !== 'none' && envelope && envelope.status === 'active' ? ' • auto' : '';
      dom.badges.safety.textContent = `Profile: ${profileName} (Lv${rank})${automation}`;
      dom.badges.safety.dataset.profileRank = String(rank);
    }
    if (dom.badges.phase) {
      const phase = meta.current_phase || wf.phase || 'idle';
      dom.badges.phase.textContent = `Phase: ${phase}`;
    }
    if (dom.badges.changedFiles) {
      const files = (meta.last_changed_files && meta.last_changed_files.length) || 0;
      dom.badges.changedFiles.textContent = `Files: ${files}`;
    }
    if (false && dom.badges.verification) {
      dom.badges.verification.textContent = `Verify: ${meta.last_verification_status || 'idle'}`;
    }
  }

  function renderPresetSummary() {
    if (!dom.profileResult) return;
    const preset = state.presets.find((p) => p.id === state.selectedPresetId);
    if (!preset) return;
    const envelopeId = selectedEnvelopeId(preset);
    const envelopeRecipe = state.envelopes.find((e) => e.envelope_id === envelopeId) || null;
    const profileLabel = preset.id === 'supervised_auto'
      ? '3: Autonomous（毎回 bounds 指定・完全自動 OFF）'
      : preset.id === 'autonomous_bounded_dev'
        ? '4: Autonomous（envelope 内で完全自動・★完全自動コード生成）'
        : preset.label;
    const lines = [
      `# ${profileLabel}`,
      `- badge: full_auto=${preset.enables_full_automation ? 'ON' : 'OFF'} / envelope=${envelopeId === 'none' ? 'none' : 'bounded_dev'}`,
      `- safety profile: \`${preset.safety_profile}\``,
      `- envelope: \`${envelopeId}\``,
      `- enables full automation: ${preset.enables_full_automation ? 'YES' : 'no'}`,
    ];
    if (preset.self_improvement_enabled) {
      lines.push(`- self-improvement: enabled (scope \`${preset.self_improvement_scope}\`)`);
    }
    if (envelopeRecipe && envelopeRecipe.bounds && envelopeRecipe.envelope_id !== 'none') {
      const b = envelopeRecipe.bounds;
      lines.push('## Bounds');
      lines.push(`- max actions per loop: ${b.max_actions_per_loop}`);
      lines.push(`- max files changed: ${b.max_files_changed}`);
      lines.push(`- max runtime: ${b.max_runtime_seconds}s`);
      lines.push(`- max risk level: ${b.max_risk_level}`);
      lines.push(`- allowed paths: ${(b.allowed_paths || []).join(', ') || '(any)'}`);
      lines.push(`- blocked paths: ${(b.blocked_paths || []).join(', ') || '(none)'}`);
      lines.push(`- command allowlist: ${(b.command_allowlist || []).join(', ') || '(none)'}`);
    }
    dom.profileResult.hidden = false;
    dom.profileResult.textContent = lines.join('\n');
  }

  function updateSelectButtonState() {
    if (!dom.selectBtn) return;
    const preset = state.presets.find((p) => p.id === state.selectedPresetId);
    dom.selectBtn.disabled = !preset;
  }

  async function selectProfile() {
    if (!root.AtlasPipelineAPI) return;
    const payload = buildSelectionPayload();
    payload.confirmation_text = CONFIRM_TEXT;
    const resp = await root.AtlasPipelineAPI.selectAutomationProfile(payload);
    if (resp.ok) {
      const preset = state.presets.find((p) => p.id === state.selectedPresetId);
      pushAtlasMessage(`Profile を Apply: **${preset ? preset.label : payload.profile}**`);
      if (resp.data && resp.data.envelope) {
        state.latestEnvelope = resp.data.envelope;
      }
      if (resp.data && resp.data.safety_profile) {
        state.latestSafetyProfile = resp.data.safety_profile;
      }
      renderBadges();
    } else {
      pushAtlasMessage(`Select failed: ${formatError(resp)}`);
    }
  }

  function selectedEnvelopeId(preset) {
    if (!preset) return 'none';
    const map = preset.work_target_envelope_map;
    if (map && state.workTarget && map[state.workTarget]) return map[state.workTarget];
    return preset.envelope_id || 'none';
  }

  function buildSelectionPayload() {
    const preset = state.presets.find((p) => p.id === state.selectedPresetId) || state.presets[0];
    if (!preset) return {};
    // Profile 4 selects envelope from Work target via work_target_envelope_map.
    // Other presets use their fixed envelope_id.
    let envelopeId = selectedEnvelopeId(preset);
    let selfImprovement = !!preset.self_improvement_enabled;
    let selfImprovementScope = preset.self_improvement_scope || 'none';
    let strictGate = !!preset.self_improvement_enabled;
    const map = preset.work_target_envelope_map;
    if (map && state.workTarget && map[state.workTarget]) {
      envelopeId = map[state.workTarget];
      if (state.workTarget === 'platform_self_improvement') {
        selfImprovement = true;
        selfImprovementScope = 'atlas_runtime_strict';
        strictGate = true;
      } else {
        selfImprovement = false;
        selfImprovementScope = 'none';
        strictGate = false;
      }
    }
    return {
      profile: preset.safety_profile,
      envelope_id: envelopeId,
      explicit_profile_selection: true,
      self_improvement_enabled: selfImprovement,
      self_improvement_scope: selfImprovementScope,
      strict_gate_approved: strictGate,
      level4_checkpoint_path: '',
    };
  }

  async function sendChatMessage() {
    if (!dom.input) return;
    const text = String(dom.input.value || '').trim();
    if (!text) return;
    dom.input.value = '';
    autoResizeInput(dom.input);
    try { localStorage.setItem(STORAGE_LAST_GOAL_KEY, text); } catch (_err) {}
    pushUserMessage(text);

    const intent = classifyIntent(text);
    await dispatchIntent(intent, text);
  }

  function classifyIntent(text) {
    const lower = text.toLowerCase().trim();
    if (lower === 'stop' || lower === 'cancel') return 'stop';
    if (lower === 'recover' || lower.startsWith('recover ')) return 'recover';
    if (lower === '/play' || lower.startsWith('/play ')) return 'play_project';
    if (lower === '/plan' || lower.startsWith('/plan ')) return 'show_plan_list';
    if (lower.startsWith('dry-run') || lower.startsWith('dry run')) return 'run_dry_run';
    if (lower.startsWith('show changed files') || lower.startsWith('files')) return 'show_changed_files';
    if (lower.startsWith('explain risk') || lower.startsWith('risk')) return 'explain_risk';
    if (lower.startsWith('start auto') || lower.startsWith('autonomous')) return 'start_autonomous_loop';
    if (lower.startsWith('switch profile') || lower.startsWith('profile ')) return 'switch_profile';
    return 'free_text_goal';
  }

  async function dispatchIntent(intent, text) {
    if (!root.AtlasPipelineAPI) {
      pushAtlasMessage('AtlasPipelineAPI is not available.');
      return;
    }
    if (intent === 'stop') {
      onStop();
      return;
    }
    if (intent === 'recover') {
      delegateRecover();
      return;
    }
    if (intent === 'show_plan_list') {
      await showPlanPoolList();
      return;
    }
    if (intent === 'play_project') {
      await resolvePlayTargetFromCommand(text);
      return;
    }
    if (intent === 'switch_profile') {
      if (dom.featuresDrawer) dom.featuresDrawer.open = true;
      pushAtlasMessage('Open the Automation Profile drawer to select a new preset.');
      return;
    }
    if (intent === 'start_autonomous_loop') {
      await startAutonomousLoop(text);
      return;
    }
    if (intent === 'run_dry_run') {
      const r = await root.AtlasPipelineAPI.startPipelineDryRun({});
      pushAtlasMessage(r && r.ok ? 'Dry-run started.' : `Dry-run failed: ${formatError(r)}`);
      return;
    }
    if (intent === 'show_changed_files') {
      const wf = state.workflowState || {};
      const files = (wf.workflow_metadata && wf.workflow_metadata.last_changed_files) || [];
      pushAtlasMessage(files.length ? `Changed files:\n${files.map((f) => `- \`${f}\``).join('\n')}` : 'No changed files reported.');
      return;
    }
    if (intent === 'explain_risk') {
      const wf = state.workflowState || {};
      const warnings = wf.warnings || [];
      pushAtlasMessage(warnings.length ? `Backend warnings:\n${warnings.map((w) => `- ${w}`).join('\n')}` : 'No backend warnings.');
      return;
    }
    // free_text_goal: treat plain text as Atlas Workbench requirement input,
    // then render the generated plan in chat so the user can supervise it.
    setBusy(true);
    const resp = await root.AtlasPipelineAPI.createPlanPool({ input: text, workspace_id: workspaceId(), project_path: projectPath(), metadata: { preset_id: state.selectedPresetId }, capability_preferences: getAtlasCapabilityPreferences(), automation_features: getAtlasAutomationFeatures() });
    if (!resp.ok) {
      setBusy(false);
      pushAtlasMessage(`PlanPool creation failed: ${formatError(resp)}`);
      return;
    }
    const poolId = resp.data && (resp.data.pool_id || resp.data.id);
    if (!poolId) {
      setBusy(false);
      pushAtlasMessage('PlanPool created but no pool id was returned.');
      return;
    }
    // Persist the active pool pointer (rides along with this message's meta) so
    // a reload can re-render the plan, then auto-name the provisional project
    // from this first instruction before any further workspace-scoped calls.
    try { localStorage.setItem(STORAGE_LAST_POOL_ID_KEY, poolId); } catch (_) {}
    appendMessage('atlas', `PlanPool 作成: \`${poolId}\``, true, { active_pool_id: poolId });
    if (state.provisional) await maybeAutoRename(text);
    if (resp.data && resp.data.planner_status === 'fallback_used') {
      pushSystemMessage('注意: LLM 未接続のため fallback プランです。実際のコード生成は LLM 起動が必要です。');
    }
    await renderPlanPoolMarkdown(poolId);
    setBusy(false);

    // If a full-automation preset is selected AND the envelope is active,
    // offer user intent only when backend-owned clarification/revision gates are clear.
    const preset = state.presets.find((p) => p.id === state.selectedPresetId);
    const envelope = state.latestEnvelope;
    const envelopeActive = envelope && envelope.status === 'active' && envelope.envelope_id !== 'none';
    const createdPool = (resp.data && (resp.data.plan_pool || resp.data)) || {};
    const clarificationBlocks = clarificationExecutionBlockReasons((createdPool && createdPool.metadata) || {});
    if (clarificationBlocks.length) {
      pushSystemMessage(`確認回答と plan revision / gate rerun が完了するまで実行できません: ${clarificationBlocks.join(', ')}`);
    } else if (preset && preset.enables_full_automation && envelopeActive) {
      appendApprovalPrompt(poolId);
    } else if (preset && preset.enables_full_automation && !envelopeActive) {
      pushSystemMessage('Backend profile と active bounded envelope が確定し、gates が通過すると実行 intent を送信できます。');
    } else {
      pushSystemMessage('Profile selection alone never starts automation; backend workflow state, active envelope, and gates are required.');
    }
  }

  async function resolvePlayTargetFromCommand(text) {
    const project = projectName() || workspaceId();
    if (!project) {
      pushAtlasMessage('Play target discovery requires an active Atlas project.');
      return;
    }
    const resp = await root.AtlasPipelineAPI.resolvePlayTarget({
      project_id: project,
      source: 'atlas_command',
      command_text: text,
    });
    if (!resp.ok) {
      pushAtlasMessage(`Play target discovery failed: ${formatError(resp)}`);
      return;
    }
    const data = resp.data || {};
    if (data.status === 'resolved' && data.target) {
      const files = (data.dependency_graph && data.dependency_graph.files) || [];
      pushAtlasMessage(`Play target resolved: \`${data.target.entrypoint}\`${files.length ? `\nRelated files: ${files.length}` : ''}`);
      return;
    }
    if (data.status === 'needs_selection') {
      const candidates = (data.candidates || []).map((c) => `- ${c.entrypoint} (${c.launch_kind})`).join('\n');
      pushAtlasMessage(candidates ? `Multiple Play targets found:\n${candidates}` : 'Multiple Play targets found.');
      return;
    }
    pushAtlasMessage(`No supported Play target found: ${(data.diagnostics || []).join(', ') || data.status}`);
  }

  // Plan action prompt: approve / request-revision / cancel. State-driven so it is re-rendered on
  // reload from pool.status (see renderPlanPoolMarkdown). Backwards-compatible alias kept below.
  function planApprovalIdentity(poolId, context = {}) {
    const meta = (context && context.poolMeta) || {};
    const strategic = (context && context.strategic) || {};
    return String(
      meta.plan_id
      || strategic.plan_id
      || meta.task_id
      || strategic.task_id
      || meta.run_id
      || strategic.run_id
      || meta.session_id
      || strategic.session_id
      || meta.plan_revision_id
      || meta.revision_id
      || strategic.revision_id
      || poolId
      || ''
    ).trim();
  }

  function clearAtlasApprovalActions(filter = {}) {
    if (!dom.transcript) return;
    const removeAll = filter.removeAll === true;
    const poolId = Object.prototype.hasOwnProperty.call(filter, 'poolId') ? String(filter.poolId || '') : null;
    const planId = Object.prototype.hasOwnProperty.call(filter, 'planId') ? String(filter.planId || '') : null;
    Array.from(dom.transcript.querySelectorAll('[data-atlas-approval-actions="true"]')).forEach((el) => {
      if (!removeAll && poolId !== null && String(el.dataset.poolId || '') !== poolId) return;
      if (!removeAll && planId !== null && String(el.dataset.planId || '') !== planId) return;
      el.remove();
    });
  }

  function insertApprovalActionsNode(node, poolId, revisionId) {
    if (!dom.transcript || !node) return;
    dom.transcript.appendChild(node);
    dom.transcript.scrollTop = dom.transcript.scrollHeight;
  }

  function appendPlanActionPrompt(poolId, context = {}) {
    if (!dom.transcript) return;
    const planKey = planApprovalIdentity(poolId, context);
    if (planKey && state.dismissedApprovalPlanKeys.has(planKey)) return;
    clearAtlasApprovalActions({ planId: planKey });
    clearAtlasApprovalActions({ removeAll: true });
    const node = document.createElement('div');
    node.className = 'atlas-claude-msg';
    node.dataset.role = 'system';
    node.dataset.atlasApprovalActions = 'true';
    node.dataset.poolId = String(poolId || '');
    node.dataset.planId = planKey;
    node.style.flexDirection = 'column';
    node.style.gap = '6px';
    const text = document.createElement('div');
    text.textContent = 'この Plan を実行しますか？（承認 / 改訂依頼 / キャンセル）';
    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.gap = '6px';

    const approve = document.createElement('button');
    approve.type = 'button';
    approve.className = 'atlas-claude-primary-btn';
    approve.textContent = '承認して実行';

    const revise = document.createElement('button');
    revise.type = 'button';
    revise.className = 'atlas-claude-secondary-btn';
    revise.textContent = '改訂を依頼';

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'atlas-claude-secondary-btn';
    cancel.textContent = 'キャンセル';

    const dismiss = () => {
      if (planKey) state.dismissedApprovalPlanKeys.add(planKey);
      Array.from(actions.querySelectorAll('button')).forEach((btn) => { btn.disabled = true; });
      node.remove();
    };

    approve.addEventListener('click', () => {
      dismiss();
      approveAndRunPipeline(poolId);
    });
    revise.addEventListener('click', () => {
      const note = (root.prompt && root.prompt('改訂依頼の内容（任意）')) || '';
      dismiss();
      requestPlanRevision(poolId, note);
    });
    cancel.addEventListener('click', () => {
      dismiss();
      cancelPlan(poolId);
    });
    actions.appendChild(approve);
    actions.appendChild(revise);
    actions.appendChild(cancel);
    node.appendChild(text);
    node.appendChild(actions);
    insertApprovalActionsNode(node, poolId, context && context.revisionId);
  }

  // Backwards-compatible alias for the original creation-time call site.
  function appendApprovalPrompt(poolId, context = {}) {
    appendPlanActionPrompt(poolId, context);
  }

  // Reuse prompt for a plan restored from Plan History that is no longer in an
  // interactive approval state (ready / completed / failed / running …). Offers the
  // same three actions as a fresh plan: re-run (re-execute), request revision, cancel.
  function appendPlanReusePrompt(poolId, context = {}, poolStatus = '') {
    if (!dom.transcript) return;
    clearAtlasApprovalActions({ removeAll: true });
    const node = document.createElement('div');
    node.className = 'atlas-claude-msg';
    node.dataset.role = 'system';
    node.dataset.atlasApprovalActions = 'true';
    node.dataset.atlasReuseActions = 'true';
    node.dataset.poolId = String(poolId || '');
    node.style.flexDirection = 'column';
    node.style.gap = '6px';

    const text = document.createElement('div');
    const statusLabel = poolStatus ? `（現在の状態: ${poolStatus}）` : '';
    text.textContent = `この既存 Plan を再利用しますか？${statusLabel} 再実行すると実行状態をリセットしてからパッチ生成を最初からやり直します。`;

    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.gap = '6px';

    const rerun = document.createElement('button');
    rerun.type = 'button';
    rerun.className = 'atlas-claude-primary-btn';
    rerun.textContent = '承認して実行（再実行）';

    const revise = document.createElement('button');
    revise.type = 'button';
    revise.className = 'atlas-claude-secondary-btn';
    revise.textContent = '改訂を依頼';

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'atlas-claude-secondary-btn';
    cancel.textContent = 'キャンセル';

    const disableAll = () => Array.from(actions.querySelectorAll('button')).forEach((b) => { b.disabled = true; });

    rerun.addEventListener('click', () => {
      disableAll();
      node.remove();
      reuseAndRunPipeline(poolId);
    });
    revise.addEventListener('click', () => {
      const note = (root.prompt && root.prompt('改訂依頼の内容（任意）')) || '';
      node.remove();
      requestPlanRevision(poolId, note);
    });
    cancel.addEventListener('click', () => {
      node.remove();
      cancelPlan(poolId);
    });
    actions.append(rerun, revise, cancel);
    node.append(text, actions);
    insertApprovalActionsNode(node, poolId, context && context.revisionId);
  }

  // Recovery prompt for when clarification was fully answered but the revised plan did NOT clear the
  // post-clarification gate (replan/gate-rerun failed, or a revision/gate-rerun is still required).
  // Replaces a dead-end text message with actionable controls so the user is never stranded on a
  // button-less plan card: revise (re-run replan + gates) or cancel.
  function appendClarificationRecoveryPrompt(poolId, context = {}, blockedReasons = [], poolMeta = {}) {
    if (!dom.transcript) return;
    clearAtlasApprovalActions({ removeAll: true });
    const node = document.createElement('div');
    node.className = 'atlas-claude-msg';
    node.dataset.role = 'system';
    node.dataset.atlasApprovalActions = 'true';
    node.dataset.atlasClarificationRecovery = 'true';
    node.dataset.poolId = String(poolId || '');
    node.style.flexDirection = 'column';
    node.style.gap = '6px';

    const text = document.createElement('div');
    const guidance = String((poolMeta && poolMeta.next_required_user_action) || '').trim()
      || '確認回答後のプラン改訂/ゲート再実行が完了しませんでした。改訂を依頼して再実行するか、キャンセルしてください。';
    text.textContent = guidance;
    node.appendChild(text);

    if (Array.isArray(blockedReasons) && blockedReasons.length) {
      const detail = document.createElement('div');
      detail.className = 'atlas-claude-stage-detail';
      detail.style.whiteSpace = 'normal';
      detail.textContent = `未解決: ${blockedReasons.join(', ')}`;
      node.appendChild(detail);
    }

    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.gap = '6px';

    const revise = document.createElement('button');
    revise.type = 'button';
    revise.className = 'atlas-claude-primary-btn';
    revise.textContent = '改訂を依頼して再実行';

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'atlas-claude-secondary-btn';
    cancel.textContent = 'キャンセル';

    const disableAll = () => Array.from(actions.querySelectorAll('button')).forEach((b) => { b.disabled = true; });

    revise.addEventListener('click', () => {
      const note = (root.prompt && root.prompt('改訂依頼の内容（任意）')) || '';
      disableAll();
      node.remove();
      requestPlanRevision(poolId, note);
    });
    cancel.addEventListener('click', () => {
      disableAll();
      node.remove();
      cancelPlan(poolId);
    });
    actions.append(revise, cancel);
    node.append(actions);
    insertApprovalActionsNode(node, poolId, context && context.revisionId);
  }

  // Record a pool-scope critical decision (approve / edit_scope / cancel) against the backend
  // /critical-decisions/decide endpoint, then re-render so the next state (approval_required after an
  // approve, cancelled after a cancel, a fresh revision after edit_scope) surfaces its own controls.
  async function submitCriticalDecision(poolId, decision, reason) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.decideCriticalEvent) return;
    try {
      const result = await root.AtlasPipelineAPI.decideCriticalEvent({
        pool_id: poolId,
        item_id: '',
        decision: decision,
        reason: reason || '',
        workspace_id: workspaceId(),
        metadata: { ui: 'atlas_claude_panel', critical_decision_path: true },
      });
      const status = result && result.data ? String(result.data.status || '') : '';
      const label = decision === 'approve'
        ? '重大リスクを承認しました'
        : (decision === 'cancel' ? 'プランをキャンセルしました' : '改訂を依頼しました');
      pushSystemMessage(status ? `${label}（状態: ${status}）` : label);
      await renderPlanPoolMarkdown(poolId);
    } catch (e) {
      pushSystemMessage('重大判断の送信に失敗しました: ' + (e && e.message ? e.message : e));
    }
  }

  // Status-driven critical-decision prompt: shown when pool.status === 'waiting_for_critical_decision'.
  // The critique gate raised a CRITICAL event on the (revised) plan, so the backend parks the pool in
  // waiting_for_critical_decision. Before this branch existed the plan card rendered with NO controls —
  // the exact reported dead-end where, after the Critic is shown and an option is selected, no approve /
  // revise / cancel buttons appear. Offer the three actions that map to the pool-scope critical-decision
  // endpoint: approve (accept the critical risk → approval_required) / edit_scope (revise) / cancel.
  function appendCriticalDecisionPrompt(poolId, poolMeta = {}, context = {}) {
    if (!dom.transcript) return;
    clearAtlasApprovalActions({ removeAll: true });
    const node = document.createElement('div');
    node.className = 'atlas-claude-msg';
    node.dataset.role = 'system';
    node.dataset.atlasApprovalActions = 'true';
    node.dataset.atlasCriticalDecision = 'true';
    node.dataset.poolId = String(poolId || '');
    node.style.flexDirection = 'column';
    node.style.gap = '6px';

    const meta = poolMeta && typeof poolMeta === 'object' ? poolMeta : {};
    const ce = meta.critical_event && typeof meta.critical_event === 'object' ? meta.critical_event : {};
    const reason = String(ce.reason || ce.summary || ce.detail || meta.next_required_user_action || '').trim()
      || 'この Plan は重大な判断（クリティカルリスク）を含みます。続行を承認するか、改訂を依頼するか、キャンセルしてください。';
    const text = document.createElement('div');
    text.textContent = `重大な判断が必要です: ${reason}`;
    node.appendChild(text);

    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.gap = '6px';

    const approve = document.createElement('button');
    approve.type = 'button';
    approve.className = 'atlas-claude-primary-btn';
    approve.textContent = '重大リスクを承認して続行';

    const revise = document.createElement('button');
    revise.type = 'button';
    revise.className = 'atlas-claude-secondary-btn';
    revise.textContent = '改訂を依頼';

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'atlas-claude-secondary-btn';
    cancel.textContent = 'キャンセル';

    const disableAll = () => Array.from(actions.querySelectorAll('button')).forEach((b) => { b.disabled = true; });

    approve.addEventListener('click', () => {
      disableAll();
      node.remove();
      submitCriticalDecision(poolId, 'approve', '');
    });
    revise.addEventListener('click', () => {
      const note = (root.prompt && root.prompt('改訂依頼の内容（任意）')) || '';
      disableAll();
      node.remove();
      submitCriticalDecision(poolId, 'edit_scope', note);
    });
    cancel.addEventListener('click', () => {
      disableAll();
      node.remove();
      submitCriticalDecision(poolId, 'cancel', '');
    });
    actions.append(approve, revise, cancel);
    node.append(actions);
    insertApprovalActionsNode(node, poolId, context && context.revisionId);
  }

  // Re-run an existing plan. Clearing prior execution first is essential: an already
  // applied/approved item sets patch_proposal.status to applied/accepted, which blocks
  // regeneration ("patch_proposal_blocked") even with force_regenerate. reset-execution
  // returns the pool to approval_required with item flags cleared so generation runs.
  async function reuseAndRunPipeline(poolId) {
    try {
      if (root.AtlasPipelineAPI && root.AtlasPipelineAPI.resetPoolExecution) {
        const reset = await root.AtlasPipelineAPI.resetPoolExecution(poolId, { workspace_id: workspaceId() });
        if (reset && reset.ok === false) {
          pushSystemMessage('実行状態のリセットに失敗しました（続行します）: ' + formatError(reset));
        }
      }
    } catch (e) {
      pushSystemMessage('実行状態のリセットに失敗しました（続行します）: ' + (e && e.message ? e.message : e));
    }
    state.dismissedApprovalPlanKeys.delete(poolId);
    await approveAndRunPipeline(poolId);
  }

  function showRevisionIndicator(poolId) {
    if (!dom.transcript) return null;
    const el = document.createElement('div');
    el.className = 'atlas-claude-msg';
    el.dataset.role = 'system';
    el.dataset.atlasRevisionIndicator = String(poolId || '');
    el.textContent = 'プランを改訂中...（LLMが処理しています）';
    dom.transcript.appendChild(el);
    dom.transcript.scrollTop = dom.transcript.scrollHeight;
    return el;
  }

  function showDebugReviewIndicator() {
    if (!dom.transcript) return null;
    const el = document.createElement('div');
    el.className = 'atlas-claude-msg';
    el.dataset.role = 'system';
    el.textContent = 'デバッグレビュー中...（分析しています）';
    dom.transcript.appendChild(el);
    dom.transcript.scrollTop = dom.transcript.scrollHeight;
    return el;
  }

  function showVerificationIndicator() {
    if (!dom.transcript) return null;
    const el = document.createElement('div');
    el.className = 'atlas-claude-msg';
    el.dataset.role = 'system';
    el.textContent = '検証コマンドを実行中...';
    dom.transcript.appendChild(el);
    dom.transcript.scrollTop = dom.transcript.scrollHeight;
    return el;
  }

  async function requestPlanRevision(poolId, note) {
    if (!root.AtlasPipelineAPI) return;
    const indicator = showRevisionIndicator(poolId);
    setBusy(true);
    try {
      const resp = await root.AtlasPipelineAPI.requestRevision(poolId, {
        note: note || '',
        workspace_id: workspaceId(),
      });
      if (!resp || resp.ok === false) {
        pushSystemMessage(`改訂依頼に失敗しました: ${formatError(resp)}`);
        return;
      }
      pushSystemMessage('プランを改訂しました。内容を確認して承認してください。');
      state.dismissedApprovalPlanKeys.delete(poolId);
      await renderPlanPoolMarkdown(poolId);
    } catch (e) {
      pushSystemMessage('改訂依頼に失敗しました: ' + (e && e.message ? e.message : e));
    } finally {
      if (indicator) indicator.remove();
      setBusy(false);
    }
  }

  async function cancelPlan(poolId) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.cancelPlanPool) {
      pushSystemMessage('キャンセルしました');
      return;
    }
    try {
      await root.AtlasPipelineAPI.cancelPlanPool(poolId, { reason: 'user cancelled', workspace_id: workspaceId() });
      pushSystemMessage('Plan をキャンセルしました（cancelled）。');
    } catch (e) {
      pushSystemMessage('キャンセルに失敗しました: ' + (e && e.message ? e.message : e));
    }
  }

  function firstPendingClarificationQuestion(poolMeta) {
    const questions = Array.isArray(poolMeta && poolMeta.clarification_questions)
      ? poolMeta.clarification_questions : [];
    return questions.find((q) => String(q.status || 'pending') !== 'answered') || questions[0] || null;
  }

  function upsertTranscriptNode(matchFn, node) {
    if (!dom.transcript || !node) return;
    const existing = Array.from(dom.transcript.children || []).find(matchFn);
    if (existing) existing.replaceWith(node);
    else dom.transcript.appendChild(node);
    dom.transcript.scrollTop = dom.transcript.scrollHeight;
  }

  async function showPlanPoolList() {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.listPlanPools) {
      pushAtlasMessage('プールリストAPIが利用できません。');
      return;
    }
    setBusy(true);
    let pools = [];
    try {
      const resp = await root.AtlasPipelineAPI.listPlanPools();
      if (resp && resp.ok && resp.data) {
        pools = resp.data.pools || [];
      }
    } catch (_e) {
      pools = [];
    }
    setBusy(false);

    if (!pools.length) {
      pushAtlasMessage('保存されているプールはありません。');
      return;
    }

    const card = document.createElement('div');
    card.className = 'atlas-claude-msg atlas-claude-stage-block';
    card.dataset.role = 'atlas';
    card.dataset.atlasPlanPoolList = 'true';

    const head = document.createElement('div');
    head.className = 'atlas-claude-summary-head';
    head.textContent = `保存済みプール — ${pools.length} 件`;
    card.appendChild(head);

    pools.forEach((p) => {
      const row = document.createElement('div');
      row.className = 'atlas-claude-stage-detail';
      row.style.cssText = 'cursor:pointer; padding:6px 4px; border-radius:4px; margin:3px 0;';

      const goal = String(p.root_goal || '').slice(0, 80) || p.pool_id;
      const status = String(p.status || '');
      const itemCount = Number(p.item_count || 0);
      const updatedAt = String(p.updated_at || p.created_at || '').replace('T', ' ').slice(0, 16);

      const nameSpan = document.createElement('span');
      nameSpan.style.cssText = 'font-weight:600; color:var(--atlas-accent, #7ecfff);';
      nameSpan.textContent = goal;

      const meta = document.createElement('span');
      meta.style.cssText = 'font-size:11px; color:var(--atlas-fg-muted, #888); margin-left:8px;';
      meta.textContent = `[${status}] ${itemCount}タスク  ${updatedAt}`;

      row.appendChild(nameSpan);
      row.appendChild(meta);

      row.addEventListener('mouseenter', () => { row.style.background = 'var(--atlas-hover-bg, rgba(255,255,255,0.06))'; });
      row.addEventListener('mouseleave', () => { row.style.background = ''; });
      row.addEventListener('click', () => restorePlanPool(p.pool_id, p.root_goal));

      card.appendChild(row);
    });

    if (dom.transcript) {
      dom.transcript.querySelector('[data-atlas-plan-pool-list="true"]')?.remove();
      dom.transcript.appendChild(card);
      dom.transcript.scrollTop = dom.transcript.scrollHeight;
    }
  }

  async function restorePlanPool(poolId, rootGoal) {
    if (!poolId) return;
    pushUserMessage(`プール復元: ${rootGoal || poolId}`);
    try { localStorage.setItem(STORAGE_LAST_POOL_ID_KEY, poolId); } catch (_) {}
    setBusy(true);
    state.dismissedApprovalPlanKeys.delete(poolId);
    // The plan card is upserted by pool/revision key: if this pool's card already exists
    // higher up in the transcript (the common case — the last pool is auto-restored on
    // load), the upsert replaces that off-screen node and the click looks like a no-op.
    // Drop stale nodes for this pool first so the fresh card lands at the bottom, right
    // after the「プール復元」message the user just produced.
    if (dom.transcript) {
      Array.from(dom.transcript.children || []).forEach((el) => {
        const d = el.dataset || {};
        if (d.poolId === String(poolId)
          && (d.atlasPlanCard === 'true' || d.atlasStageBlock === 'true' || d.atlasWorkbenchBlock === 'true')) {
          el.remove();
        }
      });
    }
    try {
      await renderPlanPoolMarkdown(poolId, { allowReuse: true });
      await restoreLatestRun(poolId);
      // Make the restored pool the project's active pool so a browser reload comes back to it.
      persistMeta({ active_pool_id: poolId });
    } catch (err) {
      pushSystemMessage('プール復元に失敗しました: ' + (err && err.message ? err.message : err));
    } finally {
      setBusy(false);
    }
  }

  function renderWorkbenchFlow(poolId, requirement, view) {
    if (!dom.transcript) return;
    const block = document.createElement('div');
    block.className = 'atlas-claude-msg atlas-claude-stage-block';
    block.dataset.role = 'atlas';
    block.dataset.atlasWorkbenchBlock = 'true';
    block.dataset.poolId = String(poolId || '');

    const details = document.createElement('div');
    details.className = 'atlas-claude-summary-block';
    const flow = [
      'Requirement input',
      'Start Atlas',
      'Plan Review',
      'Clarification / Critical Decision',
      'Execute Preview',
      'Verification / Repair',
      'Draft PR Artifact',
    ];
    renderAutonomousList(details, 'Workbench flow', flow);
    renderAutonomousList(details, 'Backend authority', [
      requirement ? `requirement: ${String(requirement).slice(0, 240)}` : '',
      'Backend workflow_state / PlanPool decide controls.',
      'Profile selection alone never starts an autonomous loop.',
      'Active envelope is required for the autonomous profile.',
      'Direct merge, remote git push, and self-apply are disabled.',
    ]);
    renderWorkbenchControls(details, (view && view.controls) || {});
    block.appendChild(details);

    upsertTranscriptNode(
      (el) => el.dataset
        && el.dataset.atlasWorkbenchBlock === 'true'
        && el.dataset.poolId === String(poolId || ''),
      block,
    );
  }

  function renderWorkbenchControls(parent, controls) {
    const c = controls || {};
    renderAutonomousList(parent, 'Status-driven controls', [
      `can_answer_clarification: ${!!c.can_answer_clarification}`,
      `can_approve_critical_event: ${!!c.can_approve_critical_event}`,
      `can_reject_critical_event: ${!!c.can_reject_critical_event}`,
      `can_continue: ${!!c.can_continue}`,
      'can_execute: false',
      'execute_apply_visible: false',
    ]);
  }

  // Claude-style clarification queue: render exactly one pending question, preserving the rest.
  function appendClarificationPrompt(poolId, poolMeta) {
    if (!dom.transcript) return;
    const question = firstPendingClarificationQuestion(poolMeta || {});
    if (!question) return;
    const options = Array.isArray(question.options) ? question.options : [];
    const node = document.createElement('div');
    node.className = 'atlas-claude-msg';
    node.dataset.role = 'system';
    node.dataset.atlasClarificationPrompt = 'true';
    node.dataset.poolId = poolId;
    node.style.flexDirection = 'column';
    node.style.gap = '6px';
    const text = document.createElement('div');
    const index = question.index || 1;
    const total = question.total || Math.max(1, options.length ? 1 : index);
    text.textContent = `確認が必要です: ${index}/${total}`;
    node.appendChild(text);
    const prompt = document.createElement('div');
    prompt.className = 'atlas-claude-stage-detail';
    prompt.style.whiteSpace = 'normal';
    prompt.textContent = String(question.title || question.prompt || 'Clarification required');
    node.appendChild(prompt);
    if (question.user_facing_issue_summary) {
      const summary = document.createElement('div');
      summary.className = 'atlas-claude-stage-detail';
      summary.style.whiteSpace = 'normal';
      summary.textContent = String(question.user_facing_issue_summary);
      node.appendChild(summary);
    }
    if (question.why_it_matters) {
      const why = document.createElement('div');
      why.className = 'atlas-claude-stage-detail';
      why.style.whiteSpace = 'normal';
      why.textContent = String(question.why_it_matters);
      node.appendChild(why);
    }
    if (question.reason) {
      const reason = document.createElement('div');
      reason.className = 'atlas-claude-stage-detail';
      reason.style.whiteSpace = 'normal';
      reason.textContent = `Detected: ${String(question.reason)}`;
      node.appendChild(reason);
    }
    const custom = document.createElement('textarea');
    custom.className = 'atlas-claude-input';
    custom.rows = 2;
    custom.placeholder = '自由入力 / Custom answer';
    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.flexDirection = 'column';
    actions.style.gap = '6px';
    options.forEach((opt) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'atlas-claude-secondary-btn';
      btn.style.textAlign = 'left';
      const label = String(opt.label || opt.option_id || 'option');
      const desc = String(opt.description || '');
      const impact = String(opt.plan_change_summary || opt.implementation_scope || '');
      const recommended = opt.recommended || question.recommended_option_id === opt.option_id ? 'Recommended: ' : '';
      btn.textContent = [recommended + label, desc, impact ? `Impact: ${impact}` : ''].filter(Boolean).join(' — ');
      btn.addEventListener('click', () => {
        Array.from(actions.querySelectorAll('button')).forEach((actionBtn) => { actionBtn.disabled = true; });
        custom.disabled = true;
        submitClarification(poolId, question.question_id, opt.option_id, opt.requires_text ? custom.value : '');
      });
      actions.appendChild(btn);
    });
    node.appendChild(custom);
    node.appendChild(actions);
    upsertTranscriptNode(
      (el) => el.dataset && el.dataset.atlasClarificationPrompt === 'true' && el.dataset.poolId === String(poolId),
      node,
    );
  }

  async function submitClarification(poolId, questionId, optionId, answerText) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.clarifyPlanPool) return;
    try {
      const result = await root.AtlasPipelineAPI.clarifyPlanPool(poolId, {
        question_id: questionId,
        option_id: optionId,
        answer_text: answerText || '',
        workspace_id: workspaceId(),
      });
      const pending = result && result.data ? Number(result.data.pending_question_count || 0) : 0;
      pushSystemMessage(pending > 0 ? `選択を記録しました。残り ${pending} 件の確認があります。` : '選択を記録しました。Plan revision と gate rerun が必要です。');
      await renderPlanPoolMarkdown(poolId);
    } catch (e) {
      pushSystemMessage('選択の送信に失敗しました: ' + (e && e.message ? e.message : e));
    }
  }

  function clarificationExecutionBlockReasons(metadata) {
    const meta = metadata && typeof metadata === 'object' ? metadata : {};
    const reasons = [];
    const add = (reason) => {
      if (reason && !reasons.includes(reason)) reasons.push(reason);
    };
    if (meta.clarification_required) add('clarification_required');
    if (Number(meta.pending_question_count || 0) > 0) add('clarification_pending_questions');
    const questions = Array.isArray(meta.clarification_questions) ? meta.clarification_questions : [];
    if (questions.some((q) => q && String(q.status || 'pending') !== 'answered')) {
      add('clarification_questions_unanswered');
    }
    const answers = Array.isArray(meta.clarification_answers) ? meta.clarification_answers : [];
    const hasAnswers = answers.length > 0;
    const hasRevisedPlan = !!meta.revised_plan_snapshot;
    const hasGateRerunEvidence = !!(
      meta.gate_rerun_performed_after_clarification
      || meta.gate_rerun_after_clarification
      || meta.gate_rerun_evidence_after_clarification
      || (meta.rerun_critique_gate_after_clarification && meta.rerun_safety_gate_after_clarification)
    );
    if (meta.plan_revision_required_after_clarification) add('plan_revision_required_after_clarification');
    if (meta.gate_rerun_required_after_clarification) add('gate_rerun_required_after_clarification');
    if (hasAnswers && !hasRevisedPlan) add('missing_revised_plan_snapshot_after_clarification');
    if (hasAnswers && !hasGateRerunEvidence) add('missing_gate_rerun_evidence_after_clarification');
    return reasons;
  }

  // Identify plan items that are ALREADY applied (a prior run completed them), so a re-run / resume
  // skips them instead of re-generating — which would error with patch_proposal_blocked and, worse,
  // risk re-applying or dropping prior work. An item is applied when the pool says it is completed,
  // lists it in completed_item_ids, or it carries a safe_apply change record.
  function appliedItemIds(poolData) {
    const ids = new Set();
    const completed = (poolData && (poolData.completed_item_ids
      || (poolData.plan_pool && poolData.plan_pool.completed_item_ids))) || [];
    completed.forEach((id) => ids.add(String(id)));
    const items = (poolData && (poolData.items || poolData.plan_items
      || (poolData.plan_pool && (poolData.plan_pool.items || poolData.plan_pool.plan_items)))) || [];
    items.forEach((it) => {
      const id = String(it.item_id || it.id || '');
      if (!id) return;
      const md = it.metadata || {};
      const changed = ((md.safe_apply || {}).changed_files) || [];
      if (String(it.status || '').toLowerCase() === 'completed' || (Array.isArray(changed) && changed.length > 0)) {
        ids.add(id);
      }
    });
    return ids;
  }

  async function approveAndRunPipeline(poolId, opts) {
    if (!root.AtlasPipelineAPI) return;
    const resume = !!(opts && opts.resume);
    setBusy(true);
    const stages = appendStageBlock(poolId);
    try {
      // ── Stage 1: Plan ──
      updateStage(stages, 'plan', 'running', 'fetching items');
      const pool = await root.AtlasPipelineAPI.getPlanPool(poolId);
      if (!pool.ok || !pool.data) {
        updateStage(stages, 'plan', 'failed', formatError(pool));
        renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
          phase: 'failed',
          status: 'failed',
          message: 'Run status unavailable',
          error: formatError(pool),
          requires_user_action: true,
          next_actions: ['retry', 'cancel'],
        }), stages);
        return;
      }
      const poolMeta = pool.data.metadata || (pool.data.plan_pool && pool.data.plan_pool.metadata) || {};
      const poolStatus = String(pool.data.status || (pool.data.plan_pool && pool.data.plan_pool.status) || '');
      const clarificationBlocks = clarificationExecutionBlockReasons(poolMeta);
      if (clarificationBlocks.length) {
        updateStage(stages, 'plan', 'failed', `clarification revision/gate rerun required: ${clarificationBlocks.join(', ')}`);
        renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
          phase: 'blocked_safety_review',
          status: 'blocked',
          message: 'Patch generation has not started',
          block_reason: `clarification revision/gate rerun required: ${clarificationBlocks.join(', ')}`,
          requires_user_action: true,
          next_actions: ['revise plan', 'cancel'],
          authoritative_source: 'PlanPool',
        }), stages);
        return;
      }
      if (poolStatus === 'blocked_safety_review') {
        const reason = String(poolMeta.safety_gate_block_reason_after_clarification || 'safety_gate_blocked');
        updateStage(stages, 'patch', 'failed', `Safety gate blocked: ${reason}`);
        renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
          phase: 'blocked_safety_review',
          status: 'blocked',
          items_total: (pool.data.items || pool.data.plan_items || []).length,
          message: 'Blocked by safety gate',
          block_reason: reason,
          requires_user_action: true,
          next_actions: ['override safety block', 'revise plan', 'cancel'],
          authoritative_source: 'PlanPool',
        }), stages);
        appendSafetyBlockPrompt(poolId, poolMeta);
        return;
      }
      const items = pool.data.items || pool.data.plan_items || [];
      // Items a prior run already applied — always skipped on a re-run so we never re-generate or
      // re-apply finished work (flag-safe resume). Populated for both an explicit "続きからリトライ"
      // and an ordinary re-run of a partially-completed pool.
      const alreadyApplied = appliedItemIds(pool.data);
      if (!items.length) {
        updateStage(stages, 'plan', 'failed', 'no items');
        renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
          phase: 'patch_generation',
          status: 'waiting',
          message: 'Patch generation has not started: no plan items are available',
          requires_user_action: true,
          next_actions: ['revise plan', 'cancel'],
        }), stages);
        return;
      }
      const approvalTargets = poolStatus === 'approval_required'
        ? items.filter((it) => {
          const decision = String((((it.metadata || {}).approval || {}).decision) || '').toLowerCase();
          const itemStatus = String(it.status || '').toLowerCase();
          return decision !== 'approved' && (
            itemStatus === 'approval_required'
            || itemStatus === 'paused'
            || itemStatus === 'waiting_for_critical_decision'
            || it.requires_user_confirmation
          );
        })
        : [];
      if (approvalTargets.length) {
        renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
          phase: 'approving',
          status: 'running',
          items_total: items.length,
          items_started: 0,
          message: 'Approving plan items',
          next_actions: ['wait'],
          authoritative_source: '/api/atlas/approvals/decide',
        }), stages);
        updateStage(stages, 'plan', 'running', `approving 0/${approvalTargets.length}`);
        for (let i = 0; i < approvalTargets.length; i += 1) {
          const it = approvalTargets[i];
          const approval = await root.AtlasPipelineAPI.decideApproval({
            pool_id: poolId,
            item_id: it.item_id || it.id,
            decision: 'approved',
            reason: 'user approved plan execution',
            workspace_id: workspaceId(),
            metadata: { ui: 'atlas_claude_panel', plan_approval: true },
          });
          if (!approval || approval.ok === false) {
            const err = formatError(approval);
            updateStage(stages, 'plan', 'failed', err);
            renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
              phase: 'failed',
              status: 'failed',
              items_total: items.length,
              message: 'Approval failed before patch generation',
              error: err,
              requires_user_action: true,
              next_actions: ['retry', 'revise plan', 'cancel'],
              authoritative_source: '/api/atlas/approvals/decide',
            }), stages);
            return;
          }
          updateStage(stages, 'plan', 'running', `approving ${i + 1}/${approvalTargets.length}`);
        }
      }
      updateStage(stages, 'plan', 'done', `${items.length} items`);

      // ── Stage 2: Patch generation ──
      // A proposal can return status="proposed" yet carry NO applicable content (weak/absent LLM
      // or fallback). Only items with real patch content can actually be applied, so count and
      // approve ONLY those — otherwise the UI shows fake "4/4 success" and Apply silently skips all.
      renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
        phase: 'patch_generation',
        status: 'waiting',
        items_total: items.length,
        items_started: 0,
        items_completed: 0,
        message: 'Patch generation has not started',
        next_actions: ['wait', 'retry', 'cancel'],
        authoritative_source: 'PlanPool',
      }), stages);
      updateStage(stages, 'patch', 'running', `0/${items.length}`);
      // Interleaved generate -> approve -> apply+verify, ONE item at a time, so each patch is
      // generated against the CURRENT file (including earlier items' applied edits). Generating ALL
      // patches first and then applying them in a batch caused EDIT DRIFT (a later item's old_string
      // no longer matched the file an earlier item had changed) -> safe_apply_not_applied.
      const envelope = state.latestEnvelope || {};
      const bounds = envelope.bounds || {};
      let generated = 0;
      let appliedCount = 0;
      let failedCount = 0;
      const genFailures = [];
      const appliableIds = [];
      const perItemResults = [];
      // User-facing checklist of the planned items (steps); updated as each one runs.
      const planSteps = items.map((it) => ({ item_id: it.item_id || it.id, title: it.title || it.goal || it.item_id || it.id, state: 'pending', note: '' }));
      renderPlanSteps(stages, planSteps);
      const markStep = (idx, state, note) => { if (planSteps[idx]) { planSteps[idx].state = state; if (note != null) planSteps[idx].note = note; renderPlanSteps(stages, planSteps); } };
      for (let i = 0; i < items.length; i += 1) {
        const it = items[i];
        const itemId = it.item_id || it.id;
        if (!itemId) continue;
        // Flag-safe resume: an item a prior run already applied is kept as-is — never re-generated
        // (which would error patch_proposal_blocked) and never re-applied. We count it as completed so
        // the summary and the "first patch" guard reflect the real progress, then move to the next.
        if (alreadyApplied.has(String(itemId))) {
          markStep(i, 'done', '既に反映済み(スキップ)');
          generated += 1;
          appliedCount += 1;
          perItemResults.push({ item_id: itemId, status: 'completed', reason: 'already_applied' });
          updateStage(stages, 'patch', 'running', `${i + 1}/${items.length}`);
          continue;
        }
        // Show that THIS item is now being generated BEFORE the (potentially long /
        // slow LLM) call returns. Without this, the panel stays frozen on the previous
        // item's "N/total" until generation completes, so a slow item looks like a hang.
        markStep(i, 'running', resume ? '続きから生成中' : '生成中');
        updateStage(stages, 'patch', 'running', `${i}/${items.length} → 生成中 ${i + 1}`);
        renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
          phase: 'patch_generation',
          status: 'running',
          items_total: items.length,
          items_started: i,
          items_completed: generated,
          current_item_index: i + 1,
          current_item_title: it.title || itemId,
          message: `Patchを生成中 ${i + 1}/${items.length}`,
          next_actions: ['wait', 'cancel'],
          authoritative_source: '/api/atlas/patch-proposals/generate',
          // Carry an explicit running state so renderRuntimeStatusPanel does not skip this
          // update after a previous item reached the terminal "succeeded" state.
          patch_generation: { state: 'running', run_id: '' },
        }), stages);
        // Generation can miss non-deterministically on a weak local model (e.g. a transient
        // semantic_validation_failed) even for a real implementation item. A fresh attempt usually
        // succeeds, so retry a content-required item before giving up — this is a generation
        // reliability fix, NOT a no-op: the item IS meant to produce code.
        // GEN_MAX_ATTEMPTS = the visible per-item retry budget. Kept in step with the backend's
        // ATLAS patch-generation attempt budget (MAX_LLM_GENERATION_ATTEMPTS = 5) so the "生成リトライ
        // x/5" the user sees matches the configured value (previously hard-coded 2, which looked like
        // only 2 retries even though the backend was set to 5).
        const GEN_MAX_ATTEMPTS = 5;
        let r = null, prop = null, propMeta = {}, resultMeta = {}, patchGeneration = {}, hasContent = false;
        for (let attempt = 1; attempt <= GEN_MAX_ATTEMPTS && !hasContent; attempt += 1) {
          if (attempt > 1) markStep(i, 'running', `生成リトライ ${attempt}/${GEN_MAX_ATTEMPTS}`);
          // A thrown error (network / backend 500 / timeout) must NOT abort the whole run and leave the
          // remaining steps untouched. Convert it to a per-item failure result so this attempt loop and
          // the outer item loop keep going; the item is then reported as a genuine failure.
          try {
            r = await root.AtlasPipelineAPI.generatePatchProposal({
              pool_id: poolId,
              item_id: itemId,
              workspace_id: workspaceId(),
              force_regenerate: true,
            });
          } catch (err) {
            r = { ok: false, error: true, message: String((err && err.message) || err) };
          }
          prop = r && r.ok && r.data ? r.data.proposal : null;
          propMeta = (prop && prop.metadata) || {};
          resultMeta = (r && r.ok && r.data && r.data.metadata) || {};
          patchGeneration = resultMeta.patch_generation || propMeta.patch_generation || {};
          const generatedRunId = (r && r.ok && r.data && r.data.run_id) || patchGeneration.run_id || '';
          if (generatedRunId) {
            try {
              localStorage.setItem(STORAGE_LAST_POOL_ID_KEY, poolId);
              localStorage.setItem(STORAGE_LAST_RUN_ID_KEY, generatedRunId);
            } catch (_) {}
          }
          hasContent = patchGeneration.state === 'succeeded'
            && patchGeneration.outcome === 'success'
            && patchGeneration.patch_content_available === true;
        }
        if (hasContent) {
          generated += 1;
          appliableIds.push(itemId);
          updateStage(stages, 'patch', 'running', `${i + 1}/${items.length}`);
          // Approve, then apply+verify THIS item immediately (single-item autopilot keeps
          // self-correction / bounded-retry) so the NEXT item is generated against the updated file.
          updateStage(stages, 'approve', 'running', `${generated}`);
          await root.AtlasPipelineAPI.decidePatchProposal({ pool_id: poolId, item_id: itemId, decision: 'approved' });
          markStep(i, 'running', '適用+検証中');
          updateStage(stages, 'apply', 'running', `${appliedCount}/${generated}`);
          // Keep the theme-colored indicator current during the (token-less) apply/verify of this item.
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('atlas:llm-progress', { detail: { phase: 'applying', tokens: 0, secondsSince: 0, poolId } }));
          }
          renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
            phase: 'applying', status: 'running', items_total: items.length, items_started: generated,
            items_completed: appliedCount, current_item_index: i + 1, current_item_title: it.title || itemId,
            message: `適用+検証 ${i + 1}/${items.length}`, next_actions: ['wait', 'cancel'],
            authoritative_source: '/api/atlas/multi-item-autopilot/run',
          }), stages);
          let one;
          // The single-item apply+verify+self-correct call is synchronous and can take minutes (browser
          // smoke + LLM repair). Poll the server's live SUB-PHASE so the step shows WHAT is executing
          // now (適用中 / ブラウザスモーク検証中 / 不具合を自動修正中) instead of looking "stuck at apply".
          const autopilotRunId = `interleaved_${itemId}_${Date.now().toString(36)}`;
          let _hbSec = 0;
          const _applyHeartbeat = setInterval(async () => {
            _hbSec += 2;
            let label = '適用+検証中';
            try {
              const pr = await root.AtlasPipelineAPI.getMultiItemAutopilotProgress(poolId, autopilotRunId);
              if (pr && pr.ok && pr.data && pr.data.found) label = _autopilotSubPhaseLabel(pr.data);
            } catch (_) { /* keep generic label */ }
            markStep(i, 'running', `${label}… ${_hbSec}s`);
            if (typeof window !== 'undefined') {
              window.dispatchEvent(new CustomEvent('atlas:llm-progress', { detail: { phase: label, tokens: 0, secondsSince: 0, poolId } }));
            }
          }, 2000);
          try {
            one = await root.AtlasPipelineAPI.runMultiItemAutopilot({
              pool_id: poolId, run_id: autopilotRunId, item_ids: [itemId], policy_id: 'full_auto_multi_item_v1', max_items: 1,
              max_runtime_seconds: bounds.max_runtime_seconds || 1800,
              max_changed_files_total: bounds.max_files_changed || 25, dry_run: false, require_approval: false,
              include_context_refresh: true, include_evaluator: true, include_bounded_retry: true,
              include_self_correction: true, self_correction_max_attempts: 2,
              metadata: { ui: 'atlas_claude_panel', envelope_id: envelope.envelope_id, interleaved: true },
            });
          } catch (err) { one = { ok: false, error: true, message: String(err) }; }
          finally { clearInterval(_applyHeartbeat); }
          const od = (one && one.ok && one.data) || {};
          const ir = (od.item_results || [])[0] || {};
          const itemApplied = (od.completed_count || 0) > 0 || ir.status === 'applied' || ir.status === 'completed' || ir.reason === 'safe_apply_drift_recovered' || ir.reason === 'already_satisfied';
          // Did this item FAIL verification first and then get auto-repaired (regenerate -> re-apply
          // -> re-verify) before passing? Surface that as a "fixed on re-run" note.
          const scResult = (ir.metadata || {}).self_correction_result || {};
          const recoveredByRepair = ir.reason === 'self_correction_recovered'
            || String(scResult.status || '') === 'recovered'
            || !!((ir.verification_result || {}).recovered_by_self_correction)
            || !!((ir.verification_result || {}).recovered_by_bounded_retry);
          if (itemApplied) {
            appliedCount += 1;
            const note = ir.reason === 'safe_apply_drift_recovered' ? '適用(再生成で回復)'
              : ir.reason === 'already_satisfied' ? '既に反映済み'
              : recoveredByRepair ? '不具合を修正して再検証OK'
              : '適用済み';
            markStep(i, 'done', note);
            updateStage(stages, 'apply', 'running', `${appliedCount}/${generated}`);
            updateStage(stages, 'verify', 'running', `pass ${appliedCount}`);
          } else {
            failedCount += 1;
            // Name the actual defect (e.g. 検証失敗: JSエラー) and note if auto-repair was exhausted.
            const detail = _itemFailureDetail(ir);
            const exhausted = String(scResult.status || '') === 'exhausted';
            markStep(i, 'failed', exhausted ? `${detail}（自動修正でも未解決）` : detail);
          }
          perItemResults.push({ item_id: itemId, status: ir.status || (one && one.ok ? 'unknown' : 'error'), reason: ir.reason || (one && one.message) || '', verify_detail: _itemFailureDetail(ir) });
        } else {
          // Still no content after retries. A real implementation item (has target_files) failing
          // to generate is an HONEST failure that needs attention — not a benign skip. A genuine
          // non-file/meta step (no target_files) is legitimately skipped.
          const isFileItem = Array.isArray(it.target_files) && it.target_files.length > 0;
          markStep(i, isFileItem ? 'failed' : 'skipped', isFileItem ? '生成失敗(リトライ後も内容なし)' : 'パッチ内容なし(スキップ)');
          if (isFileItem) failedCount += 1;
          // Build a richer error: distinguish "no patch content" from HTTP/backend errors so the
          // user understands WHY an item will be skipped instead of seeing a cryptic skip later.
          let msg = formatError(r);
          if (r && r.ok && r.data) {
            const status = r.data.status || 'unknown';
            const warnings = Array.isArray(r.data.warnings) ? r.data.warnings : [];
            const errors = Array.isArray(r.data.errors) ? r.data.errors : [];
            let cause = 'パッチ生成がブロックされました';
            if (warnings.includes('plan_revision_required_blocks_patch')) {
              cause = 'プラン修正が必要なため、パッチ生成は開始されませんでした';
            } else if (warnings.includes('llm_no_patch_content_generated') || warnings.includes('plan_item_patch_content_missing')) {
              cause = 'LLMがパッチ内容を生成できませんでした';
            } else if (status === 'proposed') {
              cause = 'パッチ内容が空の提案です';
            }
            const parts = [`status=${status}`, cause];
            if (warnings.length) parts.push(`warnings=${warnings.join('; ')}`);
            if (plannerFallback && plannerFallback.reason) parts.push(`planner_fallback=${plannerFallback.reason}`);
            if (errors.length) parts.push(`errors=${errors.join('; ')}`);
            msg = parts.join(' / ');
          }
          genFailures.push({ id: itemId, msg });
        }
        updateStage(stages, 'patch', 'running', `${i + 1}/${items.length}`);
        renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
          phase: 'patch_generation',
          status: patchGeneration.state || 'running',
          items_total: items.length,
          items_started: i + 1,
          items_completed: generated,
          current_item_index: i + 1,
          current_item_title: it.title || itemId,
          message: patchGeneration.state === 'repairing' ? `自動修正中: attempt ${patchGeneration.attempt || 0}` : `Patch generation ${i + 1}/${items.length}`,
          next_actions: ['wait', 'cancel'],
          authoritative_source: '/api/atlas/patch-proposals/generate',
          patch_generation: patchGeneration,
        }), stages);
      }
      if (generated === 0) {
        updateStage(stages, 'patch', 'failed', `0/${items.length} (${genFailures.length} 件パッチ内容なし)`);
        renderPipelineSummary(stages, { status: 'patch_generation_failed', genFailures });
        renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
          phase: 'failed',
          status: 'failed',
          items_total: items.length,
          items_started: items.length,
          items_completed: 0,
          message: 'Patch generation failed before first patch',
          error: genFailures.map((f) => `${f.id}: ${f.msg}`).join('; ') || 'no_patch_content',
          requires_user_action: true,
          next_actions: ['retry', 'revise plan', 'cancel'],
          authoritative_source: '/api/atlas/patch-proposals/generate',
        }), stages);
        return;
      }
      // ── Finalize (apply+verify already happened inline, per item) ──
      updateStage(stages, 'patch', generated > 0 ? 'done' : 'failed', `${generated}/${items.length}`);
      updateStage(stages, 'approve', generated > 0 ? 'done' : 'pending', `${generated}/${generated}`);
      updateStage(stages, 'apply', appliedCount > 0 ? 'done' : 'failed', `${appliedCount}/${generated}`);
      updateStage(stages, 'verify', (appliedCount > 0 && failedCount === 0) ? 'done' : (appliedCount > 0 ? 'failed' : 'pending'), `pass ${appliedCount} / fail ${failedCount}`);
      const summary = {
        status: failedCount === 0 ? 'completed' : 'completed_with_failures',
        processed_count: generated,
        completed_count: appliedCount,
        failed_count: failedCount,
        item_results: perItemResults,
      };
      if (genFailures.length) summary.no_content_failures = genFailures;
      renderPipelineSummary(stages, summary);
      renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
        phase: failedCount === 0 ? 'completed' : 'failed',
        status: summary.status,
        items_total: items.length,
        items_started: generated,
        items_completed: appliedCount,
        message: `完了 ${appliedCount} / 失敗 ${failedCount}（生成 ${generated}/${items.length}）`,
        error: failedCount ? 'safe_apply_or_verify_failed' : '',
        requires_user_action: failedCount > 0,
        next_actions: failedCount > 0 ? ['retry', 'revise plan', 'cancel'] : [],
        authoritative_source: 'multi_item_autopilot_result',
        failed_phase: failedCount > 0 ? 'verify' : undefined,
      }), stages);
      // Persist run pointer so the result block re-renders after a reload.
      persistMeta({ active_pool_id: poolId });
    } finally {
      setBusy(false);
    }
  }

  // ── Pipeline stage block helpers ──
  const STAGE_DEFS = [
    { id: 'plan', label: 'Plan' },
    { id: 'patch', label: 'Patch' },
    { id: 'approve', label: 'Approve' },
    { id: 'apply', label: 'Apply' },
    { id: 'verify', label: 'Verify' },
    { id: 'summary', label: 'Summary' },
  ];
  const STATE_ICONS = { pending: '·', running: '⟳', done: '✓', failed: '✗', skipped: '–' };

  function appendStageBlock(poolId) {
    if (!dom.transcript) return null;
    Array.from(dom.transcript.children || []).forEach((el) => {
      if (el.dataset && el.dataset.atlasStageBlock === 'true' && el.dataset.poolId === String(poolId)) el.remove();
    });
    const block = document.createElement('div');
    block.className = 'atlas-claude-msg atlas-claude-stage-block';
    block.dataset.role = 'atlas';
    block.dataset.pool = poolId;
    block.dataset.poolId = poolId;
    block.dataset.atlasStageBlock = 'true';
    // The high-level Plan/Patch/Approve/Apply/Verify/Summary stage rows were removed as redundant:
    // the per-item plan-step checklist below already conveys progress, and the theme-color indicator
    // shows live activity. updateStage() calls become graceful no-ops (no matching rows exist).
    const planSteps = document.createElement('div');
    planSteps.className = 'atlas-claude-plan-steps';
    planSteps.dataset.role = 'plan-steps';
    const summary = document.createElement('div');
    summary.className = 'atlas-claude-summary-block';
    summary.dataset.role = 'summary';
    block.append(planSteps, summary);
    dom.transcript.appendChild(block);
    scrollTranscriptIfAtBottom();
    return block;
  }

  // Compact, user-facing checklist of the PLAN ITEMS (steps) and which one is running now:
  // ✓ done, ⟳ running, ✗ failed, · pending. Replaces verbose diagnostics as the primary view.
  function renderPlanSteps(block, steps) {
    if (!block) return;
    const host = block.querySelector('.atlas-claude-plan-steps');
    if (!host) return;
    host.innerHTML = '';
    (steps || []).forEach((s, idx) => {
      const row = document.createElement('div');
      row.className = 'atlas-claude-plan-step';
      row.dataset.state = s.state || 'pending';
      const icon = document.createElement('span');
      icon.className = 'atlas-claude-plan-step-icon';
      icon.textContent = STATE_ICONS[s.state] || '·';
      const label = document.createElement('span');
      label.className = 'atlas-claude-plan-step-label';
      label.textContent = `${idx + 1}. ${s.title || s.item_id || 'step'}`;
      row.append(icon, label);
      if (s.note) {
        const note = document.createElement('span');
        note.className = 'atlas-claude-plan-step-note';
        note.textContent = s.note;
        row.append(note);
      }
      host.appendChild(row);
    });
    scrollTranscriptIfAtBottom();
  }

  // Map an internal reason/code to a short, user-facing note for the step checklist.
  function _shortStepReason(reason) {
    const r = String(reason || '').toLowerCase();
    if (r.includes('js_error')) return '検証失敗: JSエラー';
    if (r.includes('visual_contract') || r.includes('visual_missing') || r.includes('animation_not_detected')) return '検証失敗: 表示要件を満たさず';
    if (r.includes('expected_text_missing')) return '検証失敗: 必要なテキストなし';
    if (r.includes('browser_smoke') || r.includes('verification_failed')) return '検証に失敗';
    if (r.includes('safe_apply_not_applied') || r.includes('edit_not_applicable')) return '適用できず';
    if (r.includes('missing_patch_or_content')) return 'パッチ内容なし';
    if (r.includes('blocked')) return 'ブロック';
    if (r.includes('network') || r.includes('timeout')) return '接続エラー';
    return '失敗';
  }

  // Map the autopilot's live sub-phase to a short, user-facing "what is running now" label.
  function _autopilotSubPhaseLabel(p) {
    const sp = String((p && p.sub_phase) || '').toLowerCase();
    const attempt = Number((p && p.attempt) || 0);
    const map = {
      starting: '適用を準備中',
      item_start: '適用を準備中',
      context_refresh: 'コンテキストを整理中',
      safe_apply: 'コードを適用中',
      safe_apply_drift_recovery: '再生成して適用中',
      verification: 'ブラウザスモークで検証中',
      bounded_retry: '再試行中',
      self_correction: '不具合を自動修正して再検証中',
    };
    let label = map[sp] || '適用+検証中';
    if ((sp === 'self_correction' || sp === 'bounded_retry') && attempt > 0) label += `（${attempt}回目）`;
    return label;
  }

  // Pull the most specific verification failure out of an autopilot item_result (the browser-smoke /
  // visual-contract reason a verify step reported), so the checklist names the actual defect.
  function _itemFailureDetail(ir) {
    const vr = (ir && ir.verification_result) || {};
    const warnings = Array.isArray(vr.warnings) ? vr.warnings : [];
    const verify = warnings.find((w) => /browser_smoke_failed|visual_missing|visual_contract|animation_not_detected|expected_text_missing|js_error/.test(String(w)));
    return _shortStepReason(verify || (ir && ir.reason) || 'failed');
  }

  function updateStage(block, stageId, stateName, detail) {
    if (!block) return;
    const row = block.querySelector(`.atlas-claude-stage-row[data-stage="${stageId}"]`);
    if (!row) return;
    row.dataset.state = stateName;
    const icon = row.querySelector('.atlas-claude-stage-icon');
    if (icon) icon.textContent = STATE_ICONS[stateName] || '·';
    const det = row.querySelector('.atlas-claude-stage-detail');
    if (det) det.textContent = detail || '';
    scrollTranscriptIfAtBottom();
  }

  function runtimeStatusPayload(poolId, overrides) {
    return {
      ok: true,
      pool_id: poolId,
      run_id: '',
      autopilot_run_id: '',
      phase: 'patch_generation',
      status: 'waiting',
      items_total: 0,
      items_started: 0,
      items_completed: 0,
      current_item_index: 0,
      current_item_title: '',
      message: '',
      block_reason: null,
      error: null,
      requires_user_action: false,
      next_actions: ['wait'],
      authoritative_source: 'ui_runtime',
      ...(overrides || {}),
    };
  }

  async function loadRuntimeStatus(poolId) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.getPlanRuntimeStatus) return null;
    const resp = await root.AtlasPipelineAPI.getPlanRuntimeStatus(poolId, workspaceId());
    if (resp && resp.ok && resp.data) return resp.data;
    return runtimeStatusPayload(poolId, {
      phase: 'failed',
      status: 'failed',
      message: 'Run status unavailable',
      error: resp ? formatError(resp) : 'runtime_status_request_failed',
      requires_user_action: true,
      next_actions: ['retry', 'revise plan', 'cancel'],
      authoritative_source: 'PlanPool runtime-status endpoint',
    });
  }

  function renderRuntimeStatusPanel(view, block) {
    if (!view) return block || null;
    const poolId = view.pool_id || (block && block.dataset && block.dataset.poolId) || 'runtime';
    const panel = block || appendStageBlock(poolId);
    if (!panel) return null;
    const incomingPatch = view.patch_generation || {};
    const incomingRunId = incomingPatch.run_id || view.run_id || '';
    const previousPatch = panel.__atlasPatchGenerationState || null;
    const previousRunId = previousPatch?.run_id || '';
    const incomingPatchSpecific = !!(incomingPatch.state || incomingPatch.outcome);
    if (previousPatch && !incomingPatchSpecific && previousRunId && incomingRunId && previousRunId !== incomingRunId) {
      return panel;
    }
    if (previousPatch && !incomingPatchSpecific && ['repairing', 'failed', 'blocked', 'succeeded'].includes(String(previousPatch.state || ''))) {
      return panel;
    }
    if (incomingPatchSpecific) panel.__atlasPatchGenerationState = Object.assign({}, incomingPatch, { run_id: incomingRunId || incomingPatch.run_id || '' });
    const phase = String(view.phase || 'patch_generation');
    const status = String(view.status || 'waiting');
    const connectionState = classifyRuntimeConnectionState({
      ...view,
      connectionState: view.runtime_connection_state,
      secondsSince: view.progress_age_seconds ?? view.seconds_since_progress,
      stalledReason: view.stalled_reason,
    });
    panel.dataset.atlasRuntimeConnectionState = connectionState;
    ['live', 'reconnecting', 'stale', 'stalled', 'terminal', 'unknown'].forEach((state) => panel.classList.remove(`atlas-runtime-${state}`));
    panel.classList.add(`atlas-runtime-${connectionState}`);
    const total = Number(view.items_total || 0);
    const started = Number(view.items_started || 0);
    const completed = Number(view.items_completed || 0);
    ['plan', 'patch', 'approve', 'apply', 'verify', 'summary'].forEach((stage) => updateStage(panel, stage, 'pending', ''));
    updateStage(panel, 'plan', (phase === 'approving' || phase === 'planning') ? 'running' : 'done', (phase === 'approving' || phase === 'planning') ? (view.message || phase) : '');
    if (phase === 'planning') {
      updateStage(panel, 'patch', 'pending', view.message || 'Planning');
    } else if (phase === 'blocked_safety_review') {
      updateStage(panel, 'patch', 'failed', `Blocked by safety gate: ${view.block_reason || 'safety_gate_blocked'}`);
    } else if (phase === 'failed' || status === 'failed') {
      if (view.failed_phase === 'verify') {
        updateStage(panel, 'patch', 'done', `${completed || started}/${total || '-'}`);
        updateStage(panel, 'approve', 'done', '');
        updateStage(panel, 'apply', 'done', `${started || completed}/${total || '-'}`);
        updateStage(panel, 'verify', 'failed', view.error || '');
        updateStage(panel, 'summary', 'failed', view.error || '');
      } else {
        updateStage(panel, 'patch', 'failed', view.error || view.message || 'failed before first patch');
      }
    } else if (phase === 'patch_generation') {
      const patchState = String((incomingPatch.state || status || '')).toLowerCase();
      const activeRepair = patchState === 'repairing';
      const detail = activeRepair ? `自動修正中: attempt ${incomingPatch.attempt || 0}` : (total ? `${started}/${total}` : (view.message || 'Patchを生成・検証しています'));
      const stageState = ['failed', 'blocked'].includes(patchState) ? 'failed' : (patchState === 'succeeded' || status === 'completed' ? 'done' : (status === 'running' || ['queued', 'validating', 'repairing', 'retrying'].includes(patchState) ? 'running' : 'pending'));
      updateStage(panel, 'patch', stageState, detail);
    } else if (phase === 'applying') {
      updateStage(panel, 'patch', 'done', `${completed || started}/${total || '-'}`);
      updateStage(panel, 'approve', 'done', '');
      updateStage(panel, 'apply', 'running', `${started}/${total || '-'}`);
    } else if (phase === 'verifying') {
      updateStage(panel, 'patch', 'done', `${completed || started}/${total || '-'}`);
      updateStage(panel, 'approve', 'done', '');
      updateStage(panel, 'apply', 'done', `${started}/${total || '-'}`);
      updateStage(panel, 'verify', 'running', `completed ${completed}`);
    } else if (phase === 'completed') {
      updateStage(panel, 'patch', 'done', `${completed || started}/${total || '-'}`);
      updateStage(panel, 'approve', 'done', '');
      updateStage(panel, 'apply', 'done', `${started || completed}/${total || '-'}`);
      updateStage(panel, 'verify', 'done', `completed ${completed}`);
      updateStage(panel, 'summary', 'done', status);
    }

    const summary = panel.querySelector('.atlas-claude-summary-block');
    if (summary) {
      summary.innerHTML = '';
      // Minimal, user-facing progress by default; the verbose diagnostics (status,
      // ids, source, repair strategy, message…) are only added when something went
      // wrong, so the normal view stays readable and the stage row above carries the
      // high-level pipeline state.
      const PHASE_LABELS = {
        patch_generation: 'パッチ生成',
        planning: 'プラン生成',
        approving: '承認',
        applying: '適用',
        verifying: '検証',
        completed: '完了',
        failed: '失敗',
        blocked_safety_review: '安全ゲートでブロック',
      };
      const lc = (value) => String(value || '').toLowerCase();
      const phaseLabel = PHASE_LABELS[phase] || phase;
      const hasProblem = !!(
        view.error || view.block_reason || view.requires_user_action
        || ['failed', 'blocked'].includes(lc(status))
        || phase === 'failed' || phase === 'blocked_safety_review'
      );
      // Normal running progress and the "current item" are already shown by the per-item plan-step
      // checklist and the theme-color indicator, so this panel stays EMPTY during a healthy run and
      // only surfaces (a) an active self-correction re-run, or (b) a problem (concise reason + action).
      const rows = [];
      void phaseLabel;
      if (incomingPatch.state === 'repairing') {
        rows.push(`🛠 不具合を自動修正して再検証中（attempt ${incomingPatch.attempt || 0}）`);
      }
      if (view.restored_progress && view.message) {
        rows.push(`復元: ${String(view.message).slice(0, 200)}`);
      }
      if (connectionState !== 'live' || view.runtime_connection_state || view.progress_age_seconds != null || view.stalled_reason) {
        rows.push(`状態: ${runtimeConnectionLabel(connectionState, {
          ...view,
          secondsSince: view.progress_age_seconds ?? view.seconds_since_progress,
          stalledReason: view.stalled_reason,
        }).slice(0, 200)}`);
      }
      if (hasProblem) {
        const reason = view.block_reason || view.error || view.message || '';
        if (reason) rows.push(`理由: ${String(reason).slice(0, 200)}`);
        rows.push(`推奨操作: ${(view.next_actions || ['wait']).join(', ') || 'wait'}`);
      }
      rows.filter(Boolean).forEach((text) => {
        const div = document.createElement('div');
        div.className = 'atlas-claude-stage-detail';
        div.textContent = text;
        summary.appendChild(div);
      });
      // This panel is the authoritative final render of a failed run (it overwrites the pipeline
      // summary), so the actionable Retry / Revise controls must live here too — otherwise a failed
      // run shows only the "推奨操作: retry" TEXT with no clickable way to recover.
      const _nextActions = Array.isArray(view.next_actions) ? view.next_actions : [];
      if (view.requires_user_action && _nextActions.includes('retry')) {
        appendRecoveryActions(summary, view.pool_id || (block && block.dataset && block.dataset.poolId));
      }
    }
    if (dom.transcript) dom.transcript.scrollTop = dom.transcript.scrollHeight;
    return panel;
  }

  // Actionable recovery controls for a failed run: a Retry (re-run, skipping already-applied items
  // so only the failed ones regenerate) and a Revise-plan button. Previously the failure summary
  // only printed text hints, leaving the user with no way to recover from the UI.
  function appendRecoveryActions(parentBox, poolId) {
    const pid = String(poolId || '').trim();
    if (!pid || !parentBox) return;
    const actions = document.createElement('div');
    actions.className = 'atlas-claude-recovery-actions';
    actions.style.display = 'flex';
    actions.style.gap = '6px';
    actions.style.marginTop = '8px';
    actions.style.flexWrap = 'wrap';

    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'atlas-claude-primary-btn';
    retry.textContent = '生成をリトライ';
    retry.addEventListener('click', () => {
      Array.from(actions.querySelectorAll('button')).forEach((b) => { b.disabled = true; });
      state.dismissedApprovalPlanKeys?.delete?.(pid);
      approveAndRunPipeline(pid, { resume: true });
    });

    const revise = document.createElement('button');
    revise.type = 'button';
    revise.className = 'atlas-claude-secondary-btn';
    revise.textContent = 'プランを改訂';
    revise.addEventListener('click', () => {
      const note = (root.prompt && root.prompt('改訂依頼の内容（任意）')) || '';
      requestPlanRevision(pid, note);
    });

    actions.append(retry, revise);
    parentBox.appendChild(actions);
  }

  function renderPipelineSummary(block, d) {
    if (!block) return;
    const activePatch = block.__atlasPatchGenerationState || null;
    if (activePatch && ['repairing', 'failed', 'blocked', 'succeeded'].includes(String(activePatch.state || ''))) {
      renderRuntimeStatusPanel(runtimeStatusPayload(block.dataset?.poolId || '', {
        phase: 'patch_generation',
        status: activePatch.state,
        run_id: activePatch.run_id || '',
        message: activePatch.state === 'repairing' ? `自動修正中: attempt ${activePatch.attempt || 0}` : (activePatch.reason_code || 'Patch generation status restored'),
        requires_user_action: ['failed', 'blocked'].includes(String(activePatch.state || '')),
        next_actions: activePatch.state === 'repairing' ? ['wait', 'cancel'] : ['retry', 'revise plan', 'cancel'],
        authoritative_source: 'reconciled patch_generation state',
        patch_generation: activePatch,
      }), block);
      if (activePatch.state === 'repairing') return;
    }
    const summary = block.querySelector('.atlas-claude-summary-block');
    if (!summary) return;
    summary.innerHTML = '';

    const stopped = d.status === 'patch_generation_failed' || d.status === 'autopilot_failed' || d.status === 'blocked_safety_review';

    // Counts: when autopilot did not run, the 0/0/0/0 line is misleading.
    // Show an explicit "stopped" line with the upstream failure instead.
    const counts = document.createElement('div');
    counts.className = 'atlas-claude-summary-counts';
    if (d.status === 'patch_generation_failed') {
      const n = (d.genFailures || []).length;
      counts.textContent = `Patch 段階で停止 — ${n} 件の生成失敗。Autopilot は未実行。`;
    } else if (d.status === 'autopilot_failed') {
      counts.textContent = `Autopilot 起動失敗 — ${d.error || 'unknown'}`;
    } else if (d.status === 'blocked_safety_review') {
      counts.textContent = `Safety gate blocked — reason: ${d.stop_reason || 'safety_gate_blocked'}`;
    } else {
      counts.textContent = `完了 ${d.completed_count || 0}  失敗 ${d.failed_count || 0}  ブロック ${d.blocked_count || 0}  スキップ ${d.skipped_count || 0}`;
    }
    summary.appendChild(counts);
    updateStage(block, 'summary', (d.failed_count > 0 || stopped) ? 'failed' : 'done', d.stop_reason ? `stop: ${d.stop_reason}` : '');

    // Patch-stage failure detail: surface per-item error messages so the user
    // can investigate WHY generation failed (LLM down, missing fields, etc.).
    if (d.status === 'patch_generation_failed' && d.genFailures && d.genFailures.length) {
      const box = document.createElement('div');
      box.className = 'atlas-claude-summary-recovery';
      const head = document.createElement('div');
      head.className = 'atlas-claude-summary-head';
      head.textContent = `Patch 生成失敗の詳細 (${d.genFailures.length} 件)`;
      box.appendChild(head);
      const ul = document.createElement('ul');
      d.genFailures.forEach((f) => {
        const li = document.createElement('li');
        const msg = String(f.msg || 'unknown').slice(0, 500);
        li.textContent = `${f.id}: ${msg}`;
        ul.appendChild(li);
      });
      box.appendChild(ul);
      const hint = document.createElement('div');
      hint.className = 'atlas-claude-summary-pr-hint';
      hint.innerHTML = '<strong>調査方法:</strong> ① LLM が起動しているか（ヘッダーの LLM ready 表示）/ ② 失敗した item の goal / target_files / description / done_definition が埋まっているか / ③ サーバ側ログで <code>patch_proposal</code> 関連スタックトレース';
      box.appendChild(hint);
      appendRecoveryActions(box, block.dataset?.poolId || d.pool_id);
      summary.appendChild(box);
    }

    // Items that produced no patch content (so they were NOT approved/applied). This makes the
    // "why was nothing applied" explicit instead of a silent skip.
    if (Array.isArray(d.no_content_failures) && d.no_content_failures.length) {
      const box = document.createElement('div');
      box.className = 'atlas-claude-summary-recovery';
      const head = document.createElement('div');
      head.className = 'atlas-claude-summary-head';
      head.textContent = `パッチ内容なしで未適用 (${d.no_content_failures.length} 件)`;
      box.appendChild(head);
      const ul = document.createElement('ul');
      d.no_content_failures.forEach((f) => {
        const li = document.createElement('li');
        li.textContent = `${f.id}: ${String(f.msg || 'no_patch_content').slice(0, 300)}`;
        ul.appendChild(li);
      });
      box.appendChild(ul);
      const hint = document.createElement('div');
      hint.className = 'atlas-claude-summary-pr-hint';
      hint.innerHTML = '<strong>対処:</strong> ① より高性能な LLM を選択 / ② item の target_files と done_definition を具体化 / ③ ゴールをファイル単位の具体タスクに分解して再実行';
      box.appendChild(hint);
      appendRecoveryActions(box, block.dataset?.poolId || d.pool_id);
      summary.appendChild(box);
    }

    // Changed files (summary-first: list top 10, full list in <details>).
    const allChanged = collectChangedFiles(d.item_results || []);
    if (allChanged.length) {
      const filesBox = document.createElement('div');
      filesBox.className = 'atlas-claude-summary-files';
      const head = document.createElement('div');
      head.className = 'atlas-claude-summary-head';
      head.textContent = `変更ファイル ${allChanged.length} 件`;
      filesBox.appendChild(head);
      const top = allChanged.slice(0, 10);
      const ul = document.createElement('ul');
      top.forEach((f) => {
        const li = document.createElement('li');
        li.textContent = f;
        ul.appendChild(li);
      });
      filesBox.appendChild(ul);
      if (allChanged.length > 10) {
        const det = document.createElement('details');
        const sm = document.createElement('summary');
        sm.textContent = `… 残り ${allChanged.length - 10} 件`;
        det.appendChild(sm);
        const ul2 = document.createElement('ul');
        allChanged.slice(10).forEach((f) => {
          const li = document.createElement('li');
          li.textContent = f;
          ul2.appendChild(li);
        });
        det.appendChild(ul2);
        filesBox.appendChild(det);
      }
      summary.appendChild(filesBox);
    }

    // Per-item summary (status + reason).
    const itemResults = d.item_results || [];
    if (itemResults.length) {
      const det = document.createElement('details');
      det.className = 'atlas-claude-summary-items';
      const sm = document.createElement('summary');
      sm.textContent = `アイテム別結果 (${itemResults.length})`;
      det.appendChild(sm);
      const ul = document.createElement('ul');
      itemResults.forEach((r) => {
        const li = document.createElement('li');
        const precise = preciseVerificationReason(r);
        const displayReason = precise && r.reason === 'verification_failed' ? `verification_failed:${precise}` : (r.reason || precise || '');
        const reason = displayReason ? ` (${displayReason})` : '';
        li.textContent = `${r.item_id}: ${r.status}${reason}`;
        ul.appendChild(li);
      });
      det.appendChild(ul);
      summary.appendChild(det);
    }

    // Failure recovery suggestion.
    // NOTE: failure_stop_suggestion defaults to an empty object {} on every item
    // (backend pydantic default). An empty {} is truthy in JS, so a bare truthy
    // check would wrongly include skipped items (e.g. missing_patch_or_content)
    // and render them as failures. Only items with a *populated* suggestion are
    // real verification failures, so require a non-empty object here.
    const failuresWithSuggestion = (d.item_results || []).filter(
      (r) => r.failure_stop_suggestion && Object.keys(r.failure_stop_suggestion).length > 0
    );
    if (failuresWithSuggestion.length) {
      const recovery = renderRecoverySection(failuresWithSuggestion);
      summary.appendChild(recovery);
    }

    // Draft PR artifact.
    const prInfo = extractDraftPr(d);
    if (prInfo) {
      const pr = document.createElement('div');
      pr.className = 'atlas-claude-summary-pr';
      if (prInfo.url) {
        const a = document.createElement('a');
        a.href = prInfo.url;
        a.target = '_blank';
        a.rel = 'noreferrer noopener';
        a.textContent = `📦 Draft PR ${prInfo.number ? '#' + prInfo.number : ''}`.trim();
        pr.appendChild(a);
      } else if (prInfo.number) {
        pr.textContent = `📦 Draft PR #${prInfo.number}`;
      }
      summary.appendChild(pr);
    } else if ((d.completed_count || 0) > 0) {
      // No PR yet, but applied changes succeeded — offer manual creation hint.
      const hint = document.createElement('div');
      hint.className = 'atlas-claude-summary-pr-hint';
      hint.textContent = 'Draft PR 未作成。変更ファイルを確認してから手動で `gh pr create --draft` を実行してください。';
      summary.appendChild(hint);
    }

    // Resume control: when a run ended with any item still unfinished (a generation failure, a
    // verify/apply failure, no-content items, or an early stop), offer "続きからリトライ". It re-runs
    // ONLY the un-applied items — applied ones are skipped (flag-safe), so the user can continue from
    // where it stopped instead of restarting the whole plan. Hidden when everything completed cleanly.
    const resumePoolId = (block.dataset && block.dataset.poolId) || '';
    const hasUnfinished = (d.failed_count || 0) > 0
      || (Array.isArray(d.no_content_failures) && d.no_content_failures.length > 0)
      || (Array.isArray(d.genFailures) && d.genFailures.length > 0)
      || d.status === 'patch_generation_failed'
      || d.status === 'autopilot_failed'
      || d.status === 'completed_with_failures';
    if (resumePoolId && hasUnfinished) {
      const resumeBox = document.createElement('div');
      resumeBox.className = 'atlas-claude-summary-resume';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'atlas-claude-resume-btn';
      btn.textContent = '▶ 続きからリトライ';
      btn.title = '未適用の項目だけを再実行します（適用済みの項目はスキップ）';
      btn.addEventListener('click', () => {
        btn.disabled = true;
        btn.textContent = '再実行中…';
        Promise.resolve(approveAndRunPipeline(resumePoolId, { resume: true })).catch(() => {});
      });
      const note = document.createElement('div');
      note.className = 'atlas-claude-summary-pr-hint';
      note.textContent = '未適用の項目のみ再実行します（適用済みはスキップ）。';
      resumeBox.append(btn, note);
      summary.appendChild(resumeBox);
    }

    if (dom.transcript) dom.transcript.scrollTop = dom.transcript.scrollHeight;
  }

  function collectChangedFiles(itemResults) {
    const set = new Set();
    itemResults.forEach((r) => {
      const sa = r.safe_apply_result || {};
      (sa.changed_files || []).forEach((f) => set.add(f));
      const stop = r.failure_stop_suggestion || {};
      (stop.changed_files || []).forEach((f) => set.add(f));
    });
    return Array.from(set);
  }

  function extractDraftPr(d) {
    // Look on the autopilot result first, then on item results.
    if (d.draft_pr_url || d.draft_pr_number) {
      return { url: d.draft_pr_url || '', number: d.draft_pr_number || 0 };
    }
    for (const r of (d.item_results || [])) {
      const sa = r.safe_apply_result || {};
      if (sa.draft_pr_url || sa.draft_pr_number) {
        return { url: sa.draft_pr_url || '', number: sa.draft_pr_number || 0 };
      }
    }
    return null;
  }


  function preciseVerificationReason(item) {
    const reason = item && item.reason ? String(item.reason) : '';
    if (reason.startsWith('verification_failed:')) return reason.replace(/^verification_failed:/, '');
    const stop = (item && item.failure_stop_suggestion) || {};
    const metaReason = stop.metadata && stop.metadata.primary_verification_reason;
    if (metaReason) return String(metaReason);
    const warnings = [];
    if (item && Array.isArray(item.warnings)) warnings.push(...item.warnings);
    const vrWarnings = item && item.verification_result && Array.isArray(item.verification_result.warnings)
      ? item.verification_result.warnings : [];
    warnings.push(...vrWarnings);
    const priorities = ['browser_smoke_failed:', 'visual_contract_failed', 'visual_missing:', 'test_harness_unavailable', 'pytest_not_installed'];
    for (const prefix of priorities) {
      const found = warnings.find((w) => String(w) === prefix || String(w).startsWith(prefix));
      if (found) return String(found);
    }
    return '';
  }

  function verificationConsoleErrors(item) {
    const stop = (item && item.failure_stop_suggestion) || {};
    const stopMeta = stop.metadata || {};
    const direct = item && item.browser_smoke && item.browser_smoke.console_errors;
    const nested = item && item.verification_result && item.verification_result.metadata
      && item.verification_result.metadata.browser_smoke
      && item.verification_result.metadata.browser_smoke.console_errors;
    const errors = stopMeta.console_errors || direct || nested || [];
    return Array.isArray(errors) ? errors.map((e) => String(e)).filter(Boolean) : [];
  }

  function renderAutonomousWorkflowState(view) {
    if (!dom.transcript || !view) return;
    const poolId = view.pool_id || '';
    const block = appendStageBlock(poolId || 'autonomous');
    if (!block) return;
    const phase = String(view.current_phase || 'idle');
    const status = String(view.status || view.automation_state || '');
    ['plan', 'patch', 'approve', 'apply', 'verify'].forEach((stage) => updateStage(block, stage, 'pending', ''));
    // A safety block must NOT leave the Patch/Apply stages spinning: stop on the block and surface the
    // reason. Derived from backend status so a reload shows the same (no spinner desync).
    if (status === 'blocked_safety_review' && phase !== 'needs_scope_confirmation' && phase !== 'waiting_for_critical_decision') {
      const reason = String(view.stop_reason || (view.evidence_summary && view.evidence_summary.safety_block_reason) || 'safety gate blocked');
      updateStage(block, 'plan', 'done', '');
      updateStage(block, 'patch', 'failed', `safety gate blocked — ${reason}`);
    } else if (phase === 'needs_scope_confirmation') updateStage(block, 'plan', 'failed', 'clarification required');
    else if (phase === 'waiting_for_critical_decision') updateStage(block, 'plan', 'failed', 'critical decision required');
    else if (phase === 'replanning_lower_impact') updateStage(block, 'plan', 'running', 'lower-impact replanning');
    else if (phase === 'candidate_generation') updateStage(block, 'patch', 'running', '');
    else if (phase === 'candidate_apply') updateStage(block, 'apply', 'running', '');
    else if (phase === 'verification') updateStage(block, 'verify', 'running', '');
    else if (phase === 'failure_analysis') updateStage(block, 'verify', 'failed', 'repairable verification failure');
    else if (phase === 'bounded_repair') updateStage(block, 'verify', 'running', 'bounded repair');
    else if (phase === 'final_summary') updateStage(block, 'summary', 'done', view.status || '');
    renderAutonomousWorkflowSummary(block, view);
  }

  function renderAutonomousWorkflowSummary(block, view) {
    const summary = block && block.querySelector('.atlas-claude-summary-block');
    if (!summary) return;
    summary.innerHTML = '';
    const profile = view.active_profile || {};
    const evidence = view.evidence_summary || {};
    const plan = view.plan_summary || {};
    const decisions = view.decision_targets || {};
    const controls = view.controls || {};
    const rows = [
      `state: ${view.automation_state || view.status || '-'}`,
      `phase: ${view.current_phase || '-'}`,
      `profile: ${profile.profile || 'review_only'} / ${profile.envelope_id || 'none'} / ${profile.runtime_level || '-'}`,
      `plan: processed ${plan.processed_count || 0}, completed ${plan.completed_count || 0}, failed ${plan.failed_count || 0}`,
      `next: ${view.next_action || '-'}`,
    ];
    rows.forEach((text) => {
      const div = document.createElement('div');
      div.className = 'atlas-claude-stage-detail';
      div.textContent = text;
      summary.appendChild(div);
    });
    renderAutonomousList(summary, 'Changed files', evidence.changed_files || []);
    const verification = evidence.verification && evidence.verification.statuses ? evidence.verification.statuses : {};
    renderAutonomousList(summary, 'Verification', Object.keys(verification).map((key) => `${key}: ${verification[key]}`));
    const usage = evidence.llm_usage || {};
    if (usage.calls) {
      const tdiv = document.createElement('div');
      tdiv.className = 'atlas-claude-stage-detail';
      // Token usage with a thinking-vs-output split (think = reasoning tokens, output = answer).
      tdiv.textContent = `tokens: prompt ${usage.prompt_tokens || 0}, think ${usage.thinking_tokens || 0}, output ${usage.output_tokens || 0}, total ${usage.total_tokens || 0} (${usage.calls} call${usage.calls === 1 ? '' : 's'})`;
      summary.appendChild(tdiv);
    }
    renderAutonomousFailureSummary(summary, evidence.verification_failure_summary || {});
    renderAutonomousRepairPlan(summary, evidence.repair_plan || {});
    renderAutonomousCIFailure(summary, evidence.ci_failure_evidence || {}, evidence.ci_repair_plan || {});
    renderAutoMergeReadiness(summary, evidence.auto_merge_readiness || {});
    renderAutonomousList(summary, 'Repair attempts', (evidence.repair_attempts || []).map((r) => `${r.item_id}: ${r.kind} ${r.status || ''}`));
    renderAutonomousSubPhaseTimeline(summary, evidence.item_sub_phases || []);
    renderAutonomousList(summary, 'User-visible warnings', view.user_visible_warnings || []);
    renderWorkbenchControls(summary, controls);
    if (decisions.clarification && decisions.clarification.visible) {
      appendAutonomousDecision(summary, 'Clarification required', controls.can_answer_clarification);
    }
    if (decisions.critical_event && decisions.critical_event.visible) {
      appendAutonomousDecision(summary, 'Critical event decision required', controls.can_approve_critical_event || controls.can_reject_critical_event);
    }
    if (decisions.lower_impact_replanning && decisions.lower_impact_replanning.visible) {
      appendAutonomousDecision(summary, 'Lower-impact replanning visible', controls.can_continue);
    }
    const draft = evidence.draft_pr || {};
    if (draft.ready || draft.artifact_path || draft.body_path || draft.draft_pr_url) {
      renderAutonomousList(summary, 'Draft PR artifact', [
        draft.draft_pr_url ? `url: ${draft.draft_pr_url}` : '',
        draft.artifact_path ? `artifact: ${draft.artifact_path}` : '',
        draft.body_path ? `body: ${draft.body_path}` : '',
      ]);
    }
  }

  function renderAutonomousSubPhaseTimeline(host, items) {
    if (!host) return;
    const rows = (items || []).filter((item) => (item.sub_phases || []).length);
    if (!rows.length) return;
    const block = document.createElement('details');
    block.className = 'atlas-autonomous-subphase-timeline';
    const title = document.createElement('summary');
    title.textContent = 'Item timeline';
    block.appendChild(title);
    rows.forEach((item) => {
      const card = document.createElement('div');
      card.className = 'atlas-autonomous-subphase-item';
      const phases = (item.sub_phases || []).map((phase) => {
        const detail = phase.detail ? ` ${JSON.stringify(phase.detail)}` : '';
        return `<li>${badge(phase.name || 'phase', phase.status || 'muted')} <span>${esc(phase.status || '')}</span><small>${esc(detail)}</small></li>`;
      }).join('');
      card.innerHTML = `<b>${esc(item.item_id || '-')}</b> ${badge(item.status || 'item', item.status || 'muted')}<ol>${phases}</ol>`;
      block.appendChild(card);
    });
    host.appendChild(block);
  }

  function renderAutonomousList(parent, title, values) {
    const cleaned = (values || []).map((v) => String(v || '')).filter(Boolean);
    if (!cleaned.length) return;
    const box = document.createElement('div');
    box.className = 'atlas-claude-summary-recovery';
    const head = document.createElement('div');
    head.className = 'atlas-claude-summary-head';
    head.textContent = title;
    box.appendChild(head);
    const ul = document.createElement('ul');
    cleaned.slice(0, 12).forEach((value) => {
      const li = document.createElement('li');
      li.textContent = value;
      ul.appendChild(li);
    });
    box.appendChild(ul);
    parent.appendChild(box);
  }

  function renderAutonomousFailureSummary(parent, failure) {
    if (!failure || !Object.keys(failure).length) return;
    const lines = [
      failure.user_facing_summary || '',
      (failure.failed_contracts || []).length ? `failed: ${(failure.failed_contracts || []).join(', ')}` : '',
      failure.likely_cause ? `likely cause: ${failure.likely_cause}` : '',
      failure.verification_tool_error ? `tool: ${failure.verification_tool_error}` : '',
      typeof failure.retry_count_remaining === 'number' ? `retries remaining: ${failure.retry_count_remaining}` : '',
    ].filter(Boolean);
    const box = document.createElement('div');
    box.className = 'atlas-claude-summary-recovery';
    const head = document.createElement('div');
    head.className = 'atlas-claude-summary-head';
    head.textContent = failure.user_facing_title || 'Verification failure';
    box.appendChild(head);
    const ul = document.createElement('ul');
    lines.slice(0, 10).forEach((value) => {
      const li = document.createElement('li');
      li.textContent = value;
      ul.appendChild(li);
    });
    box.appendChild(ul);
    const steps = Array.isArray(failure.recommended_repair_steps) ? failure.recommended_repair_steps : [];
    if (steps.length) {
      renderAutonomousList(box, 'Recommended repair steps', steps);
    }
    parent.appendChild(box);
  }

  function renderAutonomousRepairPlan(parent, plan) {
    if (!plan || !Object.keys(plan).length) return;
    const lines = [
      `status: ${plan.status || '-'}`,
      (plan.allowed_repair_files || []).length ? `allowed files: ${(plan.allowed_repair_files || []).join(', ')}` : '',
      typeof plan.retry_index === 'number' && typeof plan.max_retries === 'number' ? `retry: ${plan.retry_index}/${plan.max_retries}` : '',
      plan.post_repair_verification_required ? 'post-repair verification required' : '',
      (plan.blocked_reasons || []).length ? `blocked: ${(plan.blocked_reasons || []).join(', ')}` : '',
    ].filter(Boolean);
    renderAutonomousList(parent, 'Bounded repair plan', lines);
    if ((plan.concrete_repair_steps || []).length) {
      renderAutonomousList(parent, 'Concrete repair steps', plan.concrete_repair_steps || []);
    }
  }

  function renderAutonomousCIFailure(parent, evidence, plan) {
    if ((!evidence || !Object.keys(evidence).length) && (!plan || !Object.keys(plan).length)) return;
    renderAutonomousList(parent, 'CI failure evidence', [
      evidence.source ? `source: ${evidence.source}` : '',
      evidence.failing_command ? `command: ${evidence.failing_command}` : '',
      (evidence.failing_test_names || []).length ? `tests: ${(evidence.failing_test_names || []).join(', ')}` : '',
      evidence.confidence ? `confidence: ${evidence.confidence}` : '',
    ]);
    renderAutonomousList(parent, 'CI bounded repair plan', [
      plan.status ? `status: ${plan.status}` : '',
      plan.failure_class ? `class: ${plan.failure_class}` : '',
      (plan.allowed_repair_files || []).length ? `allowed files: ${(plan.allowed_repair_files || []).join(', ')}` : '',
      plan.post_repair_verification_required ? 'post-CI repair verification required' : '',
    ]);
  }

  function renderAutoMergeReadiness(parent, readiness) {
    if (!readiness || !Object.keys(readiness).length) return;
    renderAutonomousList(parent, 'Supervised auto-merge readiness', [
      readiness.status ? `status: ${readiness.status}` : '',
      `ready: ${!!readiness.ready}`,
      `ci_green_required: ${!!readiness.ci_green_required}`,
      'direct_merge_enabled: false',
      'merge_executed: false',
      'merge requires explicit future gate/manual action',
      (readiness.blocking_reasons || []).length ? `blocked: ${(readiness.blocking_reasons || []).join(', ')}` : '',
    ]);
  }

  function appendAutonomousDecision(parent, label, enabled) {
    const row = document.createElement('div');
    row.className = 'atlas-claude-summary-pr-hint';
    row.textContent = `${label}: ${enabled ? 'backend action available' : 'backend action blocked'}`;
    parent.appendChild(row);
  }

  function _visualRepairGuidanceForProfile(repairProfile) {
    if (repairProfile === 'canvas_game_repair') {
      return 'run Debug Review and inspect index.html; add requestAnimationFrame loop, input handling, update/render separation, collision handling, HUD state, and visible motion/color/canvas signals.';
    }
    if (repairProfile === 'animated_dom_repair') {
      return 'ensure the animated element exists in the DOM; add CSS @keyframes, Web Animations API, or requestAnimationFrame updating style properties (transform, opacity, color) over time; verify style changes are detectable across frames.';
    }
    if (repairProfile === 'canvas_animation_repair') {
      return 'ensure a <canvas> element is present; initialise the rendering context (getContext); ensure requestAnimationFrame draws each frame so frame_changes_over_time is detectable.';
    }
    if (repairProfile === 'static_html_repair') {
      return 'add or restore expected HTML content; fix invalid HTML syntax; resolve load errors (missing linked CSS/JS files).';
    }
    if (repairProfile === 'chart_repair') {
      return 'ensure the chart element (SVG, canvas, or library root) is present; ensure data points, bars, lines, or slices are rendered with correct data bindings.';
    }
    if (repairProfile === 'ui_component_repair') {
      return 'add missing controls (buttons, inputs, selects); ensure event bindings trigger state updates; add labels and ARIA attributes for interactive elements.';
    }
    if (repairProfile === 'universal_visual_repair' || repairProfile === '') {
      return 'run Debug Review and inspect index.html; ensure the page loads without JS errors, HTML content is present, and any requested animation (CSS @keyframes / requestAnimationFrame) or interactive controls are implemented.';
    }
    // Generic fallback for any unrecognised profile
    return 'run Debug Review and inspect index.html; ensure the required visual signals (animation, interaction state, or content structure) are present and detectable.';
  }

  function visualFailureDetails(item) {
    const warnings = [];
    if (item && Array.isArray(item.warnings)) warnings.push(...item.warnings);
    const verification = item && (item.verification_result || item.auto_verification_result || {});
    if (Array.isArray(verification.warnings)) warnings.push(...verification.warnings);
    const metadata = verification.metadata || (item && item.metadata) || {};
    const visual = metadata.visual_contract || {};
    const smoke = metadata.browser_smoke || {};
    const pipelineMeta = metadata.visual_pipeline || {};
    const missing = Array.isArray(visual.missing) ? visual.missing.map((x) => String(x)).filter(Boolean) : [];
    const visualWarnings = warnings.map((w) => String(w)).filter((w) => w.startsWith('visual_missing:'));
    const smokeStatus = String(smoke.status || '');
    const smokeReason = String(smoke.reason || '');
    if (!missing.length && !visualWarnings.length && !smokeStatus) return '';
    const parts = [];
    if (visual.status) parts.push(`visual_contract.status=${visual.status}`);
    if (missing.length) parts.push(`missing=${missing.join(', ')}`);
    if (visualWarnings.length) parts.push(`warnings=${visualWarnings.join(', ')}`);
    if (smokeStatus || smokeReason) parts.push(`browser_smoke=${smokeStatus || '-'}${smokeReason ? ':' + smokeReason : ''}`);
    const repairProfile = String(pipelineMeta.repair_profile || '');
    parts.push('Repair guidance: ' + _visualRepairGuidanceForProfile(repairProfile));
    return `Visual contract failed: ${parts.join(' | ')}`;
  }

  function primaryRecoveryReason(stop, item) {
    const metaReason = stop && stop.metadata && stop.metadata.primary_verification_reason;
    if (metaReason) return String(metaReason);
    return preciseVerificationReason(item);
  }

  function renderRecoverySection(failures) {
    const box = document.createElement('div');
    box.className = 'atlas-claude-summary-recovery';
    const head = document.createElement('div');
    head.className = 'atlas-claude-summary-head';
    head.textContent = `失敗 ${failures.length} 件 — recovery 提案`;
    box.appendChild(head);
    const ul = document.createElement('ul');
    failures.forEach((r) => {
      const stop = r.failure_stop_suggestion || {};
      const li = document.createElement('li');
      const primary = primaryRecoveryReason(stop, r);
      const reason = primary ? `Verification failed: ${primary}` : (stop.reason || r.reason || 'unknown');
      const actions = (stop.suggested_manual_actions || []).join(', ');
      const consoleErrors = verificationConsoleErrors(r);
      const visualDetails = primary === 'visual_contract_failed' || String(primary).startsWith('visual_missing:')
        ? visualFailureDetails(r) : '';
      li.textContent = `${r.item_id}: ${reason}${actions ? ' — ' + actions : ''}${visualDetails ? ' — ' + visualDetails : ''}${consoleErrors.length ? ' — console_errors: ' + consoleErrors.slice(0, 3).join(' | ') : ''}`;
      ul.appendChild(li);
    });
    box.appendChild(ul);
    const actions = document.createElement('div');
    actions.className = 'atlas-claude-summary-actions';
    const rec = document.createElement('button');
    rec.type = 'button';
    rec.className = 'atlas-claude-secondary-btn';
    rec.textContent = 'Recover (最新状態を再ロード)';
    rec.addEventListener('click', () => delegateRecover());
    actions.appendChild(rec);
    const rollback = document.createElement('button');
    rollback.type = 'button';
    rollback.className = 'atlas-claude-secondary-btn';
    rollback.textContent = 'Rollback 手順を表示';
    rollback.addEventListener('click', () => {
      const stops = failures.map((r) => r.failure_stop_suggestion).filter(Boolean);
      const snapshots = stops
        .map((s) => s.change_snapshot && s.change_snapshot.manifest_path)
        .filter(Boolean);
      const lines = snapshots.length
        ? ['## Rollback 手順', '', '1. 以下の snapshot manifest を参照して手動 restore を実行してください:', ...snapshots.map((p) => `   - \`${p}\``), '', '2. Restore 完了後、再度 Plan を作り直して Send してください。']
        : ['## Rollback 手順', '', 'Snapshot manifest が未生成のため手動 restore は不要です。元の Git 状態をご確認ください。'];
      pushAtlasMessage(lines.join('\n'));
    });
    actions.appendChild(rollback);
    box.appendChild(actions);
    return box;
  }

  async function renderPlanPoolMarkdown(poolId, opts = {}) {
    if (!root.AtlasPipelineAPI) return;
    // Primary view: a concise structured list of the plan items. The verbose raw markdown
    // (Status / Planning Depth / Items table / Warnings / Errors) is tucked into a collapsible
    // <details> so the execution steps are readable at a glance.
    let items = [];
    let strategic = null;
    let poolStatus = '';
    let poolMeta = {};
    try {
      const pool = await root.AtlasPipelineAPI.getPlanPool(poolId);
      if (pool && pool.ok && pool.data) {
        items = pool.data.items || pool.data.plan_items || [];
        poolStatus = String(pool.data.status || (pool.data.plan_pool && pool.data.plan_pool.status) || '');
        const meta = pool.data.metadata || (pool.data.plan_pool && pool.data.plan_pool.metadata) || {};
        poolMeta = meta || {};
        if (meta && typeof meta.strategic_plan === 'object') strategic = meta.strategic_plan;
      }
    } catch (_e) { items = []; }

    let rawMarkdown = '';
    if (root.AtlasPipelineAPI.getPlanPoolMarkdown) {
      try {
        const md = await root.AtlasPipelineAPI.getPlanPoolMarkdown(poolId, workspaceId());
        if (md && md.ok) rawMarkdown = typeof md.data === 'string' ? md.data : (md.data && (md.data.markdown || md.data.text)) || '';
      } catch (_e) { rawMarkdown = ''; }
    }

    if (!items.length && !rawMarkdown && !strategic) {
      // Non-persisting: this is a transient render-time status, never a conversation event. Persisting
      // it (the old behavior) duplicated it into the log on every reload.
      appendMessage('atlas', 'Plan was created. Use Recover to view it.', false);
      return;
    }
    if (!dom.transcript) {
      pushAtlasMessage(rawMarkdown ? rawMarkdown.slice(0, 4000) : 'Plan was created.');
      return;
    }
    const revisionId = String(
      poolMeta.plan_revision_id
      || poolMeta.revision_id
      || (poolMeta.critical_replanning && poolMeta.critical_replanning.revision_id)
      || (strategic && strategic.revision_id)
      || ''
    );
    appendStrategicPlanCard(poolId, revisionId, strategic, items, rawMarkdown);
    // State-driven prompts (survive a browser reload): re-derive from the server pool.status /
    // metadata instead of in-memory flags, so the approval / clarification controls reappear.
    const clarification = poolMeta.critique_clarification_options || {};
    const clarificationBlocks = clarificationExecutionBlockReasons(poolMeta);
    if (poolMeta.gate_rerun_performed_after_clarification && !clarificationBlocks.length) {
      const summary = [
        poolMeta.revised_plan_summary || 'Plan revised and gates rerun',
        poolMeta.changed_scope_summary ? `Changed scope: ${poolMeta.changed_scope_summary}` : '',
        poolMeta.gate_rerun_summary ? `Gate rerun: ${poolMeta.gate_rerun_summary}` : '',
        Array.isArray(poolMeta.allowed_paths_after_clarification) && poolMeta.allowed_paths_after_clarification.length
          ? `Allowed paths: ${poolMeta.allowed_paths_after_clarification.join(', ')}` : '',
        Array.isArray(poolMeta.item_changed_fields) && poolMeta.item_changed_fields.length
          ? `Changed fields: ${poolMeta.item_changed_fields.map((item) => `${item.item_id || 'item'}=${(item.changed_fields || []).join('/')}`).join(', ')}` : '',
      ].filter(Boolean).join('\n');
      pushSystemMessage(summary);
    }
    const approvalContext = { poolMeta, strategic, revisionId };
    if (poolStatus !== 'approval_required' || poolMeta.clarification_required || clarificationBlocks.length) {
      clearAtlasApprovalActions({ poolId });
    }
    if (poolStatus === 'blocked_safety_review') {
      let runtime = null;
      try {
        runtime = await loadRuntimeStatus(poolId);
      } catch (err) {
        console.warn('Atlas runtime status render failed', err);
      }
      renderRuntimeStatusPanel(runtime || runtimeStatusPayload(poolId, {
        phase: 'blocked_safety_review',
        status: 'blocked',
        message: 'Blocked by safety gate',
        block_reason: poolMeta.safety_gate_block_reason_after_clarification || 'safety_gate_blocked',
        requires_user_action: true,
        next_actions: ['override safety block', 'revise plan', 'cancel'],
        authoritative_source: 'PlanPool',
      }));
      appendSafetyBlockPrompt(poolId, poolMeta);
      return;
    }
    if (poolMeta.clarification_required && Array.isArray(poolMeta.clarification_questions) && poolMeta.clarification_questions.length) {
      appendClarificationPrompt(poolId, poolMeta);
    } else if (poolMeta.clarification_required && Array.isArray(clarification.options) && clarification.options.length) {
      appendClarificationPrompt(poolId, { clarification_questions: [{ question_id: 'clar_q_1', index: 1, total: 1, prompt: '確認が必要です。以下から選択してください:', options: clarification.options, status: 'pending' }] });
    } else if (clarificationBlocks.length) {
      // Clarification was answered but the revised plan did NOT clear the gate (typically the
      // post-answer replan/gate-rerun failed). Without a control here the user is stranded on a
      // button-less plan card. Surface WHY plus an actionable recovery path (revise / cancel).
      appendClarificationRecoveryPrompt(poolId, approvalContext, clarificationBlocks, poolMeta);
    } else if (poolStatus === 'waiting_for_critical_decision') {
      // The critique gate raised a CRITICAL event on the (revised) plan, so the backend parked the
      // pool in waiting_for_critical_decision. This state had NO branch before, so the plan card
      // rendered with zero controls — the reported "Critic shown, then no approve/revise/cancel
      // buttons" dead-end. Surface approve / revise / cancel mapped to the critical-decision endpoint.
      appendCriticalDecisionPrompt(poolId, poolMeta, approvalContext);
    } else if (poolStatus === 'approval_required') {
      appendPlanActionPrompt(poolId, approvalContext);
    } else if (opts.allowReuse) {
      // Reusing an existing plan from Plan History: the pool is past approval_required
      // (ready / completed / failed / running …) so no interactive prompt fires above and
      // the plan would render with no controls. Offer reuse actions so the user can
      // re-run it (re-execute), request a revision, or cancel.
      appendPlanReusePrompt(poolId, approvalContext, poolStatus);
    }
  }

  // Status-driven safety-block panel: shown when pool.status === 'blocked_safety_review'. Renders the
  // block reason and three actions — Approve & continue (grant a human safety override), Revise, and
  // Cancel — mapping to backend routes. No spinner is shown; the state comes purely from the backend.
  function appendSafetyBlockPrompt(poolId, poolMeta) {
    if (!dom.transcript) return;
    const meta = poolMeta && typeof poolMeta === 'object' ? poolMeta : {};
    const reason = String(meta.safety_gate_block_reason_after_clarification || '').trim()
      || String(meta.gate_rerun_summary || '').trim()
      || 'safety gate blocked the revised plan';
    const node = document.createElement('div');
    node.className = 'atlas-claude-msg';
    node.dataset.role = 'system';
    node.dataset.atlasSafetyBlockPrompt = 'true';
    node.dataset.poolId = String(poolId);
    node.style.flexDirection = 'column';
    node.style.gap = '6px';

    const text = document.createElement('div');
    text.textContent = `安全ゲートがブロックされました — 理由: ${reason}`;
    node.appendChild(text);

    const hint = document.createElement('div');
    hint.className = 'atlas-claude-stage-detail';
    hint.style.whiteSpace = 'normal';
    hint.textContent = String(meta.next_required_user_action
      || '安全オーバーライドを許可して続行するか、計画/スコープを修正するか、キャンセルしてください。');
    node.appendChild(hint);

    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.gap = '6px';

    const approve = document.createElement('button');
    approve.type = 'button';
    approve.className = 'atlas-claude-primary-btn';
    approve.textContent = '承認して続行';

    const revise = document.createElement('button');
    revise.type = 'button';
    revise.className = 'atlas-claude-secondary-btn';
    revise.textContent = '改訂を依頼';

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'atlas-claude-secondary-btn';
    cancel.textContent = 'キャンセル';

    approve.addEventListener('click', () => {
      const note = (root.prompt && root.prompt('安全オーバーライドの理由（任意）')) || '';
      Array.from(actions.querySelectorAll('button')).forEach((b) => { b.disabled = true; });
      grantSafetyOverrideAndContinue(poolId, note);
    });
    revise.addEventListener('click', () => {
      const note = (root.prompt && root.prompt('改訂依頼の内容（任意）')) || '';
      node.remove();
      requestPlanRevision(poolId, note);
    });
    cancel.addEventListener('click', () => {
      node.remove();
      cancelPlan(poolId);
    });
    actions.append(approve, revise, cancel);
    node.appendChild(actions);
    upsertTranscriptNode(
      (el) => el.dataset && el.dataset.atlasSafetyBlockPrompt === 'true' && el.dataset.poolId === String(poolId),
      node,
    );
  }

  async function grantSafetyOverrideAndContinue(poolId, reason) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.grantSafetyOverride) {
      pushSystemMessage('Safety override is not available in this client.');
      return;
    }
    try {
      const resp = await root.AtlasPipelineAPI.grantSafetyOverride(poolId, {
        reason: reason || '', workspace_id: workspaceId(),
      });
      if (resp && resp.ok) {
        pushSystemMessage('Safety override を記録しました。パイプラインを再開します...');
        await approveAndRunPipeline(poolId);
      } else {
        pushSystemMessage(`Safety override に失敗しました: ${formatError(resp)}`);
      }
    } catch (e) {
      pushSystemMessage('Safety override に失敗しました: ' + (e && e.message ? e.message : e));
    }
  }

  // Render a Claude/Codex-style strategic plan the user can review before approving: goal, approach,
  // per-step detail, risks/review, done-definition. Falls back to the thin item list when no
  // strategic_plan is present (older pools). textContent-based; never injects HTML.
  function preparePlanCardForUpsert(card, poolId, revisionId) {
    card.dataset.atlasPlanCard = 'true';
    card.dataset.poolId = String(poolId || '');
    card.dataset.planRevisionId = String(revisionId || '');
    return card;
  }

  function upsertPlanCard(card, poolId, revisionId) {
    preparePlanCardForUpsert(card, poolId, revisionId);
    upsertTranscriptNode(
      (el) => el.dataset
        && el.dataset.atlasPlanCard === 'true'
        && el.dataset.poolId === String(poolId || '')
        && el.dataset.planRevisionId === String(revisionId || ''),
      card,
    );
  }

  function appendStrategicPlanCard(poolId, revisionId, strategic, items, rawMarkdown) {
    if (!strategic || typeof strategic !== 'object') {
      appendPlanCard(poolId, revisionId, items, rawMarkdown);
      return;
    }
    const card = document.createElement('div');
    card.className = 'atlas-claude-msg atlas-claude-stage-block';
    card.dataset.role = 'atlas';

    const head = document.createElement('div');
    head.className = 'atlas-claude-summary-head';
    const stepCount = Array.isArray(strategic.steps) ? strategic.steps.length : 0;
    head.textContent = `戦略プラン — 実行ステップ ${stepCount} 件`;
    card.appendChild(head);

    const addSection = (label, render) => {
      const sec = document.createElement('div');
      sec.style.margin = '8px 0 2px';
      const h = document.createElement('div');
      h.className = 'atlas-claude-summary-head';
      h.style.fontSize = '12px';
      h.textContent = label;
      sec.appendChild(h);
      render(sec);
      card.appendChild(sec);
    };
    const para = (parent, text) => {
      if (!text) return;
      const d = document.createElement('div');
      d.className = 'atlas-claude-stage-detail';
      d.style.whiteSpace = 'normal';
      d.textContent = text;
      parent.appendChild(d);
    };
    const bullets = (parent, arr) => {
      if (!Array.isArray(arr) || !arr.length) return;
      arr.forEach((x) => {
        const d = document.createElement('div');
        d.className = 'atlas-claude-stage-detail';
        d.style.whiteSpace = 'normal';
        d.textContent = `• ${x}`;
        parent.appendChild(d);
      });
    };
    const textItems = (value) => {
      if (Array.isArray(value)) return value.map((x) => String(x || '').trim()).filter(Boolean);
      const s = String(value || '').trim();
      return s ? [s] : [];
    };

    // Goal / summary
    if (strategic.goal || strategic.requirement_summary) {
      addSection('ゴール', (sec) => {
        para(sec, strategic.goal);
        if (strategic.requirement_summary && strategic.requirement_summary !== strategic.goal) para(sec, strategic.requirement_summary);
      });
    }
    // Approach / architecture
    if (strategic.selected_architecture || (strategic.architecture_options || []).length || (strategic.research && strategic.research.recommended_approach)) {
      addSection('アプローチ / アーキテクチャ', (sec) => {
        if (strategic.research && strategic.research.recommended_approach) para(sec, strategic.research.recommended_approach);
        para(sec, strategic.selected_architecture);
        bullets(sec, strategic.architecture_options);
      });
    }
    // Steps
    if (stepCount) {
      addSection('実行ステップ', (sec) => {
        strategic.steps.forEach((s, i) => {
          const row = document.createElement('div');
          row.style.padding = '4px 0';
          const t = document.createElement('div');
          const meta = [s.action_type, s.risk_level].filter(Boolean).join(' · ');
          t.innerHTML = `<strong>${escapeText(`${i + 1}. ${s.title || 'step'}`)}</strong>${meta ? ` <span class="atlas-claude-stage-detail">(${escapeText(meta)})</span>` : ''}`;
          row.appendChild(t);
          if (s.goal) para(row, `ゴール: ${s.goal}`);
          para(row, s.description);
          bullets(row, textItems(s.acceptance_criteria).map((x) => `受入条件: ${x}`));
          if ((s.target_files || []).length) para(row, `files: ${s.target_files.join(', ')}`);
          if (s.verification) para(row, `検証: ${s.verification}`);
          if (s.rollback) para(row, `ロールバック: ${s.rollback}`);
          sec.appendChild(row);
        });
      });
    }
    // Risks & review
    const review = strategic.review || {};
    const critique = strategic.adversarial_critique || {};
    if ((strategic.risks || []).length || review.summary || (review.findings || []).length || (critique.findings || []).length) {
      addSection('リスク / レビュー', (sec) => {
        if (review.overall_risk) para(sec, `総合リスク: ${review.overall_risk}`);
        if (review.summary) para(sec, review.summary);
        bullets(sec, strategic.risks);
        const unresolvedReview = (review.findings || []).filter((f) => ['high', 'critical'].includes(String(f.severity || '').toLowerCase()) || f.requires_user_confirmation);
        const resolvedReview = (review.findings || []).filter((f) => !unresolvedReview.includes(f));
        unresolvedReview.forEach((f) => para(sec, `未解決 ⚠ [${f.severity || '-'}] ${f.title || ''}${f.recommendation ? ' → ' + f.recommendation : ''}`));
        if (resolvedReview.length) para(sec, `解決済み/低リスク findings: ${resolvedReview.length} 件（折りたたみ対象）`);
        if (critique.requires_revision) para(sec, `敵対的批評: 要改訂 (${critique.consensus_risk || '-'})`);
        const unresolvedCritique = (critique.findings || []).filter((f) => ['high', 'critical'].includes(String(f.severity || '').toLowerCase()));
        unresolvedCritique.forEach((f) => para(sec, `未解決 ⚔ [${f.severity || '-'}/${f.angle || '-'}] ${f.title || ''}${f.recommendation ? ' → ' + f.recommendation : ''}`));
      });
    }
    // Done definition / tests
    if ((strategic.done_definition || []).length || (strategic.test_plan || []).length) {
      addSection('完了条件 / テスト', (sec) => {
        bullets(sec, strategic.done_definition);
        bullets(sec, strategic.test_plan);
      });
    }

    // Raw details preserved for power users.
    if (rawMarkdown) {
      const det = document.createElement('details');
      det.className = 'atlas-claude-summary-items';
      const sm = document.createElement('summary');
      sm.textContent = '詳細（生のプラン情報）';
      det.appendChild(sm);
      const body = document.createElement('div');
      const trimmed = rawMarkdown.length > 8000 ? rawMarkdown.slice(0, 8000) + '\n\n…(truncated)' : rawMarkdown;
      const pre = document.createElement('pre');
      pre.textContent = trimmed;
      body.appendChild(pre);
      det.appendChild(body);
      card.appendChild(det);
    }

    upsertPlanCard(card, poolId, revisionId);
  }

  function appendPlanCard(poolId, revisionId, items, rawMarkdown) {
    const card = document.createElement('div');
    card.className = 'atlas-claude-msg atlas-claude-stage-block';
    card.dataset.role = 'atlas';

    const head = document.createElement('div');
    head.className = 'atlas-claude-summary-head';
    head.textContent = `プラン — 実行ステップ ${items.length} 件`;
    card.appendChild(head);

    if (items.length) {
      const list = document.createElement('div');
      list.className = 'atlas-claude-stage-list';
      items.forEach((it, i) => {
        const id = it.item_id || it.id || `item_${i + 1}`;
        const title = it.title || it.summary || it.goal || `step ${i + 1}`;
        const type = it.item_type || '-';
        const status = it.status || '-';
        const files = Array.isArray(it.target_files) ? it.target_files : [];
        const row = document.createElement('div');
        row.style.padding = '3px 0';
        const line1 = document.createElement('div');
        line1.innerHTML = `<strong>${escapeText(id)}</strong> · ${escapeText(title)}`;
        const line2 = document.createElement('div');
        line2.className = 'atlas-claude-stage-detail';
        line2.style.whiteSpace = 'normal';
        const filesText = files.length ? ` · files: ${files.map(escapeText).join(', ')}` : ' · files: —';
        line2.innerHTML = `type: ${escapeText(type)} · status: ${escapeText(status)}${filesText}`;
        row.append(line1, line2);
        list.appendChild(row);
      });
      card.appendChild(list);
    }

    if (rawMarkdown) {
      const det = document.createElement('details');
      det.className = 'atlas-claude-summary-items';
      const sm = document.createElement('summary');
      sm.textContent = '詳細（生のプラン情報）';
      det.appendChild(sm);
      const body = document.createElement('div');
      const trimmed = rawMarkdown.length > 8000 ? rawMarkdown.slice(0, 8000) + '\n\n…(truncated)' : rawMarkdown;
      if (root.marked && typeof root.marked.parse === 'function') {
        body.innerHTML = root.marked.parse(trimmed);
      } else {
        const pre = document.createElement('pre');
        pre.textContent = trimmed;
        body.appendChild(pre);
      }
      det.appendChild(body);
      card.appendChild(det);
    }

    upsertPlanCard(card, poolId, revisionId);
  }

  function escapeText(value) {
    const div = document.createElement('div');
    div.textContent = String(value == null ? '' : value);
    return div.innerHTML;
  }

  function setBusy(busy) {
    if (dom.stopBtn) dom.stopBtn.style.display = busy ? '' : 'none';
    if (dom.sendBtn) dom.sendBtn.disabled = !!busy;
    if (dom.input) dom.input.disabled = !!busy;
    if (!busy) clearLlmProgressLine();
  }

  // E: surface ASR transcription progress on the Atlas input placeholder (the
  // transcribing SSE events would otherwise only land in the hidden Lumen message
  // list). The old header title was removed, so the input is the visible anchor.
  function setTranscribingStatus(on) {
    const inputEl = dom.input;
    if (!inputEl) return;
    if (on) {
      if (!inputEl.dataset.origPlaceholder) inputEl.dataset.origPlaceholder = inputEl.placeholder || '';
      inputEl.placeholder = '変換中…';
      inputEl.classList.add('atlas-claude-title-transcribing');
    } else {
      inputEl.placeholder = inputEl.dataset.origPlaceholder || '指示を入力...';
      delete inputEl.dataset.origPlaceholder;
      inputEl.classList.remove('atlas-claude-title-transcribing');
    }
  }

  // Guard against ever surfacing a raw HTML error page (e.g. a Cloudflare/runpod 5xx body) in chat.
  function sanitizeErrorText(text) {
    let s = String(text == null ? '' : text);
    const head = s.slice(0, 200).toLowerCase();
    if (head.includes('<html') || head.includes('<!doctype') || head.includes('cf-error') || head.includes('cloudflare')) {
      return 'サーバが時間内に応答しませんでした（タイムアウト）。少し待って再実行してください。';
    }
    if (s.length > 500) s = s.slice(0, 500) + '…';
    return s;
  }

  function formatError(resp) {
    if (!resp) return 'no response';
    // Prefer the canned message produced by parseResponse for gateway/timeout/non-JSON errors.
    if (resp.code === 'gateway_timeout' || resp.code === 'plan_pool_timeout' || resp.code === 'plan_pool_stalled' || resp.code === 'plan_pool_absolute_timeout' || resp.code === 'plan_pool_failed' || resp.code === 'network_error') {
      return sanitizeErrorText(resp.message || 'request failed');
    }
    const detail = resp && resp.detail && resp.detail.detail !== undefined ? resp.detail.detail : resp.message;
    if (detail == null) return sanitizeErrorText(resp.message || 'unknown error');
    if (typeof detail === 'string') return sanitizeErrorText(detail);
    if (Array.isArray(detail)) {
      // FastAPI pydantic validation errors arrive as an array of {loc, msg, type}.
      return detail.map((d) => {
        if (d && typeof d === 'object') {
          const loc = Array.isArray(d.loc) ? d.loc.join('.') : (d.loc || '');
          const msg = d.msg || d.message || JSON.stringify(d);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(d);
      }).join('; ');
    }
    if (typeof detail === 'object') {
      if (detail.error || detail.reason || detail.message) {
        return [detail.error, detail.reason, detail.message].filter(Boolean).join(': ');
      }
      try { return JSON.stringify(detail); } catch (_e) { return String(detail); }
    }
    return String(detail);
  }

  async function startAutonomousLoop(text) {
    const preset = state.presets.find((p) => p.id === state.selectedPresetId);
    if (!preset || !preset.enables_full_automation) {
      pushAtlasMessage('Current Automation Profile does not enable autonomous execution. Pick Profile 4 first.');
      return;
    }
    const envelope = state.latestEnvelope;
    if (!envelope || envelope.status !== 'active') {
      pushAtlasMessage('No active envelope manifest. Open the Features drawer and Select the profile first.');
      return;
    }
    const requestKind = preset.envelope_id === 'pre_authorized_self_improvement_envelope'
      ? 'autonomous_self_improvement_loop'
      : 'autonomous_dev_loop';
    const bounds = envelope.bounds || {};
    const payload = {
      request_kind: requestKind,
      loop_goal: text,
      requested_actions: bounds.max_actions_per_loop || 1,
      requested_files: bounds.max_files_changed || 1,
      requested_runtime_seconds: bounds.max_runtime_seconds || 60,
      requested_risk_level: bounds.max_risk_level || 'low',
      requested_paths: bounds.allowed_paths || [],
      requested_commands: bounds.command_allowlist || [],
    };
    const resp = await root.AtlasPipelineAPI.startAutonomousLoopFromEnvelope(payload);
    if (resp.ok && resp.data && resp.data.status === 'active') {
      pushAtlasMessage(`Autonomous loop session prepared (\`${resp.data.session_id}\`). Backend autopilot will progress within the envelope bounds.`);
    } else {
      const reasons = resp.data && resp.data.blocking_reasons ? resp.data.blocking_reasons.join(', ') : formatError(resp);
      pushAtlasMessage(`Autonomous loop blocked: ${reasons}`);
    }
  }

  function onStop() {
    setBusy(false);
    const legacy = document.getElementById('atlas-workflow-stop-btn');
    if (legacy) legacy.click();
    pushSystemMessage('停止しました');
  }

  function delegateRecover() {
    if (root.AtlasDashboard && typeof root.AtlasDashboard.loadRecoveredPlan === 'function') {
      root.AtlasDashboard.loadRecoveredPlan();
      if (typeof root.AtlasDashboard.refreshStatus === 'function') {
        root.AtlasDashboard.refreshStatus();
      }
      pushAtlasMessage('前回の状態を読み込みました');
    } else {
      pushAtlasMessage('Recovery unavailable.');
    }
  }

  function pushUserMessage(text) { appendMessage('user', text); }
  function pushAtlasMessage(text) { appendMessage('atlas', text); }
  function pushSystemMessage(text) { appendMessage('system', text); }

  // Render-time status lines that must not be treated as real conversation when replaying a
  // persisted transcript. An earlier bug persisted these on every reload; filter them on restore so
  // legacy logs stop showing duplicates (the plan/progress itself is re-rendered from server state).
  function isTransientStatusMessage(m) {
    const role = m && m.role;
    const text = String((m && m.text) || '').trim();
    return role === 'atlas' && /^Plan was created/.test(text);
  }

  function appendMessage(role, text, persist = true, meta = null) {
    if (!dom.transcript) return;
    state.transcript.push({ role, text, ts: Date.now() });
    while (state.transcript.length > TRANSCRIPT_MAX_MESSAGES) state.transcript.shift();
    // Never persist while restoring: loadProject() replays/re-renders server state, so persisting
    // here would duplicate render-time status lines into the conversation log on every reload.
    if (persist && !state.restoring) persistMessage(role, text, meta);

    const node = document.createElement('div');
    node.className = 'atlas-claude-msg';
    node.dataset.role = role;
    // Defense-in-depth: never run marked (-> innerHTML) on text that smells like a raw HTML error
    // page. Render it as plain text instead so a leaked Cloudflare/runpod body can't inject markup.
    const head = String(text || '').slice(0, 200).toLowerCase();
    const htmlish = head.includes('<html') || head.includes('<!doctype') || head.includes('cf-error') || head.includes('cf-icon') || head.includes('cloudflare');
    if (root.marked && typeof root.marked.parse === 'function' && role !== 'system' && !htmlish) {
      node.innerHTML = root.marked.parse(text);
    } else {
      node.textContent = text;
    }
    dom.transcript.appendChild(node);
    while (dom.transcript.childElementCount > TRANSCRIPT_MAX_MESSAGES) {
      dom.transcript.removeChild(dom.transcript.firstChild);
    }
    dom.transcript.scrollTop = dom.transcript.scrollHeight;
  }

  root.AtlasClaudePanel = {
    init,
    activate,
    deactivate,
    refresh: refreshWorkflowState,
    sendChatMessage,
    selectProfile,
    startAutonomousLoop,
    setActiveProject,
    loadProject,
    setTranscribingStatus,
    showPlanList: showPlanPoolList,
    state,
  };

  // ── Capability Preferences ─────────────────────────────────────────────────
  // These checkboxes store USER PREFERENCE METADATA only.
  // Backend/runtime policy remains authoritative over actual capability availability.
  // Checked preference ≠ backend authorization.

  const _CAP_STORAGE_KEY = 'atlas_capability_preferences';
  const _CAP_IDS = [
    'cap-command-execution',
    'cap-browser-automation',
    'cap-playwright-verification',
    'cap-web-evidence',
    'cap-sandboxed-install',
  ];
  const _CAP_ID_TO_KEY = {
    'cap-command-execution': 'command_execution_requested',
    'cap-browser-automation': 'browser_automation_requested',
    'cap-playwright-verification': 'playwright_visual_verification_requested',
    'cap-web-evidence': 'web_evidence_gathering_requested',
    'cap-sandboxed-install': 'sandboxed_package_installation_requested',
  };

  function saveAtlasCapabilityPreferences() {
    const prefs = {};
    _CAP_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el) prefs[id] = el.checked;
    });
    try {
      localStorage.setItem(_CAP_STORAGE_KEY, JSON.stringify(prefs));
    } catch (e) {
      // localStorage unavailable — preferences are in-memory only
    }
    persistAtlasAutomationFeatures();
  }

  function loadAtlasCapabilityPreferences() {
    let stored = {};
    try {
      const raw = localStorage.getItem(_CAP_STORAGE_KEY);
      if (raw) stored = JSON.parse(raw);
    } catch (e) {
      // ignore parse errors — use defaults (all checked)
    }
    _CAP_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      // If key is absent from storage, keep default (checked)
      if (Object.prototype.hasOwnProperty.call(stored, id)) {
        el.checked = Boolean(stored[id]);
      }
    });
  }

  function getAtlasCapabilityPreferences() {
    const prefs = {};
    _CAP_IDS.forEach(id => {
      const el = document.getElementById(id);
      prefs[id] = el ? el.checked : true;
    });
    return prefs;
  }

  // Expose for external callers (e.g., pipeline API payload builders)
  window.saveAtlasCapabilityPreferences = saveAtlasCapabilityPreferences;
  window.getAtlasCapabilityPreferences = getAtlasCapabilityPreferences;

  // ── Automation features (human-in-the-loop): critical_handling / clarification_mode /
  // quality_gate_enforcement / requirement_coverage_enforcement. Read from <select> controls in the Features panel; sent with the
  // plan-pool create request and persisted server-side via /api/atlas/automation-features. ──
  const _FEATURE_SELECTS = {
    'feat-critical-handling': 'critical_handling',
    'feat-clarification-mode': 'clarification_mode',
    'feat-quality-enforcement': 'quality_gate_enforcement',
    'feat-requirement-coverage-enforcement': 'requirement_coverage_enforcement',
  };

  function getAtlasAutomationFeatures() {
    const features = {};
    Object.entries(_FEATURE_SELECTS).forEach(([id, key]) => {
      const el = document.getElementById(id);
      if (el && el.value) features[key] = el.value;
    });
    return features;
  }

  async function persistAtlasAutomationFeatures() {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.setAutomationFeatures) return;
    try {
      await root.AtlasPipelineAPI.setAutomationFeatures({
        features: getAtlasAutomationFeatures(),
        selected_preset_id: state.selectedPresetId || 'autonomous_bounded_dev',
        capability_preferences: getAtlasCapabilityPreferences(),
      });
    } catch (e) { /* best-effort */ }
  }

  async function loadAtlasAutomationFeatures() {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.getAutomationFeatures) return;
    try {
      const r = await root.AtlasPipelineAPI.getAutomationFeatures();
      const data = (r && r.ok && r.data) || {};
      const f = data.features || {};
      if (data.selected_preset_id) {
        state.selectedPresetId = data.selected_preset_id;
        const radio = Array.from(document.querySelectorAll('input[name="atlas-claude-preset"]')).find((el) => el.value === state.selectedPresetId);
        if (radio) radio.checked = true;
      }
      const caps = data.capability_preferences || {};
      _CAP_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const key = _CAP_ID_TO_KEY[id] || id;
        if (Object.prototype.hasOwnProperty.call(caps, id)) el.checked = Boolean(caps[id]);
        else if (Object.prototype.hasOwnProperty.call(caps, key)) el.checked = Boolean(caps[key]);
      });
      Object.entries(_FEATURE_SELECTS).forEach(([id, key]) => {
        const el = document.getElementById(id);
        if (el && f[key]) el.value = f[key];
        if (el && !el._featBound) { el.addEventListener('change', persistAtlasAutomationFeatures); el._featBound = true; }
      });
      renderPresetSummary();
      updateSelectButtonState();
    } catch (e) { /* defaults shown */ }
  }

  window.getAtlasAutomationFeatures = getAtlasAutomationFeatures;
  window.loadAtlasAutomationFeatures = loadAtlasAutomationFeatures;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
