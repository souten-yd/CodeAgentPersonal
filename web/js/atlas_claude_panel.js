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
    dom.featuresBtn = $('atlas-claude-feature-btn');
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
    pushSystemMessage('指示を入力してください');
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
    if (dom.featuresBtn && dom.featuresDrawer) {
      dom.featuresBtn.addEventListener('click', () => {
        dom.featuresDrawer.open = !dom.featuresDrawer.open;
      });
    }
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
      pushAtlasMessage(`Select failed: ${formatError(resp)}`);
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
    pushAtlasMessage(`PlanPool 作成: \`${poolId}\``);
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
    try {
      // 1. Re-fetch the pool to get up-to-date items.
      const pool = await root.AtlasPipelineAPI.getPlanPool(poolId);
      if (!pool.ok || !pool.data) {
        pushAtlasMessage(`Plan 取得失敗: ${formatError(pool)}`);
        return;
      }
      const items = pool.data.items || pool.data.plan_items || [];
      if (!items.length) {
        pushAtlasMessage('Plan にアイテムがありません。');
        return;
      }

      // 2. Generate patch proposals for every item via the LLM.
      pushSystemMessage(`Patch 生成中 (${items.length} items)...`);
      let generated = 0;
      const genFailures = [];
      for (const it of items) {
        const itemId = it.item_id || it.id;
        if (!itemId) continue;
        const r = await root.AtlasPipelineAPI.generatePatchProposal({
          pool_id: poolId,
          item_id: itemId,
          workspace_id: 'default',
        });
        const okStatus = r && r.ok && r.data
          && r.data.status && /(proposed|completed|approved)/i.test(String(r.data.status));
        if (okStatus) {
          generated += 1;
        } else {
          genFailures.push({ id: itemId, msg: formatError(r) });
        }
      }
      pushSystemMessage(`Patch 生成: ${generated}/${items.length} success`);
      if (genFailures.length) {
        pushAtlasMessage(`一部失敗:\n${genFailures.map((f) => `- \`${f.id}\`: ${f.msg}`).join('\n')}`);
      }

      // 3. Approve each generated patch proposal so the autopilot will pick it up.
      pushSystemMessage('アイテムを承認中...');
      for (const it of items) {
        const itemId = it.item_id || it.id;
        if (!itemId) continue;
        await root.AtlasPipelineAPI.decidePatchProposal({
          pool_id: poolId,
          item_id: itemId,
          decision: 'approve',
        });
      }

      // 4. Run the autopilot end-to-end. Envelope authorises require_approval=false.
      const envelope = state.latestEnvelope || {};
      const bounds = envelope.bounds || {};
      pushSystemMessage('Autopilot 実行中...');
      const result = await root.AtlasPipelineAPI.runMultiItemAutopilot({
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

      if (!result.ok) {
        pushAtlasMessage(`Autopilot 失敗: ${formatError(result)}`);
        return;
      }
      renderAutopilotResult(result.data || {});
    } finally {
      setBusy(false);
    }
  }

  function renderAutopilotResult(d) {
    const lines = [
      '# 実行完了',
      `- status: \`${d.status || 'unknown'}\``,
      `- 完了: ${d.completed_count || 0}`,
      `- 失敗: ${d.failed_count || 0}`,
      `- ブロック: ${d.blocked_count || 0}`,
      `- スキップ: ${d.skipped_count || 0}`,
    ];
    if (d.stop_reason) lines.push(`- stop_reason: \`${d.stop_reason}\``);
    const itemResults = d.item_results || [];
    if (itemResults.length) {
      lines.push('', '## アイテム別結果');
      itemResults.forEach((r) => {
        const status = r.status || '?';
        const reason = r.reason ? ` (${r.reason})` : '';
        lines.push(`- \`${r.item_id}\`: ${status}${reason}`);
      });
    }
    pushAtlasMessage(lines.join('\n'));
  }

  async function renderPlanPoolMarkdown(poolId) {
    if (!root.AtlasPipelineAPI || !root.AtlasPipelineAPI.getPlanPoolMarkdown) return;
    const md = await root.AtlasPipelineAPI.getPlanPoolMarkdown(poolId, 'default');
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
    state,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
