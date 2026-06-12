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
    { id: 'benchmark', label: 'Benchmark' },
    { id: 'arena', label: 'Arena' },
    { id: 'loadouts', label: 'Loadouts' },
    { id: 'settings', label: 'Settings' },
    { id: 'advanced', label: 'Advanced' },
  ];

  // Stage modes; the active production-routing ones require explicit acknowledgement.
  const STAGE_MODES = ['disabled', 'shadow_select', 'fallback_only', 'fixed_model', 'auto_select', 'arena_select'];
  const ACTIVE_STAGE_MODES = ['fixed_model', 'auto_select', 'arena_select'];

  const state = {
    activated: false,
    loading: false,
    tab: 'overview',
    data: { status: {}, providers: [], loadouts: [], profiles: [], leaderboard: [], presets: [], settings: {}, openrouterCatalog: null },
    // Benchmark selector state. Depth defaults to 'standard' — full/deep is never forced.
    bench: { presets: [], depth: 'standard', provider: '', model: '', result: null },
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
    if (p.provider_id === 'local_openai_compatible' && p.runtime_health === 'not_probed') {
      return 'Configured, not runtime-ready until an explicit probe succeeds.';
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
      + '<div class="forge-prov-note">Configured: ' + escapeHtml(p.configured_state || 'missing_config')
      + ' · Runtime: ' + escapeHtml(p.runtime_health || 'not_probed')
      + (p.last_probe_at ? ' · Probe: ' + escapeHtml(p.last_probe_at) : '') + '</div>'
      + (note ? '<div class="forge-prov-note">' + escapeHtml(note) + '</div>' : '')
      + (p.provider_id !== 'legacy_atlas'
        ? '<button type="button" class="forge-probe-btn" data-provider-probe="' + escapeHtml(p.provider_id) + '">Probe</button>'
        : '')
      + '</div>'
    );
  }

  // ----- view builders (pure: data -> HTML string) -----

  function overviewHtml(data) {
    const status = data.status || {};
    const forgeState = status.forge_enabled ? 'On' : 'Off (legacy primary)';
    const active = (data.loadouts || []).find((l) => l.active)
      || (data.loadouts || []).find((l) => l.builtin) || (data.loadouts || [])[0] || null;
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

  // ----- Benchmark selector (PFG-23) -----

  const DEPTHS = ['quick', 'standard', 'deep'];

  function selectedProvider(data) {
    return (data.providers || []).find((p) => p.provider_id === state.bench.provider) || null;
  }

  function primaryPresets(presets) {
    return (presets || []).filter((p) => p.primary_rank !== null && p.primary_rank !== undefined)
      .sort((a, b) => Number(a.primary_rank) - Number(b.primary_rank));
  }

  function benchmarkHtml(data) {
    const presets = data.presets || [];
    const sel = state.bench;
    const primaries = primaryPresets(presets);
    const primaryIds = primaries.map((p) => p.preset_id);
    const others = presets.filter((p) => primaryIds.indexOf(p.preset_id) < 0);
    const checkbox = (p) => (
      '<label class="forge-check"><input type="checkbox" data-bench-preset="' + escapeHtml(p.preset_id) + '"'
      + (sel.presets.indexOf(p.preset_id) >= 0 ? ' checked' : '') + '>'
      + '<span>' + escapeHtml(p.display_name || p.preset_id) + '</span></label>'
    );
    const depthBtns = DEPTHS.map((d) => (
      '<button type="button" class="forge-seg' + (sel.depth === d ? ' active' : '')
      + '" data-bench-depth="' + d + '"' + (d === 'standard' ? '' : ' disabled title="unavailable_not_supported"')
      + '>' + escapeHtml(d) + '</button>'
    )).join('');
    const provOpts = ['<option value="">Select provider…</option>'].concat(
      (data.providers || []).map((p) => (
        '<option value="' + escapeHtml(p.provider_id) + '"' + (sel.provider === p.provider_id ? ' selected' : '')
        + '>' + escapeHtml(providerLabel(p.provider_id)) + ' (' + escapeHtml(p.health) + ')</option>'
      ))
    ).join('');
    const prov = selectedProvider(data);
    const catalogModels = prov && prov.provider_id === 'openrouter' && data.openrouterCatalog
      ? (data.openrouterCatalog.models || []) : [];
    const modelSelect = catalogModels.length
      ? '<select class="forge-select" data-bench-model-select><option value="">Catalog model...</option>'
        + catalogModels.map((m) => (
          '<option value="' + escapeHtml(m.model_id) + '"' + (sel.model === m.model_id ? ' selected' : '') + '>'
          + escapeHtml(m.display_name || m.model_id) + '</option>'
        )).join('') + '</select>'
      : '';
    const externalWarning = prov && prov.source_class === 'external_cloud'
      ? '<div class="forge-warn">External provider selected. Source/privacy policy applies; '
        + 'this is blocked under Local Only and may send context to a cloud model.</div>'
      : '';
    const canRun = sel.presets.length > 0 && sel.provider && sel.model;
    const result = sel.result
      ? '<div class="forge-bench-result">' + escapeHtml(sel.result) + '</div>'
      : '';
    return (
      '<div class="forge-card">'
      + '<div class="forge-card-title">Benchmark presets</div>'
      + '<div class="forge-check-grid">' + (primaries.map(checkbox).join('') || '<div class="forge-empty">No presets.</div>') + '</div>'
      + (others.length ? '<details class="forge-more"><summary>More presets</summary><div class="forge-check-grid">'
          + others.map(checkbox).join('') + '</div></details>' : '')
      + '</div>'
      + '<div class="forge-card">'
      + '<div class="forge-card-title">Depth</div>'
      + '<div class="forge-seg-row">' + depthBtns + '</div>'
      + '<div class="forge-hint">Default is standard; full/deep is opt-in.</div>'
      + '</div>'
      + '<div class="forge-card">'
      + '<div class="forge-card-title">Model</div>'
      + '<select class="forge-select" data-bench-provider>' + provOpts + '</select>'
      + modelSelect
      + '<input class="forge-input" data-bench-model placeholder="provider model id" value="' + escapeHtml(sel.model) + '">'
      + externalWarning
      + '<button type="button" class="forge-run-btn" data-bench-run' + (canRun ? '' : ' disabled') + '>Run benchmark</button>'
      + result
      + '</div>'
    );
  }

  function wireBenchmark(content, data) {
    content.querySelectorAll('[data-bench-preset]').forEach((cb) => {
      cb.addEventListener('change', () => {
        const id = cb.getAttribute('data-bench-preset');
        const i = state.bench.presets.indexOf(id);
        if (cb.checked && i < 0) state.bench.presets.push(id);
        else if (!cb.checked && i >= 0) state.bench.presets.splice(i, 1);
        renderActive();
      });
    });
    content.querySelectorAll('[data-bench-depth]').forEach((btn) => {
      btn.addEventListener('click', () => { state.bench.depth = btn.getAttribute('data-bench-depth'); renderActive(); });
    });
    content.querySelector('[data-bench-provider]')?.addEventListener('change', (e) => {
      state.bench.provider = e.target.value; renderActive();
    });
    content.querySelector('[data-bench-model-select]')?.addEventListener('change', (e) => {
      state.bench.model = e.target.value; renderActive();
    });
    content.querySelector('[data-bench-model]')?.addEventListener('input', (e) => {
      state.bench.model = e.target.value;
      const btn = content.querySelector('[data-bench-run]');
      if (btn) btn.disabled = !(state.bench.presets.length && state.bench.provider && state.bench.model);
    });
    content.querySelector('[data-bench-run]')?.addEventListener('click', () => runBenchmark(data));
  }

  async function runBenchmark(data) {
    const sel = state.bench;
    const preset = (data.presets || []).find((p) => p.preset_id === sel.presets[0]);
    const route = (preset && preset.recommended_routes && preset.recommended_routes[0]) || 'direct_patch';
    const stage = 'patch_generation';
    setStatus('Running benchmark…');
    try {
      const record = await api('/arena/run', {
        method: 'POST',
        body: JSON.stringify({
          stage,
          specs: [{ provider_id: sel.provider, model_id: sel.model, route_id: route }],
          preset_id: sel.presets[0],
          preset_ids: sel.presets.slice(),
          depth: sel.depth,
        }),
      });
      const cand = (record.candidates || [])[0] || {};
      sel.result = 'Arena run ' + record.arena_run_id + ' — candidate ' + (cand.adoption_state || 'not_applied')
        + ' (Safe Apply required before any adoption). See the Arena tab for candidates.';
      // Fetch the enriched run (per-candidate metadata) for the Arena tab.
      try { state.data.arena = await api('/arena/runs/' + record.arena_run_id); }
      catch (_e) { state.data.arena = record; }
      setStatus('Benchmark recorded (no model adopted)', 'ok');
    } catch (err) {
      sel.result = 'Run failed: ' + (err && err.message ? err.message : 'error');
      setStatus('Benchmark run failed', 'error');
    }
    renderActive();
  }

  // ----- Arena (PFG-24) -----

  function winnerCandidateId(record) {
    // Honest, mechanical winner: among contract-valid candidates, the lowest latency.
    // No winner is declared if none ran a valid contract.
    let best = null;
    (record.candidates || []).forEach((c) => {
      const r = c.result || {};
      if (!r.contract_valid) return;
      if (best === null || (r.latency_ms || 0) < (best.result.latency_ms || 0)) best = c;
    });
    return best ? best.candidate_id : '';
  }

  function adoptionLabel(stateValue) {
    const v = String(stateValue || 'not_applied');
    return v === 'not_applied' ? 'Not applied' : v.replace(/_/g, ' ');
  }

  function candidateRow(c, isWinner) {
    const r = c.result || {};
    const score = c.evaluator_score || {};
    const blocked = c.blocked_reasons || [];
    const draft = c.proposal_draft || {};
    const created = draft.status && draft.status !== 'not_created';
    const eligible = c.eligible_for_proposal === true && !created;
    const btnLabel = created ? 'Proposal draft created' : 'Create Proposal draft';
    const btnTitle = created
      ? 'Proposal draft already exists'
      : (eligible ? 'Creates an approval-required Proposal draft'
        : ('Blocked: ' + (blocked.join('; ') || 'candidate is not eligible')));
    const contract = r.contract_valid
      ? '<span class="forge-badge forge-badge-ready">contract ok</span>'
      : '<span class="forge-badge forge-badge-error">contract fail</span>';
    const latency = r.latency_ms ? (r.latency_ms + ' ms') : '—';
    const reasonHtml = blocked.length
      ? '<div class="forge-cand-blocked">Blocked: ' + escapeHtml(blocked.join('; ')) + '</div>'
      : '<div class="forge-cand-blocked forge-cand-ok">Proposal handoff eligible; approval required.</div>';
    return (
      '<div class="forge-cand-row' + (isWinner ? ' is-winner' : '') + '">'
      + '<div class="forge-cand-main">'
      + (isWinner ? '<span class="forge-cand-win">★ winner</span>' : '')
      + '<span class="forge-cand-model">' + escapeHtml(c.model_id) + '</span>'
      + '<span class="forge-cand-route">' + escapeHtml(c.route_id) + '</span>'
      + '</div>'
      + '<div class="forge-cand-metrics">'
      + contract
      + '<span class="forge-cand-metric">lat ' + escapeHtml(latency) + '</span>'
      + '<span class="forge-cand-metric">score ' + escapeHtml(String(score.final_score ?? '—')) + '</span>'
      + '<span class="forge-cand-metric">risk ' + escapeHtml(c.risk_level || 'medium') + '</span>'
      + '<span class="forge-cand-adopt">' + escapeHtml(adoptionLabel(c.adoption_state)) + '</span>'
      + '</div>'
      + reasonHtml
      + '<div class="forge-cand-actions">'
      + '<button type="button" class="forge-adopt-btn" data-candidate-proposal="'
      + escapeHtml(c.candidate_id) + '"' + (eligible ? '' : ' disabled')
      + ' title="' + escapeHtml(btnTitle) + '">' + escapeHtml(btnLabel) + '</button>'
      + '<span class="forge-cand-metric">approval required; requires Safe Apply</span>'
      + '</div>'
      + '</div>'
    );
  }

  function arenaHtml(data) {
    const record = data.arena;
    if (!record || !(record.candidates || []).length) {
      return (
        '<div class="forge-card">'
        + '<div class="forge-card-title">Arena</div>'
        + '<div class="forge-empty">No Arena run yet. Run a Benchmark to compare model × '
        + 'route candidates side by side. Candidates are never applied automatically.</div>'
        + '</div>'
      );
    }
    const winner = winnerCandidateId(record);
    const rows = record.candidates.map((c) => candidateRow(c, c.candidate_id === winner)).join('');
    return (
      '<div class="forge-card">'
      + '<div class="forge-card-title">Arena run ' + escapeHtml(record.arena_run_id) + '</div>'
      + '<div class="forge-cand-list">' + rows + '</div>'
      + '</div>'
      + '<div class="forge-card forge-adopt-card">'
      + '<div class="forge-card-title">Adoption</div>'
      + '<div class="forge-adopt-note">Arena candidates are never applied directly. To adopt a '
      + 'candidate it must go through Proposal → Safe Apply → Verification (and Portal when '
      + 'runnable). There is no direct apply here.</div>'
      + '</div>'
    );
  }

  async function createProposalDraft(candidateId) {
    if (!candidateId) return;
    setStatus('Creating Proposal draft...');
    try {
      const result = await api('/arena/candidates/' + encodeURIComponent(candidateId) + '/proposal-draft', {
        method: 'POST',
        body: '{}',
      });
      if (result.status !== 'created') {
        setStatus('Proposal draft blocked: ' + ((result.blocked_reasons || []).join('; ') || 'not eligible'), 'error');
      } else {
        setStatus('Proposal draft created; approval required before Safe Apply', 'ok');
      }
      if (result.arena_run_id) state.data.arena = await api('/arena/runs/' + result.arena_run_id);
    } catch (err) {
      setStatus('Proposal draft failed: ' + (err && err.message ? err.message : 'error'), 'error');
    }
    renderActive();
  }

  // ----- Advanced: Stage Matrix and Route Matrix (PFG-25) -----

  function stageRow(entry) {
    const active = ACTIVE_STAGE_MODES.indexOf(entry.mode) >= 0;
    const opts = STAGE_MODES.map((m) => (
      '<option value="' + m + '"' + (entry.mode === m ? ' selected' : '') + '>' + m + '</option>'
    )).join('');
    const model = entry.fixed_model_id ? escapeHtml(entry.fixed_model_id) : '—';
    const warn = active
      ? '<span class="forge-warn-pill" title="Changes live routing">routes live</span>' : '';
    return (
      '<div class="forge-matrix-row">'
      + '<span class="forge-matrix-key">' + escapeHtml(entry.stage) + '</span>'
      + '<select class="forge-select forge-matrix-select" data-stage="' + escapeHtml(entry.stage) + '">' + opts + '</select>'
      + '<span class="forge-matrix-model">' + model + '</span>'
      + warn
      + '<span class="forge-matrix-reason">' + escapeHtml(entry.reason || '') + '</span>'
      + '</div>'
    );
  }

  function routeRow(entry) {
    const routes = (entry.candidate_routes || []).join(', ');
    const crit = entry.critical_gate_required
      ? '<span class="forge-warn-pill" title="Unsafe change class">critical gate</span>' : '';
    const pref = entry.preferred_route_override
      ? ' · default ' + escapeHtml(entry.preferred_route_override) : '';
    return (
      '<div class="forge-matrix-row">'
      + '<span class="forge-matrix-key">' + escapeHtml(entry.change_class) + '</span>'
      + '<span class="forge-matrix-routes">' + escapeHtml(routes) + escapeHtml(pref) + '</span>'
      + crit
      + '</div>'
    );
  }

  function advancedHtml(data) {
    const stagePolicy = data.stagePolicy || [];
    const routePolicy = data.routePolicy || [];
    const stageRows = stagePolicy.map(stageRow).join('') || '<div class="forge-empty">No stage policy.</div>';
    const routeRows = routePolicy.map(routeRow).join('') || '<div class="forge-empty">No route policy.</div>';
    // Collapsed by default — advanced controls do not clutter normal use.
    return (
      '<div class="forge-hint">Advanced controls. Changing a stage to a live-routing mode '
      + '(fixed/auto/arena) asks for confirmation; nothing here cuts over automatically.</div>'
      + '<details class="forge-adv"><summary>Stage Matrix</summary>'
      + '<div class="forge-matrix">' + stageRows + '</div></details>'
      + '<details class="forge-adv"><summary>Route Matrix</summary>'
      + '<div class="forge-matrix">' + routeRows + '</div></details>'
    );
  }

  function wireAdvanced(content) {
    content.querySelectorAll('[data-stage]').forEach((sel) => {
      sel.addEventListener('change', () => changeStageMode(sel.getAttribute('data-stage'), sel.value));
    });
  }

  async function changeStageMode(stage, mode) {
    const active = ACTIVE_STAGE_MODES.indexOf(mode) >= 0;
    if (active) {
      const ok = (typeof confirm === 'function')
        ? confirm('Stage "' + stage + '" → ' + mode + ' changes live production routing. Continue?')
        : false;
      if (!ok) { renderActive(); return; }
    }
    try {
      await api('/stage-policy', {
        method: 'POST',
        body: JSON.stringify({ stage, mode, allow_production_routing: active, reason: 'ui_advanced' }),
      });
      setStatus('Stage policy updated: ' + stage + ' → ' + mode, 'ok');
      try { state.data.stagePolicy = (await api('/stage-policy')).stage_policy || []; } catch (_e) {}
    } catch (err) {
      setStatus('Stage policy change refused: ' + (err && err.message ? err.message : 'error'), 'error');
    }
    renderActive();
  }

  // ----- Loadouts (PFG-26) -----

  function loadoutCard(lo) {
    const risky = !!lo.risky;
    const active = !!lo.active;
    return (
      '<div class="forge-loadout' + (active ? ' is-active' : '') + '">'
      + '<div class="forge-loadout-head">'
      + '<span class="forge-loadout-name">' + escapeHtml(lo.display_name || lo.loadout_id) + '</span>'
      + (active ? '<span class="forge-loadout-active">active</span>' : '')
      + (risky ? '<span class="forge-warn-pill" title="Changes source/routing">risky</span>' : '')
      + '</div>'
      + '<div class="forge-loadout-desc">' + escapeHtml(lo.description || '') + '</div>'
      + '<div class="forge-loadout-meta">' + escapeHtml(lo.source_mode || '')
      + ((lo.provider_preferences || []).length ? ' · ' + escapeHtml((lo.provider_preferences || []).join(', ')) : '')
      + '</div>'
      + '<button type="button" class="forge-loadout-btn" data-loadout="' + escapeHtml(lo.loadout_id) + '"'
      + ' data-risky="' + (risky ? '1' : '0') + '"' + (active ? ' disabled' : '') + '>'
      + (active ? 'Applied' : 'Apply') + '</button>'
      + '</div>'
    );
  }

  function loadoutsHtml(data) {
    const loadouts = data.loadouts || [];
    const cards = loadouts.map(loadoutCard).join('');
    return (
      '<div class="forge-hint">Loadouts are simple presets. Applying one updates stage and '
      + 'provider policy. A risky loadout (external models or live routing) asks for '
      + 'confirmation first.</div>'
      + '<div class="forge-loadout-grid">'
      + (cards || '<div class="forge-empty">No loadouts.</div>')
      + '</div>'
    );
  }

  function wireLoadouts(content) {
    content.querySelectorAll('[data-loadout]').forEach((btn) => {
      btn.addEventListener('click', () => applyLoadout(btn.getAttribute('data-loadout'), btn.getAttribute('data-risky') === '1'));
    });
  }

  async function applyLoadout(loadoutId, risky) {
    if (risky) {
      const ok = (typeof confirm === 'function')
        ? confirm('Loadout "' + loadoutId + '" uses external models or live routing. Apply it?')
        : false;
      if (!ok) return;
    }
    setStatus('Applying loadout…');
    try {
      await api('/loadouts/' + encodeURIComponent(loadoutId) + '/apply', {
        method: 'POST',
        body: JSON.stringify({ acknowledge_risky: !!risky }),
      });
      setStatus('Loadout applied: ' + loadoutId, 'ok');
      try { state.data.loadouts = (await api('/loadouts')).loadouts || []; } catch (_e) {}
      try { state.data.stagePolicy = (await api('/stage-policy')).stage_policy || []; } catch (_e) {}
    } catch (err) {
      setStatus('Loadout apply refused: ' + (err && err.message ? err.message : 'error'), 'error');
    }
    renderActive();
  }

  // ----- Settings (PFH-2) -----

  function settingsHtml(data) {
    const settings = data.settings || {};
    const local = settings.local_provider || {};
    const openrouter = settings.openrouter || {};
    const catalog = data.openrouterCatalog || {};
    return (
      '<div class="forge-card">'
      + '<div class="forge-card-title">Local Provider</div>'
      + '<label class="forge-label">Base URL<input class="forge-input" data-setting-local-base value="' + escapeHtml(local.base_url || '') + '"></label>'
      + '<label class="forge-label">Model ID<input class="forge-input" data-setting-local-model value="' + escapeHtml(local.model_id || '') + '"></label>'
      + '<label class="forge-label">LLM folder<input class="forge-input" data-setting-local-dir value="' + escapeHtml(local.model_storage_dir || '') + '"></label>'
      + '</div>'
      + '<div class="forge-card">'
      + '<div class="forge-card-title">OpenRouter</div>'
      + '<label class="forge-check"><input type="checkbox" data-setting-openrouter-enabled' + (openrouter.enabled ? ' checked' : '') + '><span>Enabled</span></label>'
      + '<label class="forge-label">API key env<input class="forge-input" data-setting-openrouter-env value="' + escapeHtml(openrouter.api_key_env || 'OPENROUTER_API_KEY') + '"></label>'
      + '<label class="forge-label">Base URL<input class="forge-input" data-setting-openrouter-base value="' + escapeHtml(openrouter.base_url || 'https://openrouter.ai/api/v1') + '"></label>'
      + '<div class="forge-kv"><span>Credential</span><b>' + escapeHtml(openrouter.credential_configured ? 'configured' : 'missing') + '</b></div>'
      + '<div class="forge-kv"><span>Catalog</span><b>' + escapeHtml(catalog.status || 'disabled') + '</b></div>'
      + '<button type="button" class="forge-run-btn" data-settings-save>Save settings</button>'
      + '</div>'
    );
  }

  function wireSettings(content) {
    content.querySelector('[data-settings-save]')?.addEventListener('click', () => saveSettings(content));
  }

  async function saveSettings(content) {
    const payload = {
      local_provider: {
        base_url: content.querySelector('[data-setting-local-base]')?.value || '',
        model_id: content.querySelector('[data-setting-local-model]')?.value || '',
        model_storage_dir: content.querySelector('[data-setting-local-dir]')?.value || '',
      },
      openrouter: {
        enabled: !!content.querySelector('[data-setting-openrouter-enabled]')?.checked,
        api_key_env: content.querySelector('[data-setting-openrouter-env]')?.value || 'OPENROUTER_API_KEY',
        base_url: content.querySelector('[data-setting-openrouter-base]')?.value || 'https://openrouter.ai/api/v1',
      },
    };
    try {
      state.data.settings = (await api('/settings', { method: 'POST', body: JSON.stringify(payload) })).settings || {};
      setStatus('Forge settings saved', 'ok');
      try { state.data.openrouterCatalog = await api('/providers/openrouter/catalog'); } catch (_e) {}
    } catch (err) {
      setStatus('Settings save refused: ' + (err && err.message ? err.message : 'error'), 'error');
    }
    renderActive();
  }

  const VIEWS = {
    overview: overviewHtml, skills: skillsHtml, benchmark: benchmarkHtml,
    arena: arenaHtml, loadouts: loadoutsHtml, settings: settingsHtml, advanced: advancedHtml,
  };

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
    } else if (state.tab === 'overview') {
      content.querySelectorAll('[data-provider-probe]').forEach((btn) => {
        btn.addEventListener('click', () => probeProvider(btn.getAttribute('data-provider-probe')));
      });
    } else if (state.tab === 'benchmark') {
      wireBenchmark(content, state.data);
    } else if (state.tab === 'arena') {
      content.querySelectorAll('[data-candidate-proposal]').forEach((btn) => {
        btn.addEventListener('click', () => createProposalDraft(btn.getAttribute('data-candidate-proposal')));
      });
    } else if (state.tab === 'advanced') {
      wireAdvanced(content);
    } else if (state.tab === 'loadouts') {
      wireLoadouts(content);
    } else if (state.tab === 'settings') {
      wireSettings(content);
    }
  }

  function setTab(tab) {
    state.tab = tab;
    renderShell();
  }

  async function probeProvider(providerId) {
    if (!providerId) return;
    setStatus('Probing provider...');
    try {
      await api('/providers/' + encodeURIComponent(providerId) + '/probe', { method: 'POST', body: '{}' });
      state.data.providers = (await api('/providers')).providers || [];
      setStatus('Provider probe recorded: ' + providerId, 'ok');
    } catch (err) {
      setStatus('Provider probe failed: ' + (err && err.message ? err.message : 'error'), 'error');
    }
    renderActive();
  }

  async function refresh() {
    if (state.loading) return;
    state.loading = true;
    setStatus('Loading…');
    try {
      const status = await api('/status');
      const data = { status, providers: [], loadouts: [], profiles: [], leaderboard: [], settings: {}, openrouterCatalog: null };
      try { data.providers = (await api('/providers')).providers || []; } catch (_e) {}
      try { data.settings = (await api('/settings')).settings || {}; } catch (_e) {}
      try { data.openrouterCatalog = await api('/providers/openrouter/catalog'); } catch (_e) {}
      try { data.loadouts = (await api('/loadouts')).loadouts || []; } catch (_e) {}
      try { data.profiles = (await api('/profiles')).profiles || []; } catch (_e) {}
      try { data.leaderboard = (await api('/leaderboard')).leaderboard || []; } catch (_e) {}
      try { data.presets = (await api('/presets')).presets || []; } catch (_e) {}
      try { data.stagePolicy = (await api('/stage-policy')).stage_policy || []; } catch (_e) {}
      try { data.routePolicy = (await api('/route-policy')).route_policy || []; } catch (_e) {}
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
    _benchmarkHtml: benchmarkHtml,
    _arenaHtml: arenaHtml,
    _advancedHtml: advancedHtml,
    _loadoutsHtml: loadoutsHtml,
    _settingsHtml: settingsHtml,
    _runBenchmark: runBenchmark,
    _state: state,
  };
})();
