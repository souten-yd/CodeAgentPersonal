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

(function installAtlasClaudeProjectPathControl() {
  const root = (typeof window !== 'undefined' ? window : globalThis);
  const STORAGE_KEY = 'kasane.atlas.project_path';
  const STYLE_ID = 'atlas-claude-project-path-style';
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

  let hydrationStarted = false;
  let patchTimer = null;

  function isUsableProjectPath(value) {
    const text = String(value || '').trim();
    if (!text) return false;
    const lower = text.toLowerCase();
    return !lower.includes('backend-provided project path') && lower !== 'default workspace';
  }

  function readStoredProjectPath() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return isUsableProjectPath(stored) ? stored.trim() : '';
    } catch (_err) {
      return '';
    }
  }

  function writeStoredProjectPath(value) {
    const text = String(value || '').trim();
    if (!text) return;
    try { localStorage.setItem(STORAGE_KEY, text); } catch (_err) {}
  }

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .atlas-claude-header-actions {
        align-items: center;
        justify-content: flex-end;
        gap: 6px;
        flex-wrap: wrap;
        margin-left: auto;
        min-width: 0;
      }
      .atlas-claude-project-path-control {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 6px;
        min-width: min(100%, 260px);
        max-width: min(48vw, 520px);
      }
      .atlas-claude-project-path-label {
        color: var(--text3);
        font-family: var(--font-mono);
        font-size: 10px;
        white-space: nowrap;
      }
      .atlas-claude-project-path-input {
        width: clamp(180px, 26vw, 420px);
        min-width: 0;
        border: 1px solid var(--border);
        border-radius: 6px;
        background: var(--bg2);
        color: var(--text);
        font-family: var(--font-mono);
        font-size: 11px;
        padding: 4px 8px;
        outline: none;
      }
      .atlas-claude-project-path-input:focus {
        border-color: var(--accent-border);
      }
      .atlas-claude-project-path-input[aria-invalid="true"] {
        border-color: var(--red);
      }
      .atlas-claude-project-path-error {
        flex-basis: 100%;
        color: var(--red);
        font-family: var(--font-mono);
        font-size: 10px;
        text-align: right;
      }
      @media (max-width: 700px) {
        .atlas-claude-header {
          align-items: flex-start;
          flex-wrap: wrap;
        }
        .atlas-claude-header-actions {
          width: 100%;
        }
        .atlas-claude-project-path-control {
          flex: 1 1 100%;
          max-width: 100%;
        }
        .atlas-claude-project-path-input {
          flex: 1 1 auto;
          width: auto;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function ensureControl() {
    const actions = document.querySelector('.atlas-claude-header-actions');
    const recover = document.getElementById('atlas-claude-recovery-btn');
    if (!actions || !recover) return false;
    if (document.getElementById('atlas-claude-project-path-input')) return true;

    const control = document.createElement('label');
    control.className = 'atlas-claude-project-path-control';
    control.setAttribute('for', 'atlas-claude-project-path-input');

    const label = document.createElement('span');
    label.className = 'atlas-claude-project-path-label';
    label.textContent = 'Project path';

    const input = document.createElement('input');
    input.id = 'atlas-claude-project-path-input';
    input.className = 'atlas-claude-project-path-input';
    input.type = 'text';
    input.placeholder = 'Backend project path';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.value = readStoredProjectPath();

    const error = document.createElement('span');
    error.id = 'atlas-claude-project-path-error';
    error.className = 'atlas-claude-project-path-error';
    error.hidden = true;

    input.addEventListener('input', () => {
      const value = input.value.trim();
      if (value) writeStoredProjectPath(value);
      input.removeAttribute('aria-invalid');
      error.hidden = true;
      error.textContent = '';
    });

    control.append(label, input, error);
    actions.insertBefore(control, recover);
    return true;
  }

  async function hydrateDefaultProjectPath() {
    if (hydrationStarted) return;
    hydrationStarted = true;
    if (!ensureControl()) return;
    const input = document.getElementById('atlas-claude-project-path-input');
    if (!input || input.value.trim()) return;
    const stored = readStoredProjectPath();
    if (stored) {
      input.value = stored;
      return;
    }
    try {
      const response = await fetch('/api/atlas/workflow-state/read-only', { headers: { 'Content-Type': 'application/json' } });
      if (!response.ok) return;
      const payload = await response.json();
      const projectPath = payload && payload.project_path;
      if (isUsableProjectPath(projectPath)) {
        input.value = String(projectPath).trim();
        writeStoredProjectPath(input.value);
      }
    } catch (_err) {
      // Keep the field editable; backend remains authoritative when a request is made.
    }
  }

  function pushValidationMessage(message) {
    const transcript = document.getElementById('atlas-claude-transcript');
    if (!transcript) return;
    const previous = document.getElementById('atlas-claude-project-path-validation-msg');
    if (previous) previous.remove();
    const node = document.createElement('div');
    node.id = 'atlas-claude-project-path-validation-msg';
    node.className = 'atlas-claude-msg';
    node.dataset.role = 'system';
    node.textContent = message;
    transcript.appendChild(node);
    transcript.scrollTop = transcript.scrollHeight;
  }

  function showValidation(message) {
    ensureControl();
    const input = document.getElementById('atlas-claude-project-path-input');
    const error = document.getElementById('atlas-claude-project-path-error');
    if (input) input.setAttribute('aria-invalid', 'true');
    if (error) {
      error.textContent = message;
      error.hidden = false;
    }
    pushValidationMessage(message);
  }

  function getProjectPath() {
    ensureControl();
    const input = document.getElementById('atlas-claude-project-path-input');
    const value = input ? String(input.value || '').trim() : '';
    return isUsableProjectPath(value) ? value : readStoredProjectPath();
  }

  function requireProjectPath() {
    const projectPath = getProjectPath();
    if (!projectPath) {
      showValidation('Project path is required.');
      return '';
    }
    writeStoredProjectPath(projectPath);
    return projectPath;
  }

  function withProjectPath(payload) {
    const projectPath = requireProjectPath();
    const base = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {};
    return projectPath ? { ...base, project_path: projectPath } : base;
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
    ensureControl();
    hydrateDefaultProjectPath();
    const apiReady = patchAtlasPipelineAPI();
    const recoverReady = patchAtlasDashboardRecover();
    if (apiReady && recoverReady) return;
    if (patchTimer) return;
    patchTimer = setInterval(() => {
      ensureControl();
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
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, { once: true });
  } else {
    install();
  }
  window.addEventListener('load', install, { once: true });
})();
