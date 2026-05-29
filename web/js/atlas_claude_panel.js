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
 * AtlasPipelineAPI method or to a backend route. The shell does not bypass
 * backend gates, but selecting the Autonomous Bounded Dev or Autonomous
 * Self-Improvement preset DOES pre-authorise the autonomous loop via the
 * envelope manifest so chat-driven full automation becomes possible.
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
          restored = true;
        }
      }
    } catch (_err) { /* network errors are non-fatal */ }
    if (!restored) pushSystemMessage('指示を入力してください');
  }

  async function restoreLatestRun(poolId) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.getLatestMultiItemAutopilotResult) return;
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
    } catch (_err) { /* no prior run to restore */ }
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
    dom.previewBtn = $('atlas-claude-preview-profile-btn');
    dom.selectBtn = $('atlas-claude-select-profile-btn');
    dom.confirmInput = $('atlas-claude-confirm-text');
    dom.recoveryBtn = $('atlas-claude-recovery-btn');
    dom.badges = {
      safety: dom.col.querySelector('.atlas-claude-badge.safety'),
      phase: dom.col.querySelector('.atlas-claude-badge.phase'),
      changedFiles: dom.col.querySelector('.atlas-claude-badge.changed-files'),
    };

    bindInputs();
    appendMessage('system', '指示を入力してください', false);
    refreshPolicies();
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
    if (dom.previewBtn) dom.previewBtn.addEventListener('click', () => previewProfile());
    if (dom.selectBtn) dom.selectBtn.addEventListener('click', () => selectProfile());
    if (dom.confirmInput) dom.confirmInput.addEventListener('input', updateSelectButtonState);
    if (dom.recoveryBtn) dom.recoveryBtn.addEventListener('click', () => delegateRecover());

    document.querySelectorAll('input[name="atlas-claude-preset"]').forEach((radio) => {
      radio.addEventListener('change', (ev) => {
        const value = ev.target.value;
        state.selectedPresetId = value;
        renderPresetSummary();
        updateSelectButtonState();
      });
    });
    document.querySelectorAll('input[name="atlas-claude-work-target"]').forEach((radio) => {
      radio.addEventListener('change', (ev) => {
        state.workTarget = ev.target.value;
        renderBadges();
        renderPresetSummary();
        updateSelectButtonState();
        // When the user switches to self-improvement target on an autonomous
        // preset, warn explicitly and require an explicit re-Apply (the auto-
        // applied envelope is dev_envelope; self_improvement_envelope is more
        // restrictive AND requires strict gate + Level-4 checkpoint backend-side).
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
    if (envResp.ok) state.envelopes = envResp.data.envelopes || [];

    // Auto-apply Profile 0 (Review Only) at startup if no profile is yet
    // selected. This ensures Apply / Send work immediately without forcing
    // the user to type confirmation text for the safe default.
    const latest = state.latestSafetyProfile;
    if (!latest || latest.status !== 'active') {
      autoApplyDefaultProfile();
    }
  }

  async function autoApplyDefaultProfile() {
    // Default initial profile: Profile 4 (Autonomous) + Work target Dev/repair.
    // This auto-applies the pre_authorized_bounded_dev_envelope so the user can
    // send instructions and execute end-to-end without manually pressing Apply.
    // Self-improvement target still requires an explicit re-Apply with warning.
    if (!root.AtlasPipelineAPI) return;
    const r = await root.AtlasPipelineAPI.selectAutomationProfile({
      profile: 'autonomous_dev_agent',
      envelope_id: 'pre_authorized_bounded_dev_envelope',
      explicit_profile_selection: true,
      self_improvement_enabled: false,
      self_improvement_scope: 'none',
      strict_gate_approved: false,
      confirmation_text: 'SELECT AUTOMATION PROFILE',
    });
    if (r.ok && r.data && r.data.safety_profile) {
      state.latestSafetyProfile = r.data.safety_profile;
      state.latestEnvelope = r.data.envelope || null;
      renderBadges();
      appendMessage('system', 'Profile 4 Autonomous + Dev/repair を初期適用しました', false);
    }
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
    const envelopeRecipe = state.envelopes.find((e) => e.envelope_id === preset.envelope_id) || null;
    const lines = [
      `# ${preset.label}`,
      `- safety profile: \`${preset.safety_profile}\``,
      `- envelope: \`${preset.envelope_id}\``,
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
    // Profile 0-2 (Review / Single Action / Supervised) do not enable any
    // autonomous execution, so Apply is one-click. Profile 3-5 require the
    // explicit SELECT AUTOMATION PROFILE confirmation text.
    const preset = state.presets.find((p) => p.id === state.selectedPresetId);
    const rank = preset && typeof preset.rank === 'number' ? preset.rank : 0;
    const requiresConfirmation = rank >= 3;
    if (!requiresConfirmation) {
      dom.selectBtn.disabled = false;
      return;
    }
    const text = dom.confirmInput ? String(dom.confirmInput.value || '').trim() : '';
    const matches = text === CONFIRM_TEXT || text === 'SELECT AUTOMATION SAFETY PROFILE';
    dom.selectBtn.disabled = !matches;
  }

  async function previewProfile() {
    if (!root.AtlasPipelineAPI) return;
    const payload = buildSelectionPayload();
    const resp = await root.AtlasPipelineAPI.previewAutomationProfile(payload);
    if (resp.ok) {
      renderPreviewResult(resp.data);
    } else {
      pushAtlasMessage(`Preview failed: ${formatError(resp)}`);
    }
  }

  function renderPreviewResult(data) {
    const safety = data.safety_profile || {};
    const envelope = data.envelope;
    const lines = [
      `## Preview`,
      `- status: \`${safety.status}\``,
      `- profile: \`${safety.automation_safety_profile}\``,
      `- self-improvement: ${safety.self_improvement_enabled ? 'on' : 'off'}`,
      `- enables full automation: ${data.enables_full_automation ? 'YES' : 'no'}`,
    ];
    if (safety.blocking_reasons && safety.blocking_reasons.length) {
      lines.push(`- blocked: ${safety.blocking_reasons.join(', ')}`);
    }
    if (envelope) {
      lines.push(`- envelope: \`${envelope.envelope_id}\` status=\`${envelope.status}\``);
      if (envelope.blocking_reasons && envelope.blocking_reasons.length) {
        lines.push(`- envelope blocked: ${envelope.blocking_reasons.join(', ')}`);
      }
    }
    if (dom.profileResult) {
      dom.profileResult.hidden = false;
      dom.profileResult.textContent = lines.join('\n');
    }
  }

  async function selectProfile() {
    if (!root.AtlasPipelineAPI) return;
    const payload = buildSelectionPayload();
    // Profile 0-2 may apply with the canonical confirmation text auto-filled.
    // Profile 3-5 use the user-typed text (the Apply button is disabled until
    // they type it correctly via updateSelectButtonState).
    payload.confirmation_text = (dom.confirmInput && dom.confirmInput.value.trim()) || CONFIRM_TEXT;
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

  function buildSelectionPayload() {
    const preset = state.presets.find((p) => p.id === state.selectedPresetId) || state.presets[0];
    if (!preset) return {};
    // Profile 4 selects envelope from Work target via work_target_envelope_map.
    // Other presets use their fixed envelope_id.
    let envelopeId = preset.envelope_id;
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
    const lower = text.toLowerCase();
    if (lower === 'stop' || lower === 'cancel') return 'stop';
    if (lower === 'recover' || lower.startsWith('recover ')) return 'recover';
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
    // free_text_goal: create a plan pool with the user's goal, then render
    // the generated plan in chat so the user can see what Atlas produced.
    setBusy(true);
    const resp = await root.AtlasPipelineAPI.createPlanPool({ input: text });
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
    if (state.provisional) await maybeAutoRename(text);
    if (resp.data && resp.data.planner_status === 'fallback_used') {
      pushSystemMessage('注意: LLM 未接続のため fallback プランです。実際のコード生成は LLM 起動が必要です。');
    }
    await renderPlanPoolMarkdown(poolId);
    setBusy(false);

    // If a full-automation preset is selected AND the envelope is active,
    // offer the user a one-click approval that runs patch generation +
    // approval + autopilot end-to-end without any further chat input.
    const preset = state.presets.find((p) => p.id === state.selectedPresetId);
    const envelope = state.latestEnvelope;
    const envelopeActive = envelope && envelope.status === 'active' && envelope.envelope_id !== 'none';
    if (preset && preset.enables_full_automation && envelopeActive) {
      appendApprovalPrompt(poolId);
    } else if (preset && preset.enables_full_automation && !envelopeActive) {
      pushSystemMessage('Features → 「Apply」で Profile を確定するとここに「承認して実行」ボタンが出ます。');
    } else {
      pushSystemMessage('Profile 4 (Bounded Dev) / 5 (Self-Improvement) を Apply すると自動実行が可能になります。');
    }
  }

  function appendApprovalPrompt(poolId) {
    if (!dom.transcript) return;
    const node = document.createElement('div');
    node.className = 'atlas-claude-msg';
    node.dataset.role = 'system';
    node.style.flexDirection = 'column';
    node.style.gap = '6px';
    const text = document.createElement('div');
    text.textContent = 'この Plan を実行しますか？';
    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.gap = '6px';
    const approve = document.createElement('button');
    approve.type = 'button';
    approve.className = 'atlas-claude-primary-btn';
    approve.textContent = '承認して実行';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'atlas-claude-secondary-btn';
    cancel.textContent = 'キャンセル';
    approve.addEventListener('click', () => {
      node.remove();
      approveAndRunPipeline(poolId);
    });
    cancel.addEventListener('click', () => {
      node.remove();
      pushSystemMessage('キャンセルしました');
    });
    actions.appendChild(approve);
    actions.appendChild(cancel);
    node.appendChild(text);
    node.appendChild(actions);
    dom.transcript.appendChild(node);
    dom.transcript.scrollTop = dom.transcript.scrollHeight;
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
        return;
      }
      const items = pool.data.items || pool.data.plan_items || [];
      if (!items.length) {
        updateStage(stages, 'plan', 'failed', 'no items');
        return;
      }
      updateStage(stages, 'plan', 'done', `${items.length} items`);

      // ── Stage 2: Patch generation ──
      updateStage(stages, 'patch', 'running', `0/${items.length}`);
      let generated = 0;
      const genFailures = [];
      for (let i = 0; i < items.length; i += 1) {
        const it = items[i];
        const itemId = it.item_id || it.id;
        if (!itemId) continue;
        const r = await root.AtlasPipelineAPI.generatePatchProposal({
          pool_id: poolId,
          item_id: itemId,
          workspace_id: workspaceId(),
        });
        const okStatus = r && r.ok && r.data
          && r.data.status && /(proposed|completed|approved)/i.test(String(r.data.status));
        if (okStatus) {
          generated += 1;
        } else {
          // Build a richer error: include backend warnings, status, and the
          // formatted HTTP-level error so the user can investigate.
          let msg = formatError(r);
          if (r && r.ok && r.data) {
            const status = r.data.status || 'unknown';
            const warnings = Array.isArray(r.data.warnings) ? r.data.warnings : [];
            const errors = Array.isArray(r.data.errors) ? r.data.errors : [];
            const parts = [`status=${status}`];
            if (warnings.length) parts.push(`warnings=${warnings.join('; ')}`);
            if (errors.length) parts.push(`errors=${errors.join('; ')}`);
            msg = parts.join(' / ');
          }
          genFailures.push({ id: itemId, msg });
        }
        updateStage(stages, 'patch', 'running', `${i + 1}/${items.length}`);
      }
      if (generated === 0) {
        updateStage(stages, 'patch', 'failed', `0/${items.length} (${genFailures.length} failures)`);
        renderPipelineSummary(stages, { status: 'patch_generation_failed', genFailures });
        return;
      }
      updateStage(stages, 'patch', 'done', `${generated}/${items.length}`);

      // ── Stage 3: Approve items ──
      updateStage(stages, 'approve', 'running', `0/${items.length}`);
      for (let i = 0; i < items.length; i += 1) {
        const itemId = items[i].item_id || items[i].id;
        if (!itemId) continue;
        await root.AtlasPipelineAPI.decidePatchProposal({
          pool_id: poolId,
          item_id: itemId,
          decision: 'approve',
        });
        updateStage(stages, 'approve', 'running', `${i + 1}/${items.length}`);
      }
      updateStage(stages, 'approve', 'done', `${items.length}/${items.length}`);

      // ── Stage 4: Autopilot (apply + verify) ──
      const envelope = state.latestEnvelope || {};
      const bounds = envelope.bounds || {};
      updateStage(stages, 'apply', 'running', 'starting');
      updateStage(stages, 'verify', 'pending', '');
      const autopilotPromise = root.AtlasPipelineAPI.runMultiItemAutopilot({
        pool_id: poolId,
        policy_id: 'guarded_multi_item_v1',
        max_items: Math.min(bounds.max_actions_per_loop || 12, items.length),
        max_runtime_seconds: bounds.max_runtime_seconds || 1800,
        max_changed_files_total: bounds.max_files_changed || 25,
        dry_run: false,
        require_approval: false,
        include_context_refresh: true,
        include_evaluator: true,
        include_bounded_retry: true,
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
            const total = items.length;
            updateStage(stages, 'apply', processed >= total ? 'done' : 'running', `${processed}/${total}`);
            if (completed + failed > 0) {
              updateStage(stages, 'verify', processed >= total ? 'done' : 'running', `pass ${completed} / fail ${failed}`);
            }
          }
        } catch (_e) {}
      }, 1500);
      const result = await autopilotPromise;
      clearInterval(pollTimer);

      if (!result.ok) {
        updateStage(stages, 'apply', 'failed', formatError(result));
        renderPipelineSummary(stages, { status: 'autopilot_failed', error: formatError(result) });
        return;
      }
      const d = result.data || {};
      updateStage(stages, 'apply', 'done', `${d.processed_count || 0} processed`);
      const verifyStatus = (d.failed_count || 0) === 0 ? 'done' : 'failed';
      updateStage(stages, 'verify', verifyStatus, `pass ${d.completed_count || 0} / fail ${d.failed_count || 0}`);
      renderPipelineSummary(stages, d);
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
    const block = document.createElement('div');
    block.className = 'atlas-claude-msg atlas-claude-stage-block';
    block.dataset.role = 'atlas';
    block.dataset.pool = poolId;
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

  function renderPipelineSummary(block, d) {
    if (!block) return;
    const summary = block.querySelector('.atlas-claude-summary-block');
    if (!summary) return;
    summary.innerHTML = '';

    const stopped = d.status === 'patch_generation_failed' || d.status === 'autopilot_failed';

    // Counts: when autopilot did not run, the 0/0/0/0 line is misleading.
    // Show an explicit "stopped" line with the upstream failure instead.
    const counts = document.createElement('div');
    counts.className = 'atlas-claude-summary-counts';
    if (d.status === 'patch_generation_failed') {
      const n = (d.genFailures || []).length;
      counts.textContent = `Patch 段階で停止 — ${n} 件の生成失敗。Autopilot は未実行。`;
    } else if (d.status === 'autopilot_failed') {
      counts.textContent = `Autopilot 起動失敗 — ${d.error || 'unknown'}`;
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
        const reason = r.reason ? ` (${r.reason})` : '';
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
      const reason = stop.reason || r.reason || 'unknown';
      const actions = (stop.suggested_manual_actions || []).join(', ');
      li.textContent = `${r.item_id}: ${reason}${actions ? ' — ' + actions : ''}`;
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
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.getPlanPoolMarkdown) return;
    const md = await root.AtlasPipelineAPI.getPlanPoolMarkdown(poolId, workspaceId());
    if (md && md.ok) {
      const text = typeof md.data === 'string'
        ? md.data
        : (md.data && (md.data.markdown || md.data.text)) || '';
      if (text) {
        pushAtlasMessage(text.length > 4000 ? text.slice(0, 4000) + '\n\n…(truncated)' : text);
        return;
      }
    }
    // Fallback: fetch raw plan pool and show item summaries.
    const pool = await root.AtlasPipelineAPI.getPlanPool(poolId);
    if (!pool || !pool.ok || !pool.data) {
      pushAtlasMessage('Plan was created. Use Recover to view it.');
      return;
    }
    const items = (pool.data.items || pool.data.plan_items || []);
    if (!items.length) {
      pushAtlasMessage('Plan was created but contains no items.');
      return;
    }
    const lines = ['## Plan items'];
    items.forEach((it, i) => {
      const title = it.title || it.summary || it.input || `item ${i + 1}`;
      lines.push(`${i + 1}. ${title}`);
    });
    pushAtlasMessage(lines.join('\n'));
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

  function formatError(resp) {
    if (!resp) return 'no response';
    const detail = resp && resp.detail && resp.detail.detail !== undefined ? resp.detail.detail : resp.message;
    if (detail == null) return resp.message || 'unknown error';
    if (typeof detail === 'string') return detail;
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
      pushAtlasMessage('Current Automation Profile does not enable autonomous execution. Pick Profile 4 or 5 first.');
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
    if (root.marked && typeof root.marked.parse === 'function' && role !== 'system') {
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
    previewProfile,
    selectProfile,
    startAutonomousLoop,
    setActiveProject,
    loadProject,
    setTranscribingStatus,
    state,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
