/*
 * Forge mode (PFG-20+) — top-level Model Forge shell.
 *
 * Read-only shell that calls the /api/forge backend through a small internal tab router:
 *   Overview (PFG-21) | Skills (PFG-22) | ...benchmark/arena/matrix/loadouts land in
 *   PFG-23..PFG-26.
 * Forge never executes a model from here and never changes production routing; it only
 * reflects backend state. A missing external key is shown as a disabled/unavailable
 * status with a plain note, not as repeated error noise.
 */
(function () {
  'use strict';
  const root = (typeof window !== 'undefined' ? window : globalThis);

  function $(id) { return document.getElementById(id); }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
    ));
  }

  const TABS = [
    { id: 'overview', label: 'Overview' },
    { id: 'skills', label: 'Skills' },
  ];

  const state = {
    activated: false,
    loading: false,
    tab: 'overview',
    data: { status: {}, providers: [], loadouts: [], profiles: [], leaderboard: [] },
  };

  function setStatus(text, kind) {
    const el = $('forge-status');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('is-error', kind === 'error');
    el.classList.toggle('is-ok', kind === 'ok');
  }

  async function api(path, options) {
    const resp = await fetch('/api/forge' + path, Object.assign({
      headers: { 'Content-Type': 'application/json' },
    }, options || {}));
    if (!resp.ok) {
      let detail = resp.status + '';
      try { detail = (await resp.json()).detail || detail; } catch (_e) {}
      throw new Error(detail);
    }
    return resp.json();
  }

  function healthBadge(stateValue) {
    const v = String(stateValue || 'error');
    const label = v === 'ready' ? 'Ready'
      : v === 'disabled' ? 'Disabled'
      : v === 'unavailable' ? 'Unavailable'
      : 'Error';
    return '<span class="forge-badge forge-badge-' + escapeHtml(v) + '">' + escapeHtml(label) + '</span>';
  }

  function providerLabel(id) {
    return id === 'legacy_atlas' ? 'Legacy Atlas'
      : id === 'local_openai_compatible' ? 'Local model'
      : id === 'openrouter' ? 'OpenRouter'
      : id;
  }

  // A non-ready external provider is informative, not an error: explain it plainly.
  function healthNote(p) {
    const h = String(p.health || '');
    if (h === 'ready') return '';
    const detail = String(p.health_detail || '');
    if (p.provider_id === 'openrouter' && (h === 'disabled' || detail.indexOf('credential') >= 0)) {
      return h === 'disabled' ? 'Disabled by default — enable in policy to use.'
        : 'No API key configured (set OPENROUTER_API_KEY to enable).';
    }
    if (p.provider_id === 'local_openai_compatible' && detail.indexOf('base_url') >= 0) {
      return 'No local server configured (set FORGE_LOCAL_BASE_URL).';
    }
    if (p.provider_id === 'legacy_atlas') return 'Runs in the Atlas pipeline, not from Forge.';
    return detail ? detail.replace(/_/g, ' ') : '';
  }

  function providerCard(p) {
    const note = healthNote(p);
    return (
      '<div class="forge-prov-card" data-provider="' + escapeHtml(p.provider_id) + '">'
      + '<div class="forge-prov-row">'
      + '<span class="forge-prov-id">' + escapeHtml(providerLabel(p.provider_id)) + '</span>'
      + '<span class="forge-prov-class">' + escapeHtml(p.source_class || '') + '</span>'
      + healthBadge(p.health)
      + '</div>'
      + (note ? '<div class="forge-prov-note">' + escapeHtml(note) + '</div>' : '')
      + '</div>'
    );
  }

  // ----- view builders (pure: data -> HTML string) -----

  function overviewHtml(data) {
    const status = data.status || {};
    const forgeState = status.forge_enabled ? 'On' : 'Off (legacy primary)';
    const active = (data.loadouts || []).find((l) => l.builtin) || (data.loadouts || [])[0] || null;
    const activeName = active ? active.display_name : '—';
    const cards = (data.providers || []).map(providerCard).join('');
    return (
      '<div class="forge-card">'
      + '<div class="forge-card-title">Overview</div>'
      + '<div class="forge-kv"><span>Forge</span><b>' + escapeHtml(forgeState) + '</b></div>'
      + '<div class="forge-kv"><span>Active loadout</span><b>' + escapeHtml(activeName) + '</b></div>'
      + '<div class="forge-kv"><span>Source mode</span><b>' + escapeHtml(status.source_mode || '') + '</b></div>'
      + '<div class="forge-kv"><span>Profiles</span><b>' + escapeHtml(String(status.profile_count || 0)) + '</b></div>'
      + '</div>'
      + '<div class="forge-card">'
      + '<div class="forge-card-title">Providers</div>'
      + (cards || '<div class="forge-empty">No providers registered.</div>')
      + '</div>'
    );
  }

  function scoreBar(score) {
    const pct = Math.max(0, Math.min(100, Math.round((Number(score) || 0) * 100)));
    return (
      '<span class="forge-bar"><span class="forge-bar-fill" style="width:' + pct + '%"></span></span>'
      + '<span class="forge-bar-val">' + pct + '</span>'
    );
  }

  function championCard(c) {
    return (
      '<div class="forge-champ">'
      + '<div class="forge-champ-dim">' + escapeHtml(c.dimension) + '</div>'
      + '<div class="forge-champ-model">' + escapeHtml(c.model_id) + '</div>'
      + '<div class="forge-champ-score">' + scoreBar(c.score) + '</div>'
      + '</div>'
    );
  }

  function profileRow(p) {
    const dims = p.dimension_scores || {};
    const overall = dims.overall != null ? dims.overall : (function () {
      const vals = Object.keys(dims).map((k) => dims[k]);
      return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
    })();
    return (
      '<div class="forge-model-row" data-model="' + escapeHtml(p.provider_id + '/' + p.model_id) + '">'
      + '<span class="forge-model-id">' + escapeHtml(p.model_id) + '</span>'
      + '<span class="forge-model-prov">' + escapeHtml(p.provider_id) + '</span>'
      + '<span class="forge-model-bar">' + scoreBar(overall) + '</span>'
      + '</div>'
    );
  }

  function skillsHtml(data) {
    const leaderboard = data.leaderboard || [];
    const profiles = data.profiles || [];
    if (!leaderboard.length && !profiles.length) {
      return (
        '<div class="forge-card">'
        + '<div class="forge-card-title">Skill Radar</div>'
        + '<div class="forge-empty">No model profiles yet. Run a benchmark or Arena to '
        + 'record model skills — champions and per-skill scores will appear here.</div>'
        + '</div>'
      );
    }
    const champs = leaderboard.map(championCard).join('');
    const rows = profiles.map(profileRow).join('');
    return (
      '<div class="forge-card">'
      + '<div class="forge-card-title">Champions</div>'
      + '<div class="forge-champ-grid">' + (champs || '<div class="forge-empty">No champions yet.</div>') + '</div>'
      + '</div>'
      + '<div class="forge-card">'
      + '<div class="forge-card-title">Models</div>'
      + (rows || '<div class="forge-empty">No models yet.</div>')
      + '</div>'
    );
  }

  const VIEWS = { overview: overviewHtml, skills: skillsHtml };

  // ----- model detail drawer (Skills) -----

  function openModelDrawer(modelKey) {
    const profile = (state.data.profiles || []).find(
      (p) => (p.provider_id + '/' + p.model_id) === modelKey
    );
    if (!profile) return;
    const dims = profile.dimension_scores || {};
    const rows = Object.keys(dims).sort().map((d) => (
      '<div class="forge-kv"><span>' + escapeHtml(d) + '</span><b>' + scoreBar(dims[d]) + '</b></div>'
    )).join('') || '<div class="forge-empty">No dimension scores.</div>';
    let drawer = $('forge-drawer');
    if (!drawer) {
      drawer = document.createElement('div');
      drawer.id = 'forge-drawer';
      drawer.className = 'forge-drawer';
      document.body.appendChild(drawer);
    }
    drawer.innerHTML = (
      '<div class="forge-drawer-inner">'
      + '<div class="forge-drawer-head"><span>' + escapeHtml(profile.model_id) + '</span>'
      + '<button type="button" class="forge-drawer-close" aria-label="Close">×</button></div>'
      + '<div class="forge-drawer-sub">' + escapeHtml(profile.provider_id)
      + ' · ' + escapeHtml(String(profile.sample_count || 0)) + ' samples</div>'
      + '<div class="forge-drawer-body">' + rows + '</div>'
      + '</div>'
    );
    drawer.classList.add('open');
    drawer.querySelector('.forge-drawer-close')?.addEventListener('click', closeModelDrawer);
    drawer.addEventListener('click', (e) => { if (e.target === drawer) closeModelDrawer(); });
  }

  function closeModelDrawer() {
    $('forge-drawer')?.classList.remove('open');
  }

  // ----- shell / tab routing -----

  function renderShell() {
    const body = $('forge-body');
    if (!body) return;
    const tabs = TABS.map((t) => (
      '<button type="button" class="forge-tab' + (t.id === state.tab ? ' active' : '')
      + '" data-forge-tab="' + t.id + '">' + escapeHtml(t.label) + '</button>'
    )).join('');
    body.innerHTML = (
      '<div class="forge-tabs" role="tablist">' + tabs + '</div>'
      + '<div class="forge-content" id="forge-content"></div>'
    );
    body.querySelectorAll('[data-forge-tab]').forEach((btn) => {
      btn.addEventListener('click', () => setTab(btn.getAttribute('data-forge-tab')));
    });
    renderActive();
  }

  function renderActive() {
    const content = $('forge-content');
    if (!content) return;
    const builder = VIEWS[state.tab] || overviewHtml;
    content.innerHTML = builder(state.data);
    if (state.tab === 'skills') {
      content.querySelectorAll('[data-model]').forEach((row) => {
        row.addEventListener('click', () => openModelDrawer(row.getAttribute('data-model')));
      });
    }
  }

  function setTab(tab) {
    state.tab = tab;
    renderShell();
  }

  async function refresh() {
    if (state.loading) return;
    state.loading = true;
    setStatus('Loading…');
    try {
      const status = await api('/status');
      const data = { status, providers: [], loadouts: [], profiles: [], leaderboard: [] };
      try { data.providers = (await api('/providers')).providers || []; } catch (_e) {}
      try { data.loadouts = (await api('/loadouts')).loadouts || []; } catch (_e) {}
      try { data.profiles = (await api('/profiles')).profiles || []; } catch (_e) {}
      try { data.leaderboard = (await api('/leaderboard')).leaderboard || []; } catch (_e) {}
      state.data = data;
      renderShell();
      setStatus(status.forge_enabled ? 'Forge enabled' : 'Forge off — legacy model execution primary', 'ok');
    } catch (err) {
      setStatus('Forge unavailable: ' + (err && err.message ? err.message : 'error'), 'error');
    } finally {
      state.loading = false;
    }
  }

  function activate() {
    state.activated = true;
    refresh();
  }

  function onLeave() { state.activated = false; closeModelDrawer(); }

  document.addEventListener('DOMContentLoaded', () => {
    $('forge-refresh-btn')?.addEventListener('click', refresh);
  });

  // Back-compat standalone renderer (used by focused tests).
  function renderOverview(status, providers, loadouts) {
    const body = $('forge-body');
    if (body) body.innerHTML = overviewHtml({ status, providers, loadouts });
  }

  root.Forge = {
    activate, onLeave, refresh, setTab,
    _renderOverview: renderOverview,
    _overviewHtml: overviewHtml,
    _skillsHtml: skillsHtml,
  };
})();
