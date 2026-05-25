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
