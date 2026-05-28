/* eslint-disable no-undef */
/**
 * Atlas Claude-Code-style buildless conversational panel.
 *
 * Exposes window.AtlasClaudePanel. The shell is additive: it renders inside
 * #atlas-claude-col which lives next to the legacy #atlas-panel-col in
 * ui.html. setMode('atlas') chooses between the two based on
 * localStorage['atlas_shell_preference'] (default 'claude').
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
  const STORAGE_SHELL_KEY = 'atlas_shell_preference';
  const STORAGE_LAST_GOAL_KEY = 'atlas_claude_last_goal';
  const STORAGE_TRANSCRIPT_KEY = 'atlas_claude_transcript_window_index';
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
    selectedPresetId: 'review_only',
    selfImprovementOverride: false,
    workTarget: 'software_development_or_repair',
    latestSafetyProfile: null,
    latestEnvelope: null,
    workflowState: null,
    activePresetActive: false,
  };

  const dom = {};

  function $(id) {
    return document.getElementById(id);
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
    dom.primaryCta = $('atlas-claude-primary-cta');
    dom.featuresBtn = $('atlas-claude-feature-btn');
    dom.featuresDrawer = $('atlas-claude-features-drawer');
    dom.profileResult = $('atlas-claude-profile-result');
    dom.previewBtn = $('atlas-claude-preview-profile-btn');
    dom.selectBtn = $('atlas-claude-select-profile-btn');
    dom.confirmInput = $('atlas-claude-confirm-text');
    dom.shellToggle = $('atlas-claude-shell-toggle');
    dom.recoveryBtn = $('atlas-claude-recovery-btn');
    dom.openLegacyBtn = $('atlas-claude-open-legacy-btn');
    dom.badges = {
      safety: dom.col.querySelector('.atlas-claude-badge.safety'),
      workTarget: dom.col.querySelector('.atlas-claude-badge.work-target'),
      phase: dom.col.querySelector('.atlas-claude-badge.phase'),
      nextAction: dom.col.querySelector('.atlas-claude-badge.next-action'),
      changedFiles: dom.col.querySelector('.atlas-claude-badge.changed-files'),
      verification: dom.col.querySelector('.atlas-claude-badge.verification'),
      recovery: dom.col.querySelector('.atlas-claude-badge.recovery'),
    };

    bindInputs();
    pushSystemMessage('Atlas conversational shell ready. Pick an Automation Profile and describe what you want Atlas to do.');
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
    if (dom.primaryCta) dom.primaryCta.addEventListener('click', () => onPrimaryCta());
    if (dom.stopBtn) dom.stopBtn.addEventListener('click', () => onStop());
    if (dom.featuresBtn && dom.featuresDrawer) {
      dom.featuresBtn.addEventListener('click', () => {
        dom.featuresDrawer.open = !dom.featuresDrawer.open;
      });
    }
    if (dom.previewBtn) dom.previewBtn.addEventListener('click', () => previewProfile());
    if (dom.selectBtn) dom.selectBtn.addEventListener('click', () => selectProfile());
    if (dom.confirmInput) dom.confirmInput.addEventListener('input', updateSelectButtonState);
    if (dom.shellToggle) dom.shellToggle.addEventListener('click', () => openLegacyShell());
    if (dom.openLegacyBtn) dom.openLegacyBtn.addEventListener('click', () => openLegacyShell());
    if (dom.recoveryBtn) dom.recoveryBtn.addEventListener('click', () => delegateRecover());

    document.querySelectorAll('input[name="atlas-claude-preset"]').forEach((radio) => {
      radio.addEventListener('change', (ev) => {
        const value = ev.target.value;
        state.selectedPresetId = value;
        renderPresetSummary();
        updateSelectButtonState();
      });
    });
    const selfImprovement = $('atlas-claude-self-improvement-override');
    if (selfImprovement) {
      selfImprovement.addEventListener('change', (ev) => {
        state.selfImprovementOverride = !!ev.target.checked;
      });
    }
    document.querySelectorAll('input[name="atlas-claude-work-target"]').forEach((radio) => {
      radio.addEventListener('change', (ev) => {
        state.workTarget = ev.target.value;
        renderBadges();
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
    if (dom.badges.workTarget) {
      dom.badges.workTarget.textContent = `Target: ${state.workTarget}`;
    }
    if (dom.badges.phase) {
      const phase = meta.current_phase || wf.phase || 'unknown';
      dom.badges.phase.textContent = `Phase: ${phase}`;
    }
    if (dom.badges.nextAction) {
      const cta = (wf.primary_cta && wf.primary_cta.label) || wf.primary_cta_label || 'Start Atlas';
      dom.badges.nextAction.textContent = `Next: ${cta}`;
    }
    if (dom.badges.changedFiles) {
      const files = (meta.last_changed_files && meta.last_changed_files.length) || 0;
      dom.badges.changedFiles.textContent = `Files: ${files}`;
    }
    if (dom.badges.verification) {
      dom.badges.verification.textContent = `Verify: ${meta.last_verification_status || 'idle'}`;
    }
    if (dom.badges.recovery) {
      dom.badges.recovery.textContent = `Recovery: ${meta.recovery_state || 'idle'}`;
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
      pushAtlasMessage(`Preview failed: ${resp.message || 'unknown error'}`);
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
    payload.confirmation_text = (dom.confirmInput && dom.confirmInput.value) || CONFIRM_TEXT;
    const resp = await root.AtlasPipelineAPI.selectAutomationProfile(payload);
    if (resp.ok) {
      pushAtlasMessage(`Automation profile selected: \`${payload.profile}\` (envelope \`${payload.envelope_id}\`).`);
      if (resp.data && resp.data.envelope) {
        state.latestEnvelope = resp.data.envelope;
      }
      if (resp.data && resp.data.safety_profile) {
        state.latestSafetyProfile = resp.data.safety_profile;
      }
      renderBadges();
    } else {
      const detail = resp.detail && resp.detail.detail ? resp.detail.detail : resp.message;
      pushAtlasMessage(`Select failed: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
    }
  }

  function buildSelectionPayload() {
    const preset = state.presets.find((p) => p.id === state.selectedPresetId) || state.presets[0];
    if (!preset) return {};
    return {
      profile: preset.safety_profile,
      envelope_id: preset.envelope_id,
      explicit_profile_selection: true,
      self_improvement_enabled: preset.self_improvement_enabled || state.selfImprovementOverride,
      self_improvement_scope: preset.self_improvement_scope || 'none',
      strict_gate_approved: !!preset.self_improvement_enabled,
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
    pushSystemMessage(`Intent: ${intent}`);
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
      const resp = await root.AtlasPipelineAPI.startDryRun ? root.AtlasPipelineAPI.startDryRun({}) : null;
      if (resp && resp.then) {
        const r = await resp;
        pushAtlasMessage(r.ok ? 'Dry-run started.' : `Dry-run failed: ${r.message}`);
      } else {
        pushAtlasMessage('Dry-run trigger not available in this build.');
      }
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
    // free_text_goal: create a plan pool with the user's goal.
    const resp = await root.AtlasPipelineAPI.createPlanPool({ goal: text });
    if (resp.ok) {
      const poolId = resp.data && (resp.data.pool_id || resp.data.id);
      pushAtlasMessage(`PlanPool created${poolId ? ` (\`${poolId}\`)` : ''}.`);
    } else {
      pushAtlasMessage(`PlanPool creation failed: ${resp.message || 'unknown error'}`);
    }
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
      const reasons = resp.data && resp.data.blocking_reasons ? resp.data.blocking_reasons.join(', ') : (resp.message || 'unknown error');
      pushAtlasMessage(`Autonomous loop blocked: ${reasons}`);
    }
  }

  function onPrimaryCta() {
    const text = (dom.input && dom.input.value && dom.input.value.trim()) || (() => {
      try { return localStorage.getItem(STORAGE_LAST_GOAL_KEY) || ''; } catch (_e) { return ''; }
    })();
    if (!text) {
      pushAtlasMessage('Describe what Atlas should do in the input box, then press Start.');
      return;
    }
    if (dom.input) {
      dom.input.value = text;
      sendChatMessage();
    }
  }

  function onStop() {
    const legacy = document.getElementById('atlas-workflow-stop-btn');
    if (legacy) {
      legacy.click();
      pushAtlasMessage('Stop signal delegated to backend workflow.');
    } else {
      pushAtlasMessage('Stop control unavailable.');
    }
  }

  function delegateRecover() {
    if (root.AtlasDashboard && typeof root.AtlasDashboard.loadRecoveredPlan === 'function') {
      root.AtlasDashboard.loadRecoveredPlan();
      if (typeof root.AtlasDashboard.refreshStatus === 'function') {
        root.AtlasDashboard.refreshStatus();
      }
      pushAtlasMessage('Recovery requested from backend.');
    } else {
      pushAtlasMessage('Recovery handler unavailable.');
    }
  }

  function openLegacyShell() {
    try { localStorage.setItem(STORAGE_SHELL_KEY, 'legacy'); } catch (_err) {}
    const claudeCol = $('atlas-claude-col');
    const legacyCol = $('atlas-panel-col');
    if (claudeCol) claudeCol.style.display = 'none';
    if (legacyCol) legacyCol.style.display = '';
    deactivate();
  }

  function pushUserMessage(text) { appendMessage('user', text); }
  function pushAtlasMessage(text) { appendMessage('atlas', text); }
  function pushSystemMessage(text) { appendMessage('system', text); }

  function appendMessage(role, text) {
    if (!dom.transcript) return;
    state.transcript.push({ role, text, ts: Date.now() });
    while (state.transcript.length > TRANSCRIPT_MAX_MESSAGES) state.transcript.shift();

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
    openLegacyShell,
    state,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
