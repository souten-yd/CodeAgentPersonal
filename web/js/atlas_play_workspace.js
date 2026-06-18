(function () {
  'use strict';
  const root = (typeof window !== 'undefined' ? window : globalThis);
  const state = {
    open: false,
    projectId: '',
    selectedPath: '',
    selectedSha: '',
    target: null,
    launchProfile: null,
    session: null,
    pollTimer: null,
    previewStopped: false,
  };
  const dom = {};

  function $(id) { return document.getElementById(id); }
  function api() { return root.AtlasPipelineAPI || null; }
  function activeProject() {
    return root.KASANE_ATLAS_PROJECT_PATH?.getActive?.() || {};
  }
  function projectId() {
    const project = activeProject();
    return project.workspaceId || project.workspace_id || project.name || 'default';
  }
  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  }
  function setStatus(text) {
    if (dom.status) dom.status.textContent = text || '';
  }
  function isActiveSession(session) {
    return ['starting', 'running'].includes(String(session?.state || ''));
  }
  function replacePreviewFrame(src) {
    if (!dom.frame) return;
    try { dom.frame.contentWindow?.stop?.(); } catch (_e) {}
    const next = dom.frame.cloneNode(false);
    next.dataset.atlasPreviewUrl = src || '';
    if (src) next.src = src;
    dom.frame.replaceWith(next);
    dom.frame = next;
  }
  function clearPreviewFrame(statusText) {
    state.previewStopped = true;
    replacePreviewFrame('about:blank');
    if (statusText) setStatus(statusText);
  }
  function isCapsuleBuildEligible(session) {
    return !!session?.session_id
      && session.state === 'stopped'
      && (session.exit_code === 0 || session.exit_code == null || session.stop_reason === 'user_stop');
  }
  function sessionProjectId(session) {
    return session?.project_id || state.projectId || projectId();
  }
  function profileFromSession(session) {
    if (!session?.session_id || !session.launch_profile_id || !session.launch_kind) return null;
    const adapter = session.adapter || {};
    const argv = Array.isArray(adapter.argv) ? adapter.argv : [];
    return {
      profile_id: session.launch_profile_id,
      name: session.launch_profile_id,
      kind: session.launch_kind,
      entrypoint: adapter.entrypoint || argv[1] || state.selectedPath || (session.launch_kind === 'static_web' ? 'index.html' : undefined),
      working_directory: session.working_directory || '.',
    };
  }
  function safePackageId(value, fallback) {
    const normalize = (text) => String(text || '')
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^A-Za-z0-9_.-]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 96);
    return normalize(value) || normalize(fallback) || 'app';
  }
  function apiErrorReason(resp, fallback) {
    const detail = resp?.detail?.detail || resp?.detail || resp?.data?.detail || resp?.data || null;
    const candidates = [
      resp?.data?.reason,
      resp?.data?.message,
      resp?.data?.error,
      detail?.reason,
      detail?.message,
      detail?.error,
      resp?.reason,
      resp?.error,
      resp?.message,
      resp?.code,
    ];
    for (const value of candidates) {
      if (typeof value === 'string' && value.trim()) return value.trim();
    }
    const validation = Array.isArray(detail) ? detail : (Array.isArray(detail?.detail) ? detail.detail : null);
    if (validation && validation.length) {
      return validation.map((item) => {
        const loc = Array.isArray(item.loc) ? item.loc.join('.') : '';
        return [loc, item.msg].filter(Boolean).join(': ');
      }).filter(Boolean).join('; ') || fallback;
    }
    if (detail && typeof detail === 'object') {
      try { return JSON.stringify(detail); } catch (_e) {}
    }
    return fallback || 'error';
  }

  function ensureWorkspace() {
    if ($('atlas-play-workspace')) return;
    const shell = document.createElement('div');
    shell.id = 'atlas-play-workspace';
    shell.className = 'atlas-play-workspace';
    shell.innerHTML = `
      <div class="atlas-play-sheet" role="dialog" aria-modal="true" aria-label="Atlas Play workspace">
        <div class="atlas-play-head">
          <div class="atlas-play-title">Play</div>
          <div class="atlas-play-actions">
            <button type="button" data-action="run" aria-label="Run">▶</button>
            <button type="button" data-action="restart" aria-label="Restart">↻</button>
            <button type="button" data-action="stop" aria-label="Stop">■</button>
            <button type="button" data-action="reload" aria-label="Reload">⟳</button>
            <button type="button" data-action="external" aria-label="Open preview">↗</button>
            <button type="button" data-action="fullscreen" aria-label="Fullscreen">⛶</button>
            <button type="button" data-action="close" aria-label="Close">×</button>
          </div>
        </div>
        <div class="atlas-play-subbar">
          <select id="atlas-play-target-select" aria-label="Play target"></select>
          <span id="atlas-play-status" class="atlas-play-status"></span>
        </div>
        <div class="atlas-play-tabs" role="tablist">
          <button type="button" class="active" data-tab="preview">Preview</button>
          <button type="button" data-tab="files">Files</button>
          <button type="button" data-tab="logs">Logs</button>
          <button type="button" data-tab="console">Console</button>
        </div>
        <div class="atlas-play-body">
          <section class="atlas-play-pane active" data-pane="preview"><iframe id="atlas-play-frame" title="Atlas Play preview"></iframe></section>
          <section class="atlas-play-pane atlas-play-files" data-pane="files">
            <div id="atlas-play-file-list" class="atlas-play-file-list"></div>
            <div class="atlas-play-editor">
              <div class="atlas-play-editor-head"><span id="atlas-play-file-name"></span><button type="button" data-action="save-file">Save</button></div>
              <textarea id="atlas-play-file-editor" spellcheck="false"></textarea>
            </div>
          </section>
          <section class="atlas-play-pane" data-pane="logs"><pre id="atlas-play-logs"></pre></section>
          <section class="atlas-play-pane" data-pane="console"><pre id="atlas-play-console"></pre><button type="button" data-action="repair-handoff">Repair handoff</button></section>
        </div>
      </div>`;
    document.body.appendChild(shell);
    dom.root = shell;
    dom.frame = $('atlas-play-frame');
    dom.target = $('atlas-play-target-select');
    dom.status = $('atlas-play-status');
    dom.files = $('atlas-play-file-list');
    dom.fileName = $('atlas-play-file-name');
    dom.editor = $('atlas-play-file-editor');
    dom.logs = $('atlas-play-logs');
    dom.console = $('atlas-play-console');
    shell.addEventListener('click', handleClick);
    dom.target.addEventListener('change', () => selectTarget(dom.target.value));
  }

  function openWorkspace() {
    ensureWorkspace();
    state.open = true;
    dom.root.classList.add('open');
  }

  function closeWorkspace() {
    state.open = false;
    if (dom.root) dom.root.classList.remove('open');
    stopPolling();
  }

  async function openTargetChooser() {
    openWorkspace();
    state.projectId = projectId();
    setStatus('Resolving target');
    const resp = await api()?.resolvePlayTarget?.({ project_id: state.projectId, source: 'atlas_button' });
    if (!resp || !resp.ok) { setStatus('Target resolution failed'); return; }
    state.target = resp.data || {};
    const candidates = state.target.candidates || [];
    dom.target.innerHTML = candidates.map((item) => `<option value="${escapeHtml(item.entrypoint)}">${escapeHtml(item.entrypoint)} · ${escapeHtml((item.detected_launch_kinds || [])[0] || '')}</option>`).join('');
    if (candidates.length) selectTarget(candidates[0].entrypoint);
    await loadFiles();
    setStatus(candidates.length ? 'Ready' : 'No target');
  }

  function selectTarget(entrypoint) {
    state.selectedPath = entrypoint || '';
    const kind = /\.html?$/i.test(state.selectedPath) ? 'static_web' : 'python_script';
    state.launchProfile = {
      profile_id: `play_${kind}`,
      name: kind === 'static_web' ? 'Static web' : 'Python script',
      kind,
      entrypoint: state.selectedPath,
    };
  }

  async function runSession() {
    if (!state.launchProfile) await openTargetChooser();
    if (!state.launchProfile) return;
    setStatus('Starting');
    const resp = await api()?.startPlaySession?.({ project_id: state.projectId || projectId(), launch_profile: state.launchProfile });
    if (!resp || !resp.ok) { setStatus('Run failed'); return; }
    state.session = resp.data;
    state.projectId = sessionProjectId(state.session);
    state.previewStopped = false;
    renderSession();
    startPolling();
  }

  async function stopSession() {
    if (!state.session?.session_id) return;
    stopPolling();
    clearPreviewFrame('Stopping preview');
    const resp = await api()?.stopPlaySession?.(state.session.session_id);
    if (resp && resp.ok) {
      state.session = resp.data || { ...state.session, state: 'stopped' };
      clearPreviewFrame('Preview stopped');
      renderSession();
      return;
    }
    setStatus(`Stop failed: ${apiErrorReason(resp, 'stop_failed')}`);
  }

  async function restartSession() {
    if (!state.session?.session_id) return runSession();
    const resp = await api()?.restartPlaySession?.(state.session.session_id);
    if (resp && resp.ok) state.session = resp.data;
    renderSession();
  }

  async function refreshSession() {
    if (!state.session?.session_id) return;
    const resp = await api()?.getPlaySession?.(state.session.session_id);
    if (resp && resp.ok) {
      state.session = resp.data;
      renderSession();
      if (!isActiveSession(state.session)) stopPolling();
    }
  }

  function renderSession() {
    const session = state.session || {};
    if (session.state === 'stopped') setStatus('Preview stopped');
    else setStatus(session.state || 'Ready');
    const lines = session.log_tail || [];
    if (dom.logs) dom.logs.textContent = lines.join('\n');
    if (dom.console) dom.console.textContent = lines.join('\n') || 'Read-only session output';
    if (dom.frame && session.session_id && isActiveSession(session)) {
      const base = session.launch_kind === 'static_web' ? 'preview' : 'proxy';
      const url = `/api/atlas/play/${base}/${encodeURIComponent(session.session_id)}/`;
      if (dom.frame.dataset.atlasPreviewUrl !== url) {
        dom.frame.dataset.atlasPreviewUrl = url;
        dom.frame.src = url;
      }
      state.previewStopped = false;
    } else if (session.session_id && !isActiveSession(session) && !state.previewStopped) {
      clearPreviewFrame(session.state === 'stopped' ? 'Preview stopped' : (session.state || 'Preview unavailable'));
    }
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(refreshSession, 2500);
  }
  function stopPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  async function loadFiles() {
    const resp = await api()?.listPlayWorkspaceFiles?.({ project_id: state.projectId || projectId(), directory: '.', limit: 200 });
    if (!resp || !resp.ok) return;
    const files = (resp.data.entries || []).filter((entry) => entry.kind === 'file');
    dom.files.innerHTML = files.map((entry) => `<button type="button" data-file="${escapeHtml(entry.relative_path)}">${escapeHtml(entry.relative_path)}</button>`).join('');
  }

  async function openFile(path) {
    const resp = await api()?.readPlayWorkspaceFile?.({ project_id: state.projectId || projectId(), relative_path: path });
    if (!resp || !resp.ok) { setStatus('File read failed'); return; }
    state.selectedPath = path;
    state.selectedSha = resp.data.sha256 || '';
    dom.fileName.textContent = path;
    dom.editor.value = resp.data.content || '';
  }

  async function saveFile() {
    if (!state.selectedPath || !state.selectedSha) return;
    const resp = await api()?.writePlayWorkspaceFile?.({
      project_id: state.projectId || projectId(),
      relative_path: state.selectedPath,
      content: dom.editor.value,
      expected_sha256: state.selectedSha,
    });
    if (resp && resp.ok) {
      state.selectedSha = resp.data.sha256 || '';
      setStatus('Saved');
    } else {
      setStatus('Save failed');
    }
  }

  function switchTab(tab) {
    dom.root.querySelectorAll('[data-tab]').forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === tab));
    dom.root.querySelectorAll('[data-pane]').forEach((pane) => pane.classList.toggle('active', pane.dataset.pane === tab));
  }

  function handleClick(ev) {
    const action = ev.target.closest('[data-action]')?.dataset.action;
    const file = ev.target.closest('[data-file]')?.dataset.file;
    const tab = ev.target.closest('[data-tab]')?.dataset.tab;
    if (tab) switchTab(tab);
    if (file) openFile(file);
    if (action === 'run') runSession();
    if (action === 'restart') restartSession();
    if (action === 'stop') stopSession();
    if (action === 'reload') refreshSession();
    if (action === 'external' && dom.frame?.src) window.open(dom.frame.src, '_blank', 'noopener');
    if (action === 'fullscreen') dom.root.querySelector('.atlas-play-sheet')?.requestFullscreen?.();
    if (action === 'close') closeWorkspace();
    if (action === 'save-file') saveFile();
    if (action === 'repair-handoff') root.AtlasClaudePanel?.sendText?.('/plan repair current Play session');
  }

  // ---- Capsule builder (PR-PPC-7) ----
  function ensureCapsuleDialog() {
    if ($('atlas-capsule-dialog')) return;
    const el = document.createElement('div');
    el.id = 'atlas-capsule-dialog';
    el.className = 'atlas-capsule-dialog';
    el.innerHTML = `
      <div class="atlas-capsule-card" role="dialog" aria-modal="true" aria-label="Capsule builder">
        <div class="atlas-capsule-head">
          <span class="atlas-capsule-title">Capsule builder</span>
          <button type="button" data-capsule-action="close" aria-label="Close">×</button>
        </div>
        <div class="atlas-capsule-body">
          <p class="atlas-capsule-note" id="atlas-capsule-eligibility"></p>
          <label class="atlas-capsule-field">Package name<input type="text" id="atlas-capsule-name" autocomplete="off" spellcheck="false"></label>
          <label class="atlas-capsule-field">Version<input type="text" id="atlas-capsule-version" value="0.1.0" autocomplete="off" spellcheck="false"></label>
          <div class="atlas-capsule-field">Launch profiles<div id="atlas-capsule-profiles" class="atlas-capsule-profiles"></div></div>
          <label class="atlas-capsule-field atlas-capsule-checkbox"><input type="checkbox" id="atlas-capsule-persist-data"> 永続データをサポート (data policy)</label>
          <div class="atlas-capsule-status" id="atlas-capsule-status" role="status" aria-live="polite"></div>
        </div>
        <div class="atlas-capsule-actions">
          <button type="button" class="atlas-capsule-btn primary" data-capsule-action="build">Build Capsule</button>
          <button type="button" class="atlas-capsule-btn warn" data-capsule-action="force-build" title="成功セッション判定を無視してビルドします">強制Build</button>
          <button type="button" class="atlas-capsule-btn" data-capsule-action="close">Cancel</button>
        </div>
      </div>`;
    document.body.appendChild(el);
    el.addEventListener('click', (ev) => {
      const action = ev.target.closest('[data-capsule-action]')?.dataset.capsuleAction;
      if (action === 'close') closeCapsuleDialog();
      if (action === 'build') buildCapsule(false);
      if (action === 'force-build') {
        if (root.confirm('強制Build: Play の成功判定とファイルハッシュ検証を無視してビルドします。\n動作未確認の成果物が Portal に登録される可能性があります。続行しますか?')) {
          buildCapsule(true);
        }
      }
    });
    if (!document.getElementById('atlas-capsule-style')) {
      const style = document.createElement('style');
      style.id = 'atlas-capsule-style';
      style.textContent = `
        .atlas-capsule-dialog{position:fixed;inset:0;z-index:6000;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center}
        .atlas-capsule-dialog.open{display:flex}
        .atlas-capsule-card{width:min(440px,92vw);max-height:90vh;overflow:auto;background:var(--bg1,#111);border:1px solid var(--border,#333);border-radius:14px;display:flex;flex-direction:column}
        .atlas-capsule-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--border,#333)}
        .atlas-capsule-title{font-weight:700;color:var(--text,#eee)}
        .atlas-capsule-head button{background:none;border:none;color:var(--text2,#aaa);font-size:20px;cursor:pointer}
        .atlas-capsule-body{padding:14px 16px;display:flex;flex-direction:column;gap:10px}
        .atlas-capsule-note{font-size:12px;color:var(--text3,#888);margin:0}
        .atlas-capsule-field{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--text2,#aaa)}
        .atlas-capsule-field input[type=text]{background:var(--bg2,#1a1a1a);border:1px solid var(--border,#333);border-radius:8px;color:var(--text,#eee);padding:7px 10px;font-size:13px}
        .atlas-capsule-checkbox{flex-direction:row;align-items:center;gap:8px}
        .atlas-capsule-profiles{display:flex;flex-direction:column;gap:6px}
        .atlas-capsule-profiles label{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--text,#eee)}
        .atlas-capsule-status{font-size:12px;color:var(--text3,#888);font-family:var(--font-mono,monospace);min-height:14px}
        .atlas-capsule-status.is-error{color:var(--red,#e66)}
        .atlas-capsule-status.is-ok{color:var(--green,#6c6)}
        .atlas-capsule-actions{display:flex;gap:8px;padding:12px 16px;border-top:1px solid var(--border,#333)}
        .atlas-capsule-btn{flex:1;background:var(--bg2,#1a1a1a);border:1px solid var(--border,#333);border-radius:8px;color:var(--text,#eee);padding:8px;cursor:pointer;font-size:13px}
        .atlas-capsule-btn.primary{background:var(--accent,#5af);border-color:var(--accent,#5af);color:#0a0a0a;font-weight:600}
        .atlas-capsule-btn.warn{color:var(--amber,#d90);border-color:var(--amber,#d90)}
        .atlas-capsule-btn:disabled{opacity:.45;cursor:not-allowed}`;
      document.head.appendChild(style);
    }
  }

  function setCapsuleStatus(text, kind) {
    const el = $('atlas-capsule-status');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('is-error', kind === 'error');
    el.classList.toggle('is-ok', kind === 'ok');
  }

  function closeCapsuleDialog() {
    $('atlas-capsule-dialog')?.classList.remove('open');
  }

  function capsuleProfiles() {
    // The profile the current/last Play session used is the build candidate.
    const session = state.session || {};
    const profile = state.launchProfile;
    if (profile && (!session.launch_profile_id || profile.profile_id === session.launch_profile_id)) return [profile];
    const restored = profileFromSession(session);
    if (restored) return [restored];
    return [];
  }

  function showCapsuleHandoff() {
    ensureCapsuleDialog();
    const dialog = $('atlas-capsule-dialog');
    const session = state.session || {};
    const eligible = isCapsuleBuildEligible(session);
    const elig = $('atlas-capsule-eligibility');
    if (elig) {
      // 「成功」= Play セッションが state="stopped" かつ exit_code が 0 (正常終了) または
      // null (サーバ/静的プレビューを明示停止) であること。crash (exit_code≠0) は state="failed" で不成功。
      elig.textContent = eligible
        ? '対象: 成功した Play セッション (stopped / 終了コード 0 または明示停止)。ビルドした Capsule は Portal カタログへ自動登録されます。'
        : 'Capsule には成功した Play セッションが必要です (stopped かつ exit_code 0/null または stop_reason=user_stop)。未終了なら Stop、異常終了 (failed) なら修正後に再 Play してください。検証を省いてビルドする場合は「強制Build」を使用します。';
    }
    const nameInput = $('atlas-capsule-name');
    if (nameInput && !nameInput.value) nameInput.value = String(sessionProjectId(session) || 'app');
    const profiles = capsuleProfiles();
    const host = $('atlas-capsule-profiles');
    if (host) {
      host.innerHTML = profiles.length
        ? profiles.map((p, i) => `<label><input type="checkbox" data-capsule-profile="${escapeHtml(p.profile_id)}"${i === 0 ? ' checked' : ''}> ${escapeHtml(p.name || p.profile_id)} · ${escapeHtml(p.kind)}</label>`).join('')
        : '<span class="atlas-capsule-note">起動プロファイルがありません。Play で対象を選択してください。</span>';
    }
    const hasSession = !!session.session_id;
    const buildBtn = dialog.querySelector('[data-capsule-action="build"]');
    const forceBtn = dialog.querySelector('[data-capsule-action="force-build"]');
    if (buildBtn) buildBtn.disabled = !(eligible && profiles.length);
    // Force build only needs an existing session + a selected profile; it ignores the success gate.
    if (forceBtn) forceBtn.disabled = !(hasSession && profiles.length);
    setCapsuleStatus(eligible ? '' : 'Play 成功セッションが必要です (stopped + user_stop/exit_code 0/null)', eligible ? '' : 'error');
    dialog.classList.add('open');
  }

  async function buildCapsule(force) {
    const session = state.session || {};
    if (!session.session_id) { setCapsuleStatus('Play セッションがありません', 'error'); return; }
    const selectedIds = Array.from(document.querySelectorAll('[data-capsule-profile]'))
      .filter((cb) => cb.checked).map((cb) => cb.getAttribute('data-capsule-profile'));
    if (!selectedIds.length) { setCapsuleStatus('起動プロファイルを1つ以上選択してください', 'error'); return; }
    const profiles = capsuleProfiles().filter((p) => selectedIds.includes(p.profile_id));
    const name = ($('atlas-capsule-name')?.value || '').trim();
    const packageId = safePackageId(sessionProjectId(session), session.session_id || name || 'app');
    const version = ($('atlas-capsule-version')?.value || '0.1.0').trim();
    const persistData = !!$('atlas-capsule-persist-data')?.checked;
    setCapsuleStatus(force ? 'Force building…' : 'Building…');
    const resp = await api()?.buildCapsule?.({
      project_id: sessionProjectId(session),
      play_session_id: session.session_id,
      selected_profile_ids: selectedIds,
      launch_profiles: profiles,
      default_profile_id: selectedIds[0],
      package_id: packageId,
      name: name || undefined,
      version: version || '0.1.0',
      require_current_hashes: !force,
      force: !!force,
      data_policy: { persistent_data_supported: persistData, export_includes_runtime_data: false },
    });
    if (!resp || !resp.ok) {
      setCapsuleStatus(`Build failed: ${apiErrorReason(resp, 'error')}`, 'error');
      return;
    }
    const record = resp.data?.record || {};
    const forced = resp.data?.forced ? ' [強制Build・未検証]' : '';
    setCapsuleStatus(`Built ${record.package_id} v${record.version}${forced} → Portal カタログへ登録済み (${(record.content_hash || '').slice(0, 12)}…)`, 'ok');
    try { root.Portal?.refreshCatalog?.(); } catch (_e) {}
  }

  root.AtlasPlayWorkspace = { openTargetChooser, closeWorkspace, showCapsuleHandoff };
})();
