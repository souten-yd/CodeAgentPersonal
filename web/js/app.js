window.KASANE_UI_BOOTSTRAP_LOADED = true;

(function installAtlasNextChildViewBootstrap() {
  const route = '/atlas-next/';
  const styleId = 'atlas-next-child-view-style';
  const frameId = 'atlas-next-child-frame';

  function ensureStyle() {
    if (document.getElementById(styleId)) return;
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = `
      #atlas-dashboard[data-atlas-next-child-view="enabled"] #atlas-workflow-shell,
      #atlas-dashboard[data-atlas-next-child-view="enabled"] .atlas-goal-card,
      #atlas-dashboard[data-atlas-next-child-view="enabled"] #atlas-recovery-banner,
      #atlas-dashboard[data-atlas-next-child-view="enabled"] #atlas-status-grid,
      #atlas-dashboard[data-atlas-next-child-view="enabled"] #atlas-automation-readiness-panel,
      #atlas-dashboard[data-atlas-next-child-view="enabled"] #atlas-diagnostics-drawer,
      #atlas-dashboard[data-atlas-next-child-view="enabled"] .atlas-work-grid,
      #atlas-dashboard[data-atlas-next-child-view="enabled"] #atlas-current-item-card,
      #atlas-dashboard[data-atlas-next-child-view="enabled"] #atlas-manual-loop-checklist,
      #atlas-dashboard[data-atlas-next-child-view="enabled"] #atlas-details-drawer,
      #atlas-dashboard[data-atlas-next-child-view="enabled"] .atlas-legacy-compat { display: none !important; }
      .atlas-next-child-shell { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--bg); min-height: 760px; }
      .atlas-next-child-frame { display: block; width: 100%; min-height: 760px; border: 0; background: #e8edf4; }
    `;
    document.head.appendChild(style);
  }

  function ensureAtlasNextChildView() {
    const root = document.getElementById('atlas-dashboard');
    const card = document.getElementById('atlas-workbench-card');
    if (!root || !card) return false;
    root.dataset.atlasNextChildView = 'enabled';
    ensureStyle();

    let frame = document.getElementById(frameId);
    if (!frame) {
      const shell = document.createElement('section');
      shell.className = 'atlas-next-child-shell';
      shell.setAttribute('aria-label', 'Atlas Next child workbench');
      frame = document.createElement('iframe');
      frame.id = frameId;
      frame.className = 'atlas-next-child-frame';
      frame.title = 'Atlas Next Workbench';
      frame.loading = 'eager';
      shell.appendChild(frame);
      const anchor = document.getElementById('atlas-workbench-card-resume-notice') || document.getElementById('atlas-workbench-status');
      if (anchor && anchor.parentElement === card) anchor.insertAdjacentElement('afterend', shell);
      else card.insertBefore(shell, card.firstElementChild?.nextElementSibling || card.firstChild);
    }
    if (frame.getAttribute('src') !== route) frame.setAttribute('src', route);
    return true;
  }

  window.KASANE_ATLAS_NEXT_CHILD_VIEW = {
    enabled: true,
    route,
    install: ensureAtlasNextChildView,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureAtlasNextChildView, { once: true });
  } else {
    ensureAtlasNextChildView();
  }
  window.addEventListener('load', ensureAtlasNextChildView, { once: true });
})();

