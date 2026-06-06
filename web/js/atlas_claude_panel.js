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
  const TRANSCRIPT_MAX_MESSAGES = 200;
  const POLL_INTERVAL_MS = 8000;
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
    try {
      const resp = await fetch('/api/atlas/projects/' + encodeURIComponent(target) + '/conversation', { headers: { 'Content-Type': 'application/json' } });
      if (resp.ok) {
        const data = await resp.json();
        state.provisional = !!(data.meta && data.meta.provisional);
        (data.messages || []).forEach((m) => {
          if (m && m.text) { appendMessage(m.role, m.text, false); restored = true; }
        });
        const poolId = data.meta && data.meta.active_pool_id;
        if (poolId) {
          await renderPlanPoolMarkdown(poolId);
          await restoreLatestRun(poolId);
          // appendStageBlock auto-scrolled to the stage block; scroll back so the plan card
          // is visible — user can scroll down to reach failure recovery and execution details.
          if (dom.transcript) dom.transcript.scrollTop = 0;
          restored = true;
        }
      }
    } catch (err) {
      console.warn('Atlas project restore failed', err);
    }
    if (!restored) pushSystemMessage('指示を入力してください');
  }

  async function restoreLatestRun(poolId) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.getLatestMultiItemAutopilotResult) return;
    try {
      const runtime = await loadRuntimeStatus(poolId);
      if (runtime) renderRuntimeStatusPanel(runtime);
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
      if (peek && peek.ok && peek.data) {
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
    if (projectName()) loadProject(projectName());
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
    appendMessage('atlas', `PlanPool 作成: \`${poolId}\``, true, { active_pool_id: poolId });
    renderWorkbenchFlow(poolId, text, { status: 'plan_review', controls: {} });
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
    const cards = Array.from(dom.transcript.querySelectorAll('[data-atlas-plan-card="true"]'));
    const activeCard = cards.reverse().find((el) => {
      if (String(el.dataset.poolId || '') !== String(poolId || '')) return false;
      return !revisionId || String(el.dataset.planRevisionId || '') === String(revisionId || '');
    });
    if (activeCard && activeCard.parentNode === dom.transcript) {
      dom.transcript.insertBefore(node, activeCard.nextSibling);
    } else {
      dom.transcript.appendChild(node);
    }
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

  async function requestPlanRevision(poolId, note) {
    if (!root.AtlasPipelineAPI) return;
    try {
      const pool = await root.AtlasPipelineAPI.getPlanPool(poolId);
      const items = (pool && pool.data && (pool.data.items || pool.data.plan_items)) || [];
      const targets = items.filter((it) => String(it.status || '') === 'approval_required');
      const list = targets.length ? targets : items;
      for (const it of list) {
        await root.AtlasPipelineAPI.decideApproval({
          pool_id: poolId, item_id: it.item_id, decision: 'needs_revision',
          reason: note || 'revision requested', workspace_id: workspaceId(),
        });
      }
      pushSystemMessage('改訂を依頼しました（needs_revision）。');
    } catch (e) {
      pushSystemMessage('改訂依頼に失敗しました: ' + (e && e.message ? e.message : e));
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
      const existing = dom.transcript.querySelector('[data-atlas-plan-pool-list="true"]');
      if (existing) existing.replaceWith(card);
      else dom.transcript.appendChild(card);
      dom.transcript.scrollTop = dom.transcript.scrollHeight;
    }
  }

  async function restorePlanPool(poolId, rootGoal) {
    if (!poolId) return;
    pushUserMessage(`プール復元: ${rootGoal || poolId}`);
    setBusy(true);
    await renderPlanPoolMarkdown(poolId);
    setBusy(false);
    // renderPlanPoolMarkdown は poolStatus === 'approval_required' のときのみボタンを出す。
    // 復元時はステータスに関わらず常に承認/改訂/キャンセルを表示する。
    // 過去に dismiss 済みの場合もリセットして強制表示。
    state.dismissedApprovalPlanKeys.delete(poolId);
    appendApprovalPrompt(poolId);
  }

  function renderWorkbenchFlow(poolId, requirement, view) {
    if (!dom.transcript) return;
    const block = document.createElement('div');
    block.className = 'atlas-claude-msg atlas-claude-stage-block';
    block.dataset.role = 'atlas';
    block.dataset.atlasWorkbenchBlock = 'true';
    block.dataset.poolId = String(poolId || '');

    const head = document.createElement('div');
    head.className = 'atlas-claude-summary-head';
    head.textContent = 'Atlas Workbench';
    block.appendChild(head);

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

  async function approveAndRunPipeline(poolId) {
    if (!root.AtlasPipelineAPI) return;
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
      let generated = 0;
      const genFailures = [];
      const appliableIds = [];
      for (let i = 0; i < items.length; i += 1) {
        const it = items[i];
        const itemId = it.item_id || it.id;
        if (!itemId) continue;
        const r = await root.AtlasPipelineAPI.generatePatchProposal({
          pool_id: poolId,
          item_id: itemId,
          workspace_id: workspaceId(),
        });
        const prop = r && r.ok && r.data ? r.data.proposal : null;
        const propMeta = (prop && prop.metadata) || {};
        const resultMeta = (r && r.ok && r.data && r.data.metadata) || {};
        const hasContent = !!(
          (prop && prop.unified_diff_preview)
          || propMeta.proposed_content
          || propMeta.patch_content_available === true
          || resultMeta.patch_content_available === true
        );
        if (hasContent) {
          generated += 1;
          appliableIds.push(itemId);
        } else {
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
          status: 'running',
          items_total: items.length,
          items_started: i + 1,
          items_completed: generated,
          current_item_index: i + 1,
          current_item_title: it.title || itemId,
          message: `Patch generation ${i + 1}/${items.length}`,
          next_actions: ['wait', 'cancel'],
          authoritative_source: '/api/atlas/patch-proposals/generate',
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
      updateStage(stages, 'patch', 'done', `${generated}/${items.length}`);

      // ── Stage 3: Approve items (only those with real patch content) ──
      updateStage(stages, 'approve', 'running', `0/${appliableIds.length}`);
      for (let i = 0; i < appliableIds.length; i += 1) {
        await root.AtlasPipelineAPI.decidePatchProposal({
          pool_id: poolId,
          item_id: appliableIds[i],
          decision: 'approved',
        });
        updateStage(stages, 'approve', 'running', `${i + 1}/${appliableIds.length}`);
      }
      updateStage(stages, 'approve', 'done', `${appliableIds.length}/${appliableIds.length}`);

      // ── Stage 4: Autopilot (apply + verify) — only appliable items ──
      const envelope = state.latestEnvelope || {};
      const bounds = envelope.bounds || {};
      const applyTotal = appliableIds.length;
      updateStage(stages, 'apply', 'running', 'starting');
      updateStage(stages, 'verify', 'pending', '');
      renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
        phase: 'applying',
        status: 'running',
        items_total: applyTotal,
        items_started: 0,
        items_completed: 0,
        message: 'Autopilot run starting',
        next_actions: ['wait', 'cancel'],
        authoritative_source: '/api/atlas/multi-item-autopilot/run',
      }), stages);
      const autopilotPromise = root.AtlasPipelineAPI.runMultiItemAutopilot({
        pool_id: poolId,
        item_ids: appliableIds,
        // Autonomous code-generation run: allow low/medium/high-risk create/update items so a real
        // program (not just trivial low-risk steps) can be built end-to-end.
        policy_id: 'full_auto_multi_item_v1',
        max_items: Math.min(bounds.max_actions_per_loop || 20, applyTotal),
        max_runtime_seconds: bounds.max_runtime_seconds || 1800,
        max_changed_files_total: bounds.max_files_changed || 25,
        dry_run: false,
        require_approval: false,
        include_context_refresh: true,
        include_evaluator: true,
        include_bounded_retry: true,
        include_self_correction: true,
        self_correction_max_attempts: 2,
        metadata: { ui: 'atlas_claude_panel', envelope_id: envelope.envelope_id },
      });
      // Concurrent polling: peek at the persisted autopilot result every 1.5s
      // and surface item-by-item progress while the synchronous run completes.
      const pollTimer = setInterval(async () => {
        try {
          const peek = await root.AtlasPipelineAPI.getLatestMultiItemAutopilotResult({ pool_id: poolId });
          if (peek && peek.ok && peek.data) {
            const processed = peek.data.processed_count || 0;
            const completed = peek.data.completed_count || 0;
            const failed = peek.data.failed_count || 0;
            updateStage(stages, 'apply', processed >= applyTotal ? 'done' : 'running', `${processed}/${applyTotal}`);
            if (completed + failed > 0) {
              updateStage(stages, 'verify', processed >= applyTotal ? 'done' : 'running', `pass ${completed} / fail ${failed}`);
            }
            renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
              phase: completed + failed > 0 ? 'verifying' : 'applying',
              status: peek.data.status || 'running',
              run_id: peek.data.run_id || '',
              autopilot_run_id: peek.data.autopilot_run_id || '',
              items_total: applyTotal,
              items_started: processed,
              items_completed: completed,
              message: `Autopilot ${peek.data.status || 'running'}`,
              error: peek.data.stop_reason || '',
              next_actions: ['wait', 'cancel'],
              authoritative_source: 'multi_item_autopilot_result',
            }), stages);
          }
        } catch (err) {
          console.warn('Atlas autopilot polling failed', err);
          renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
            phase: 'failed',
            status: 'failed',
            items_total: applyTotal,
            message: 'Run status unavailable',
            error: 'endpoint=/api/atlas/multi-item-autopilot/latest',
            requires_user_action: true,
            next_actions: ['retry', 'cancel'],
          }), stages);
        }
      }, 1500);
      const result = await autopilotPromise;
      clearInterval(pollTimer);

      if (!result.ok) {
        updateStage(stages, 'apply', 'failed', formatError(result));
        renderPipelineSummary(stages, { status: 'autopilot_failed', error: formatError(result), genFailures });
        renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
          phase: 'failed',
          status: 'failed',
          items_total: applyTotal,
          message: 'Autopilot failed before applying the first item',
          error: formatError(result),
          requires_user_action: true,
          next_actions: ['retry', 'revise plan', 'cancel'],
          authoritative_source: '/api/atlas/multi-item-autopilot/run',
        }), stages);
        return;
      }
      const d = result.data || {};
      // Surface items that had no patch content so the summary explains why they were not applied.
      if (genFailures.length) d.no_content_failures = genFailures;
      updateStage(stages, 'apply', 'done', `${d.processed_count || 0} processed`);
      const verifyStatus = (d.failed_count || 0) === 0 ? 'done' : 'failed';
      updateStage(stages, 'verify', verifyStatus, `pass ${d.completed_count || 0} / fail ${d.failed_count || 0}`);
      renderPipelineSummary(stages, d);
      renderRuntimeStatusPanel(runtimeStatusPayload(poolId, {
        phase: (d.failed_count || 0) === 0 ? 'completed' : 'failed',
        status: d.status || ((d.failed_count || 0) === 0 ? 'completed' : 'failed'),
        run_id: d.run_id || '',
        autopilot_run_id: d.autopilot_run_id || '',
        items_total: applyTotal,
        items_started: d.processed_count || 0,
        items_completed: d.completed_count || 0,
        message: `Autopilot ${d.status || 'completed'}`,
        error: (d.failed_count || 0) ? (d.stop_reason || 'verification_failed') : '',
        requires_user_action: (d.failed_count || 0) > 0,
        next_actions: (d.failed_count || 0) > 0 ? ['retry', 'revise plan', 'cancel'] : [],
        authoritative_source: 'multi_item_autopilot_result',
        failed_phase: (d.failed_count || 0) > 0 ? 'verify' : undefined,
      }), stages);
      // Persist run pointer so the result block re-renders after a reload.
      persistMeta({ active_pool_id: poolId, latest_autopilot_run_id: d.autopilot_run_id || '' });
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
  const STATE_ICONS = { pending: '·', running: '⟳', done: '✓', failed: '✗' };

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
    const list = document.createElement('div');
    list.className = 'atlas-claude-stage-list';
    STAGE_DEFS.forEach((def) => {
      const row = document.createElement('div');
      row.className = 'atlas-claude-stage-row';
      row.dataset.stage = def.id;
      row.dataset.state = 'pending';
      const icon = document.createElement('span');
      icon.className = 'atlas-claude-stage-icon';
      icon.textContent = STATE_ICONS.pending;
      const label = document.createElement('span');
      label.className = 'atlas-claude-stage-label';
      label.textContent = def.label;
      const detail = document.createElement('span');
      detail.className = 'atlas-claude-stage-detail';
      detail.textContent = '';
      row.append(icon, label, detail);
      list.appendChild(row);
    });
    const summary = document.createElement('div');
    summary.className = 'atlas-claude-summary-block';
    summary.dataset.role = 'summary';
    block.append(list, summary);
    dom.transcript.appendChild(block);
    dom.transcript.scrollTop = dom.transcript.scrollHeight;
    return block;
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
    if (dom.transcript) dom.transcript.scrollTop = dom.transcript.scrollHeight;
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
    const phase = String(view.phase || 'patch_generation');
    const status = String(view.status || 'waiting');
    const total = Number(view.items_total || 0);
    const started = Number(view.items_started || 0);
    const completed = Number(view.items_completed || 0);
    ['plan', 'patch', 'approve', 'apply', 'verify', 'summary'].forEach((stage) => updateStage(panel, stage, 'pending', ''));
    updateStage(panel, 'plan', phase === 'approving' ? 'running' : 'done', phase === 'approving' ? (view.message || 'approving') : '');
    if (phase === 'blocked_safety_review') {
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
      const detail = total ? `${started}/${total}` : (view.message || 'Patch generation has not started');
      updateStage(panel, 'patch', status === 'running' ? 'running' : 'pending', detail);
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
      const rows = [
        `current phase: ${phase}`,
        `status: ${status}`,
        `pool_id: ${view.pool_id || '-'}`,
        `run_id: ${view.autopilot_run_id || view.run_id || '-'}`,
        `items: ${started}/${total}, completed ${completed}`,
        view.current_item_title ? `current item: ${view.current_item_index || 0}. ${view.current_item_title}` : '',
        `message: ${view.message || (phase === 'patch_generation' && started === 0 ? 'Patch generation has not started' : '-')}`,
        view.block_reason ? `block reason: ${view.block_reason}` : '',
        view.error ? `error: ${view.error}` : '',
        `user action required: ${view.requires_user_action ? 'yes' : 'no'}`,
        `next action: ${(view.next_actions || ['wait']).join(', ') || 'wait'}`,
        `source: ${view.authoritative_source || 'PlanPool'}`,
      ].filter(Boolean);
      rows.forEach((text) => {
        const div = document.createElement('div');
        div.className = 'atlas-claude-stage-detail';
        div.textContent = text;
        summary.appendChild(div);
      });
    }
    if (dom.transcript) dom.transcript.scrollTop = dom.transcript.scrollHeight;
    return panel;
  }

  function renderPipelineSummary(block, d) {
    if (!block) return;
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
    renderWorkbenchFlow(poolId || 'autonomous', view.requirement_summary || view.user_requirement || '', view);
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

  async function renderPlanPoolMarkdown(poolId) {
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
      pushAtlasMessage('Plan was created. Use Recover to view it.');
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
      pushSystemMessage(`確認回答と plan revision / gate rerun が完了するまで承認できません: ${clarificationBlocks.join(', ')}`);
    } else if (poolStatus === 'approval_required') {
      appendPlanActionPrompt(poolId, approvalContext);
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
    text.textContent = `Safety gate blocked — reason: ${reason}`;
    node.appendChild(text);

    const hint = document.createElement('div');
    hint.className = 'atlas-claude-stage-detail';
    hint.style.whiteSpace = 'normal';
    hint.textContent = String(meta.next_required_user_action
      || 'Grant a safety override to continue, revise the plan/scope, or cancel.');
    node.appendChild(hint);

    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.gap = '6px';

    const approve = document.createElement('button');
    approve.type = 'button';
    approve.className = 'atlas-claude-primary-btn';
    approve.textContent = 'Approve & continue';

    const revise = document.createElement('button');
    revise.type = 'button';
    revise.className = 'atlas-claude-secondary-btn';
    revise.textContent = 'Revise';

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'atlas-claude-secondary-btn';
    cancel.textContent = 'Cancel';

    approve.addEventListener('click', () => {
      const note = (root.prompt && root.prompt('Reason for the safety override (optional)')) || '';
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
        pushSystemMessage('Safety override を記録しました（blocked_safety_review → ready）。実行を続行できます。');
        await renderPlanPoolMarkdown(poolId);
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

  function appendMessage(role, text, persist = true, meta = null) {
    if (!dom.transcript) return;
    state.transcript.push({ role, text, ts: Date.now() });
    while (state.transcript.length > TRANSCRIPT_MAX_MESSAGES) state.transcript.shift();
    if (persist) persistMessage(role, text, meta);

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
