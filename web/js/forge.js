/*
 * Forge mode (PFG-20) — top-level Model Forge shell.
 *
 * Read-only shell that calls the /api/forge backend. The default view is deliberately
 * simple (Forge state + provider health). Overview/Provider cards, Skill Radar,
 * Leaderboard, Benchmark, Arena, Stage/Route matrices, and Loadouts are layered on in
 * PFG-21..PFG-26. Forge never executes a model from here and never changes production
 * routing; it only reflects backend state.
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

  function renderOverview(status, providers) {
    const body = $('forge-body');
    if (!body) return;
    const forgeState = status.forge_enabled ? 'On' : 'Off (legacy primary)';
    const rows = (providers || []).map((p) => (
      '<div class="forge-prov-row">'
      + '<span class="forge-prov-id">' + escapeHtml(p.provider_id) + '</span>'
      + '<span class="forge-prov-class">' + escapeHtml(p.source_class || '') + '</span>'
      + healthBadge(p.health)
      + '</div>'
    )).join('');
    body.innerHTML = (
      '<div class="forge-card">'
      + '<div class="forge-card-title">Overview</div>'
      + '<div class="forge-kv"><span>Forge</span><b>' + escapeHtml(forgeState) + '</b></div>'
      + '<div class="forge-kv"><span>Source mode</span><b>' + escapeHtml(status.source_mode || '') + '</b></div>'
      + '<div class="forge-kv"><span>Profiles</span><b>' + escapeHtml(String(status.profile_count || 0)) + '</b></div>'
      + '</div>'
      + '<div class="forge-card">'
      + '<div class="forge-card-title">Providers</div>'
      + (rows || '<div class="forge-empty">No providers registered.</div>')
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
      try { providers = (await api('/providers')).providers || []; } catch (_e) {}
      renderOverview(status, providers);
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