(function installAtlasClaudeProjectPicker() {
  const root = (typeof window !== 'undefined' ? window : globalThis);
  const STORAGE_KEY = 'kasane.atlas.active_project';
  const STYLE_ID = 'atlas-claude-project-picker-style';
  const PATCHED_FLAG = '__atlasProjectPathPatched';
  const payloadMethods = [
    'createPlanPool',
    'startPipelineDryRun',
    'generatePatchProposal',
    'decidePatchProposal',
    'createPatchProposalPlanItemDraft',
    'runMultiItemAutopilot',
    'getLatestMultiItemAutopilotResult',
    'startAutonomousLoopFromEnvelope',
    'devToolGitStatus',
    'devToolGitDiff',
    'devToolGitLsFiles',
    'devToolProjectTree',
    'devToolListFiles',
    'devToolFileOutline',
    'buildRepoIndex',
    'getRepoIndexImpacts',
    'getRepoIndexRelatedTests',
    'getRepoContextSnapshot',
    'getRepoContextScopeSummary',
    'getRepoContextVerificationPlan',
    'getRepoContextPlanItemImpactMap',
    'getPlannerPackagingV2',
    'getVerificationRecommendation',
    'getVerificationRecommendationHandoff',
    'getRepoContextImpactedTests',
  ];

  let patchTimer = null;
  let bootstrapped = false;
  // The currently selected Atlas project. Its name doubles as the Atlas
  // workspace_id, and projectPath is the working dir the autopilot operates on.
  let activeProject = { name: '', projectPath: '', workspaceId: '' };
  let projectsCache = [];

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  }

  function readStoredName() {
    try { return (localStorage.getItem(STORAGE_KEY) || '').trim(); } catch (_err) { return ''; }
  }

  function writeStoredName(name) {
    const text = String(name || '').trim();
    if (!text) return;
    try { localStorage.setItem(STORAGE_KEY, text); } catch (_err) {}
  }

  function setActiveProject(project) {
    if (!project || !project.name) return;
    activeProject = {
      name: project.name,
      projectPath: project.project_path || project.projectPath || '',
      workspaceId: project.workspace_id || project.workspaceId || project.name,
    };
    writeStoredName(activeProject.name);
    updateButtonLabel();
    // Mirror onto the panel so its API calls use the selected workspace.
    try { root.AtlasClaudePanel?.setActiveProject?.(activeProject); } catch (_err) {}
  }

  // Used after an auto-rename (B): keep the same working dir, swap name/workspace.
  function setActive(name) {
    const found = projectsCache.find((p) => p.name === name);
    if (found) { setActiveProject(found); }
    else {
      activeProject = { name, projectPath: activeProject.projectPath, workspaceId: name };
      writeStoredName(name);
      updateButtonLabel();
      try { root.AtlasClaudePanel?.setActiveProject?.(activeProject); } catch (_err) {}
    }
    loadProjects().catch(() => {});
  }

  function getActiveProject() { return { ...activeProject }; }

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .atlas-claude-header-actions {
        align-items: center;
        justify-content: flex-start;
        gap: 6px;
        flex-wrap: nowrap;
        min-width: 0;
      }
      .atlas-claude-proj-wrap {
        position: relative;
        min-width: 0;
        max-width: min(60vw, 260px);
      }
      .atlas-claude-proj-btn {
        display: flex;
        align-items: center;
        gap: 6px;
        max-width: 100%;
        border: 1px solid var(--border);
        border-radius: 8px;
        background: var(--bg2);
        color: var(--text);
        font-family: var(--font-mono);
        font-size: 12px;
        padding: 5px 10px;
        cursor: pointer;
      }
      .atlas-claude-proj-btn .atlas-claude-proj-name {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 160px;
      }
      .atlas-claude-proj-btn .atlas-claude-proj-caret { color: var(--text3); font-size: 9px; }
      .atlas-claude-proj-dropdown {
        position: absolute;
        top: calc(100% + 6px);
        left: 0;
        z-index: 1000;
        width: max-content;
        min-width: 240px;
        max-width: min(92vw, 360px);
        max-height: min(60vh, 420px);
        overflow-y: auto;
        background: var(--bg2);
        border: 1px solid var(--border);
        border-radius: 10px;
        box-shadow: 0 8px 28px rgba(0,0,0,0.45);
        padding: 6px;
      }
      .atlas-claude-proj-dropdown[hidden] { display: none; }
      .atlas-claude-proj-overlay {
        position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 1200;
        display: none; backdrop-filter: blur(2px);
      }
      .atlas-claude-proj-overlay.open { display: block; }
      .atlas-claude-proj-drawer {
        position: fixed; top: 0; left: 0; bottom: 0; width: min(86vw, 300px);
        background: var(--bg1); border-right: 1px solid var(--border); z-index: 1201;
        display: flex; flex-direction: column;
        transform: translateX(-100%); transition: transform .22s ease;
      }
      .atlas-claude-proj-drawer.open { transform: none; }
      .atlas-claude-proj-drawer-hdr {
        display: flex; align-items: center; justify-content: space-between;
        padding: 14px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0;
      }
      .atlas-claude-proj-drawer-title { font-size: 14px; font-weight: 700; letter-spacing: .05em; color: var(--text); }
      .atlas-claude-proj-drawer-close {
        width: 28px; height: 28px; border-radius: 6px; border: 1px solid var(--border);
        background: var(--bg2); color: var(--text2); cursor: pointer; font-size: 15px;
        display: flex; align-items: center; justify-content: center;
      }
      .atlas-claude-proj-drawer .atlas-claude-proj-list { flex: 1; overflow-y: auto; padding: 8px; }
      .atlas-claude-proj-drawer .atlas-claude-proj-new {
        padding: 10px; border-top: 1px solid var(--border); flex-shrink: 0; display: flex; gap: 6px;
      }
      .atlas-claude-proj-item {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 7px 8px;
        border-radius: 8px;
        cursor: pointer;
      }
      .atlas-claude-proj-item:hover { background: var(--bg3, rgba(255,255,255,0.05)); }
      .atlas-claude-proj-item.active { outline: 1px solid var(--accent-border, var(--accent)); }
      .atlas-claude-proj-item .atlas-claude-proj-iname {
        flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        font-size: 12px; color: var(--text);
      }
      .atlas-claude-proj-item .atlas-claude-proj-icount { font-size: 10px; color: var(--text3); }
      .atlas-claude-proj-item button {
        flex: 0 0 auto; border: 1px solid var(--border); border-radius: 6px;
        background: transparent; color: var(--text2); font-size: 10px; padding: 3px 7px; cursor: pointer;
      }
      .atlas-claude-proj-item button.atlas-claude-proj-del { color: var(--red); }
      .atlas-claude-proj-new {
        display: flex; gap: 6px; padding: 6px 4px 2px; border-top: 1px solid var(--border); margin-top: 4px;
      }
      .atlas-claude-proj-new input {
        flex: 1; min-width: 0; border: 1px solid var(--border); border-radius: 6px;
        background: var(--bg); color: var(--text); font-size: 11px; padding: 5px 8px; outline: none;
      }
      .atlas-claude-proj-new button {
        flex: 0 0 auto; border: 1px solid var(--border); border-radius: 6px;
        background: var(--accent); color: var(--bg, #000); font-size: 11px; padding: 5px 10px; cursor: pointer;
      }
    `;
    document.head.appendChild(style);
  }

  function ensurePicker() {
    const actions = document.querySelector('.atlas-claude-header-actions');
    const recover = document.getElementById('atlas-claude-recovery-btn');
    if (!actions) return false;
    if (document.getElementById('atlas-claude-proj-wrap')) return true;

    // Header button only — opens a left slide-in drawer (mirrors the Lumen project drawer) instead of
    // an absolutely-positioned dropdown that got clipped by the panel's bounds.
    const wrap = document.createElement('div');
    wrap.className = 'atlas-claude-proj-wrap';
    wrap.id = 'atlas-claude-proj-wrap';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'atlas-claude-proj-btn';
    btn.id = 'atlas-claude-proj-btn';
    btn.innerHTML = '<span>◈</span><span class="atlas-claude-proj-name" id="atlas-claude-proj-name">default</span><span class="atlas-claude-proj-caret">▼</span>';
    btn.addEventListener('click', (ev) => { ev.stopPropagation(); toggleDropdown(); });

    wrap.append(btn);
    if (recover && recover.parentElement === actions) actions.insertBefore(wrap, recover);
    else actions.insertBefore(wrap, actions.firstChild);

    ensureProjectDrawer();
    return true;
  }

  function ensureProjectDrawer() {
    if (document.getElementById('atlas-claude-proj-drawer')) return;
    const overlay = document.createElement('div');
    overlay.className = 'atlas-claude-proj-overlay';
    overlay.id = 'atlas-claude-proj-overlay';
    overlay.addEventListener('click', () => closeDropdown());

    const drawer = document.createElement('div');
    drawer.className = 'atlas-claude-proj-drawer';
    drawer.id = 'atlas-claude-proj-drawer';
    drawer.innerHTML = ''
      + '<div class="atlas-claude-proj-drawer-hdr">'
      + '<span class="atlas-claude-proj-drawer-title">プロジェクト</span>'
      + '<button type="button" class="atlas-claude-proj-drawer-close" id="atlas-claude-proj-drawer-close" aria-label="閉じる">✕</button>'
      + '</div>'
      + '<div class="atlas-claude-proj-list" id="atlas-claude-proj-list"></div>'
      + '<div class="atlas-claude-proj-new">'
      + '<input id="atlas-claude-proj-new-input" type="text" placeholder="新規プロジェクト名" autocomplete="off" spellcheck="false">'
      + '<button type="button" id="atlas-claude-proj-new-btn">作成</button></div>';
    drawer.addEventListener('click', (ev) => ev.stopPropagation());

    document.body.append(overlay, drawer);

    drawer.querySelector('#atlas-claude-proj-drawer-close').addEventListener('click', () => closeDropdown());
    drawer.querySelector('#atlas-claude-proj-new-btn').addEventListener('click', () => {
      const inp = drawer.querySelector('#atlas-claude-proj-new-input');
      const name = inp ? inp.value.trim() : '';
      createProject(name);
      if (inp) inp.value = '';
    });
    drawer.querySelector('#atlas-claude-proj-new-input').addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') { ev.preventDefault(); drawer.querySelector('#atlas-claude-proj-new-btn').click(); }
    });
    document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') closeDropdown(); });
  }

  function toggleDropdown() {
    const drawer = document.getElementById('atlas-claude-proj-drawer');
    if (!drawer) return;
    if (drawer.classList.contains('open')) { closeDropdown(); }
    else {
      drawer.classList.add('open');
      const ov = document.getElementById('atlas-claude-proj-overlay');
      if (ov) ov.classList.add('open');
      loadProjects().catch(() => {});
    }
  }

  function closeDropdown() {
    const drawer = document.getElementById('atlas-claude-proj-drawer');
    const ov = document.getElementById('atlas-claude-proj-overlay');
    if (drawer) drawer.classList.remove('open');
    if (ov) ov.classList.remove('open');
  }

  function updateButtonLabel() {
    const el = document.getElementById('atlas-claude-proj-name');
    if (el) el.textContent = activeProject.name || 'default';
  }

  function renderProjects() {
    const list = document.getElementById('atlas-claude-proj-list');
    if (!list) return;
    if (!projectsCache.length) {
      list.innerHTML = '<div class="atlas-claude-proj-icount" style="padding:8px">プロジェクトがありません</div>';
      return;
    }
    list.innerHTML = projectsCache.map((p) => {
      const active = p.name === activeProject.name ? ' active' : '';
      const count = `${p.file_count || 0} file${(p.file_count === 1) ? '' : 's'}`;
      return `<div class="atlas-claude-proj-item${active}" data-name="${escapeHtml(p.name)}">`
        + '<span>◈</span>'
        + `<div style="flex:1;min-width:0"><div class="atlas-claude-proj-iname">${escapeHtml(p.name)}</div>`
        + `<div class="atlas-claude-proj-icount">${escapeHtml(count)}</div></div>`
        + `<button type="button" class="atlas-claude-proj-dl" data-name="${escapeHtml(p.name)}">DL</button>`
        + `<button type="button" class="atlas-claude-proj-del" data-name="${escapeHtml(p.name)}">✕</button>`
        + '</div>';
    }).join('');
    list.querySelectorAll('.atlas-claude-proj-item').forEach((item) => {
      item.addEventListener('click', (ev) => {
        if (ev.target.closest('button')) return;
        selectProject(item.dataset.name);
      });
    });
    list.querySelectorAll('.atlas-claude-proj-dl').forEach((b) => {
      b.addEventListener('click', (ev) => { ev.stopPropagation(); downloadProject(b.dataset.name); });
    });
    list.querySelectorAll('.atlas-claude-proj-del').forEach((b) => {
      b.addEventListener('click', (ev) => { ev.stopPropagation(); deleteProject(b.dataset.name); });
    });
  }

  async function loadProjects() {
    try {
      const resp = await fetch('/api/atlas/projects', { headers: { 'Content-Type': 'application/json' } });
      if (!resp.ok) return projectsCache;
      const data = await resp.json();
      projectsCache = (data && data.projects) || [];
      renderProjects();
    } catch (_err) { /* non-fatal */ }
    return projectsCache;
  }

  function selectProject(name) {
    const found = projectsCache.find((p) => p.name === name);
    if (!found) return;
    setActiveProject(found);
    renderProjects();
    closeDropdown();
    try { root.AtlasClaudePanel?.loadProject?.(found.name); } catch (_err) {}
  }

  async function createProject(name) {
    try {
      const resp = await fetch('/api/atlas/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name || '' }),
      });
      if (!resp.ok) return;
      const created = await resp.json();
      await loadProjects();
      if (created && created.name) selectProject(created.name);
    } catch (_err) { /* non-fatal */ }
  }

  async function deleteProject(name) {
    if (typeof confirm === 'function' && !confirm(`プロジェクト "${name}" を削除しますか？`)) return;
    try {
      await fetch('/api/atlas/projects/' + encodeURIComponent(name), { method: 'DELETE' });
    } catch (_err) { /* non-fatal */ }
    await loadProjects();
    if (activeProject.name === name) {
      if (projectsCache.length) selectProject(projectsCache[0].name);
      else createProject('');
    }
  }

  function downloadProject(name) {
    const a = document.createElement('a');
    a.href = '/api/atlas/projects/' + encodeURIComponent(name) + '/download';
    a.download = `${name}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function bootstrapProjects() {
    if (bootstrapped) return;
    bootstrapped = true;
    if (!ensurePicker()) { bootstrapped = false; return; }
    const list = await loadProjects();
    if (!list.length) { await createProject(''); return; }
    const stored = readStoredName();
    const chosen = (stored && list.find((p) => p.name === stored)) || list[0];
    setActiveProject(chosen);
    renderProjects();
  }

  // Backwards-compatible accessors: the selected project's working dir IS the
  // project path. Returns '' when no project is selected yet.
  function getProjectPath() { return activeProject.projectPath || ''; }
  function requireProjectPath() { return activeProject.projectPath || ''; }

  function withProjectPath(payload) {
    const base = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {};
    const out = { ...base };
    if (activeProject.projectPath) out.project_path = activeProject.projectPath;
    if (activeProject.workspaceId) out.workspace_id = activeProject.workspaceId;
    return out;
  }

  function patchAtlasPipelineAPI() {
    const api = root.AtlasPipelineAPI;
    if (!api) return false;
    payloadMethods.forEach((methodName) => {
      const original = api[methodName];
      if (typeof original !== 'function' || original[PATCHED_FLAG]) return;
      const wrapped = function atlasProjectPathWrappedPayloadMethod(payload, ...rest) {
        return original.call(this, withProjectPath(payload || {}), ...rest);
      };
      wrapped[PATCHED_FLAG] = true;
      api[methodName] = wrapped;
    });
    return true;
  }

  function patchAtlasDashboardRecover() {
    const dashboard = root.AtlasDashboard;
    if (!dashboard || typeof dashboard.loadRecoveredPlan !== 'function' || dashboard.loadRecoveredPlan[PATCHED_FLAG]) return !!dashboard;
    const original = dashboard.loadRecoveredPlan;
    const wrapped = function atlasProjectPathWrappedRecover(...args) {
      const projectPath = requireProjectPath();
      if (!projectPath) return null;
      if (args.length > 0 && args[0] && typeof args[0] === 'object' && !Array.isArray(args[0])) {
        args[0] = { ...args[0], project_path: projectPath };
      } else if (args.length === 0) {
        args.push({ project_path: projectPath });
      }
      return original.apply(this, args);
    };
    wrapped[PATCHED_FLAG] = true;
    dashboard.loadRecoveredPlan = wrapped;
    return true;
  }

  function install() {
    ensureStyle();
    ensurePicker();
    bootstrapProjects();
    const apiReady = patchAtlasPipelineAPI();
    const recoverReady = patchAtlasDashboardRecover();
    if (apiReady && recoverReady) return;
    if (patchTimer) return;
    patchTimer = setInterval(() => {
      ensurePicker();
      const patchedApi = patchAtlasPipelineAPI();
      const patchedRecover = patchAtlasDashboardRecover();
      if (patchedApi && patchedRecover) {
        clearInterval(patchTimer);
        patchTimer = null;
      }
    }, 250);
    setTimeout(() => {
      if (patchTimer) {
        clearInterval(patchTimer);
        patchTimer = null;
      }
    }, 10000);
  }

  root.KASANE_ATLAS_PROJECT_PATH = {
    key: STORAGE_KEY,
    get: getProjectPath,
    require: requireProjectPath,
    withProjectPath,
    install,
    setActive,
    getActive: getActiveProject,
    selectProject,
    reloadProjects: loadProjects,
    applyRenamed: (payload) => { setActiveProject(payload); loadProjects().catch(() => {}); },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, { once: true });
  } else {
    install();
  }
  window.addEventListener('load', install, { once: true });
})();
