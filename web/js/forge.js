/*
 * Forge mode (PFG-20) — top-level Model Forge shell.
 *
 * Read-only shell that calls the /api/forge backend. The default view shows the Overview
 * (Active Loadout, Source Mode) and Provider cards (legacy/local/OpenRouter health).
 * Skill Radar, Leaderboard, Benchmark, Arena, Stage/Route matrices, and Loadout editing
 * are layered on in PFG-22..PFG-26. Forge never executes a model from here and never
 * changes production routing; it only reflects backend state. A missing external key is
 * shown as a disabled/unavailable status, not as repeated error noise.
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

  const state = { activated: false, loading: false };

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

  function renderOverview(status, providers, loadouts) {
    const body = $('forge-body');
    if (!body) return;
    const forgeState = status.forge_enabled ? 'On' : 'Off (legacy primary)';
    const active = (loadouts || []).find((l) => l.builtin) || (loadouts || [])[0] || null;
    const activeName = active ? active.display_name : '—';
    const cards = (providers || []).map(providerCard).join('');
    body.innerHTML = (
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

  async function refresh() {
    if (state.loading) return;
    state.loading = true;
    setStatus('Loading…');
    try {
      const status = await api('/status');
      let providers = [];
      let loadouts = [];
      try { providers = (await api('/providers')).providers || []; } catch (_e) {}
      try { loadouts = (await api('/loadouts')).loadouts || []; } catch (_e) {}
      renderOverview(status, providers, loadouts);
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

  function onLeave() { state.activated = false; }

  document.addEventListener('DOMContentLoaded', () => {
    $('forge-refresh-btn')?.addEventListener('click', refresh);
  });

  root.Forge = { activate, onLeave, refresh, _renderOverview: renderOverview };
})();
