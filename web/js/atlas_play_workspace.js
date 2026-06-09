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
    renderSession();
    startPolling();
  }

  async function stopSession() {
    if (!state.session?.session_id) return;
    await api()?.stopPlaySession?.(state.session.session_id);
    await refreshSession();
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
    }
  }

  function renderSession() {
    const session = state.session || {};
    setStatus(session.state || 'Ready');
    const lines = session.log_tail || [];
    if (dom.logs) dom.logs.textContent = lines.join('\n');
    if (dom.console) dom.console.textContent = lines.join('\n') || 'Read-only session output';
    if (dom.frame && session.session_id) {
      const base = session.launch_kind === 'static_web' ? 'preview' : 'proxy';
      dom.frame.src = `/api/atlas/play/${base}/${encodeURIComponent(session.session_id)}/`;
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
          <button type="button" class="atlas-capsule-btn" data-capsule-action="close">Cancel</button>
        </div>
      </div>`;
    document.body.appendChild(el);
    el.addEventListener('click', (ev) => {
      const action = ev.target.closest('[data-capsule-action]')?.dataset.capsuleAction;
      if (action === 'close') closeCapsuleDialog();
      if (action === 'build') buildCapsule();
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
    const profile = state.launchProfile;
    if (!profile) return [];
    return [profile];
  }

  function showCapsuleHandoff() {
    ensureCapsuleDialog();
    const dialog = $('atlas-capsule-dialog');
    const session = state.session || {};
    const eligible = session.session_id && (session.state === 'stopped') && (session.exit_code === 0 || session.exit_code == null);
    const elig = $('atlas-capsule-eligibility');
    if (elig) {
      elig.textContent = eligible
        ? '対象: 直近の成功した Play セッション。ビルドした Capsule は Portal カタログへ自動登録されます。'
        : 'Capsule には成功した Play セッションが必要です。先に Play を実行し、正常終了させてください。';
    }
    const nameInput = $('atlas-capsule-name');
    if (nameInput && !nameInput.value) nameInput.value = String(state.projectId || projectId() || '').replace(/[^A-Za-z0-9_.-]/g, '-') || 'app';
    const profiles = capsuleProfiles();
    const host = $('atlas-capsule-profiles');
    if (host) {
      host.innerHTML = profiles.length
        ? profiles.map((p, i) => `<label><input type="checkbox" data-capsule-profile="${escapeHtml(p.profile_id)}"${i === 0 ? ' checked' : ''}> ${escapeHtml(p.name || p.profile_id)} · ${escapeHtml(p.kind)}</label>`).join('')
        : '<span class="atlas-capsule-note">起動プロファイルがありません。Play で対象を選択してください。</span>';
    }
    const buildBtn = dialog.querySelector('[data-capsule-action="build"]');
    if (buildBtn) buildBtn.disabled = !(eligible && profiles.length);
    setCapsuleStatus(eligible ? '' : 'Play 成功セッションが必要です', eligible ? '' : 'error');
    dialog.classList.add('open');
  }

  async function buildCapsule() {
    const session = state.session || {};
    if (!session.session_id) { setCapsuleStatus('Play セッションがありません', 'error'); return; }
    const selectedIds = Array.from(document.querySelectorAll('[data-capsule-profile]'))
      .filter((cb) => cb.checked).map((cb) => cb.getAttribute('data-capsule-profile'));
    if (!selectedIds.length) { setCapsuleStatus('起動プロファイルを1つ以上選択してください', 'error'); return; }
    const profiles = capsuleProfiles().filter((p) => selectedIds.includes(p.profile_id));
    const name = ($('atlas-capsule-name')?.value || '').trim();
    const version = ($('atlas-capsule-version')?.value || '0.1.0').trim();
    const persistData = !!$('atlas-capsule-persist-data')?.checked;
    setCapsuleStatus('Building…');
    const resp = await api()?.buildCapsule?.({
      project_id: state.projectId || projectId(),
      play_session_id: session.session_id,
      selected_profile_ids: selectedIds,
      launch_profiles: profiles,
      default_profile_id: selectedIds[0],
      package_id: name || undefined,
      name: name || undefined,
      version: version || '0.1.0',
      data_policy: { persistent_data_supported: persistData, export_includes_runtime_data: false },
    });
    if (!resp || !resp.ok) {
      setCapsuleStatus(`Build failed: ${resp?.data?.error || resp?.code || 'error'}`, 'error');
      return;
    }
    const record = resp.data?.record || {};
    setCapsuleStatus(`Built ${record.package_id} v${record.version} → Portal カタログへ登録済み (${(record.content_hash || '').slice(0, 12)}…)`, 'ok');
    try { root.Portal?.refreshCatalog?.(); } catch (_e) {}
  }

  root.AtlasPlayWorkspace = { openTargetChooser, closeWorkspace, showCapsuleHandoff };
})();
