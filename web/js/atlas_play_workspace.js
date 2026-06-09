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

  function showCapsuleHandoff() {
    openWorkspace();
    setStatus('Capsule builder starts in PR-PPC-7');
  }

  root.AtlasPlayWorkspace = { openTargetChooser, closeWorkspace, showCapsuleHandoff };
})();
