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
    // ctx is the context length for the chosen local/LM-Studio model (persisted to the model
    // registry for Anvil models; used at load time by the runtime manager — see enable/monitor).
    bench: { presets: [], depth: 'standard', provider: '', model: '', ctx: '', result: null },
  };

  // The benchmark "LLM management tool": Anvil surfaces the local model registry (Models DB);
  // LM Studio surfaces a running LM Studio server's models. Both run through the local
  // OpenAI-compatible provider, so they are offered as provider choices alongside the backend ones.
  const LOCAL_RUNTIME_PROVIDERS = [
    { provider_id: 'anvil', label: 'Anvil（ローカルモデル管理）' },
    { provider_id: 'lm_studio', label: 'LM Studio' },
  ];

  function normalizeCtx(value) {
    const n = parseInt(value, 10);
    return Number.isFinite(n) && n > 0 ? n : '';
  }

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
      // Onboarding help: Forge is read-mostly and never applies a model by itself. The steps below
      // make the intended flow explicit so the tabs are not a mystery on first use.
      '<div class="forge-card forge-help">'
      + '<div class="forge-card-title">Forge の使い方</div>'
      + '<div class="forge-hint">Forge はモデルを「比較・評価」するための場です。ここから本番ルーティングを直接書き換えたり、モデルを自動適用したりはしません。</div>'
      + '<ol class="forge-help-steps">'
      + '<li><b>Settings</b>: 使うローカルサーバー（llama.cpp / LM Studio）の Runtime と Base URL・Model ID を設定（OpenRouter を使う場合はここで有効化）。</li>'
      + '<li><b>Benchmark</b>: プリセットと深さ、Provider・Model を選んで実行。結果は記録されますが適用はされません。</li>'
      + '<li><b>Arena</b>: モデル×ルートの候補を横並びで比較。採用は Proposal → Safe Apply → Verification を経由します（直接適用なし）。</li>'
      + '<li><b>Skills</b>: 蓄積されたベンチ結果からモデルごとの強み（チャンピオン/スコア）を確認。</li>'
      + '<li><b>Loadouts</b>: ステージ/プロバイダ方針のプリセット適用。<b>Advanced</b> は本番ルーティング変更（確認あり）。</li>'
      + '</ol>'
      + '</div>'
      + '<div class="forge-card">'
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
    ).concat(
      LOCAL_RUNTIME_PROVIDERS.map((p) => (
        '<option value="' + escapeHtml(p.provider_id) + '"' + (sel.provider === p.provider_id ? ' selected' : '')
        + '>' + escapeHtml(p.label) + '</option>'
      ))
    ).join('');
    const prov = selectedProvider(data);
    const isAnvil = sel.provider === 'anvil';
    const isLmStudio = sel.provider === 'lm_studio';
    let modelSelect = '';
    let modelNote = '';
    let ctxField = '';
    if (isAnvil) {
      // Anvil = the local model registry (Models DB). Each option carries its registered ctx_size;
      // the CTX editor below persists a change back to the registry so model load uses it later.
      const models = data.localModels || [];
      modelSelect = '<select class="forge-select" data-bench-model-select><option value="">登録モデルを選択…</option>'
        + models.map((m) => {
          const id = String(m.model_key || m.name || '');
          const ctx = normalizeCtx(m.ctx_size);
          return '<option value="' + escapeHtml(id) + '"' + (sel.model === id ? ' selected' : '') + '>'
            + escapeHtml(m.name || id) + (ctx ? ' · ctx ' + ctx : '') + '</option>';
        }).join('') + '</select>';
      const selModel = models.find((m) => String(m.model_key || m.name || '') === sel.model);
      const selCtx = sel.ctx || (selModel ? normalizeCtx(selModel.ctx_size) : '');
      ctxField = models.length
        ? '<label class="forge-label">CTX (context length)'
          + '<input class="forge-input" type="number" min="512" step="512" data-bench-ctx value="' + escapeHtml(String(selCtx || '')) + '"></label>'
          + (selModel ? '<button type="button" class="forge-seg" data-bench-ctx-save data-model-id="' + escapeHtml(String(selModel.id || '')) + '">CTX を登録に保存</button>' : '')
        : '<div class="forge-empty">登録モデルがありません。Models タブでスキャン/追加してください。</div>';
    } else if (isLmStudio) {
      const lmCatalog = data.lmStudioCatalog || {};
      const lm = lmCatalog.models || [];
      modelSelect = '<select class="forge-select" data-bench-model-select><option value="">LM Studio モデルを選択…</option>'
        + lm.map((m) => (
          '<option value="' + escapeHtml(m.model_id) + '"' + (sel.model === m.model_id ? ' selected' : '') + '>'
          + escapeHtml(m.model_id) + '</option>'
        )).join('') + '</select>';
      ctxField = '<label class="forge-label">CTX (context length)'
        + '<input class="forge-input" type="number" min="512" step="512" data-bench-ctx value="' + escapeHtml(String(sel.ctx || '')) + '"></label>';
      const st = String(lmCatalog.status || '');
      if (st && st !== 'ready') {
        modelNote = '<div class="forge-hint">LM Studio に接続できません（' + escapeHtml(st) + '）。Settings の Base URL（既定 :1234）と起動状態を確認してください。モデルの自動ロードは後日対応です。</div>';
      }
    } else if (prov && prov.provider_id === 'openrouter' && data.openrouterCatalog) {
      const catalogModels = data.openrouterCatalog.models || [];
      modelSelect = catalogModels.length
        ? '<select class="forge-select" data-bench-model-select><option value="">Catalog model...</option>'
          + catalogModels.map((m) => (
            '<option value="' + escapeHtml(m.model_id) + '"' + (sel.model === m.model_id ? ' selected' : '') + '>'
            + escapeHtml(m.display_name || m.model_id) + '</option>'
          )).join('') + '</select>'
        : '';
    }
    // Free-text model id stays for backend providers that have no dropdown; the managed-runtime
    // dropdowns (Anvil / LM Studio) are authoritative, so the free input is hidden for them.
    const freeTextModel = (isAnvil || isLmStudio)
      ? ''
      : '<input class="forge-input" data-bench-model placeholder="provider model id" value="' + escapeHtml(sel.model) + '">';
    // Runtime management (the "Forge management feature"): when enabled in Settings, expose a Load
    // action for the selected local model. llama-server gets a real load (POST /model/switch) with
    // live status monitoring; LM Studio auto-load is deferred and says so rather than faking it.
    const mgmtEnabled = !!(data.settings && data.settings.runtime_management && data.settings.runtime_management.enabled);
    let runtimeLoadBlock = '';
    if (mgmtEnabled && (isAnvil || isLmStudio)) {
      if (isLmStudio) {
        runtimeLoadBlock = '<div class="forge-hint">LM Studio のモデル自動ロードは後日対応です。現時点では LM Studio 側で対象モデルを手動ロードしてください。</div>';
      } else {
        const rs = data.runtimeStatus || {};
        const statusLine = rs.status
          ? '<div class="forge-kv"><span>Load status</span><b>' + escapeHtml(String(rs.status))
            + (rs.current_key ? ' · ' + escapeHtml(String(rs.current_key)) : '') + '</b></div>'
          : '';
        runtimeLoadBlock = '<button type="button" class="forge-seg" data-bench-load'
          + (sel.model ? '' : ' disabled') + '>選択モデルをロード</button>' + statusLine;
      }
    }
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
      + freeTextModel
      + ctxField
      + modelNote
      + runtimeLoadBlock
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
      state.bench.provider = e.target.value;
      // Switching provider clears the model/ctx selection so a stale id from another runtime is
      // never submitted. Selecting LM Studio pulls its live model list (server-side proxy).
      state.bench.model = '';
      state.bench.ctx = '';
      if (e.target.value === 'lm_studio') { loadLmStudioCatalog(); return; }
      renderActive();
    });
    content.querySelector('[data-bench-model-select]')?.addEventListener('change', (e) => {
      state.bench.model = e.target.value;
      state.bench.ctx = '';  // re-derive ctx from the newly selected model's registered value
      renderActive();
    });
    content.querySelector('[data-bench-model]')?.addEventListener('input', (e) => {
      state.bench.model = e.target.value;
      const btn = content.querySelector('[data-bench-run]');
      if (btn) btn.disabled = !(state.bench.presets.length && state.bench.provider && state.bench.model);
    });
    content.querySelector('[data-bench-ctx]')?.addEventListener('input', (e) => {
      state.bench.ctx = e.target.value;
    });
    content.querySelector('[data-bench-ctx-save]')?.addEventListener('click', (e) => {
      saveAnvilModelCtx(e.target.getAttribute('data-model-id'), state.bench.ctx);
    });
    content.querySelector('[data-bench-load]')?.addEventListener('click', () => loadSelectedModel());
    content.querySelector('[data-bench-run]')?.addEventListener('click', () => runBenchmark(data));
  }

  // Ask the local runtime (llama-server) to load the selected registry model, then watch the load
  // through to ready/error. Only reachable when runtime management is enabled. Reuses the core app's
  // existing /model/switch (async ensure_model) and /model/status (loading state) endpoints.
  async function loadSelectedModel() {
    const sel = state.bench;
    if (!sel.model) { setStatus('モデルが未選択です', 'error'); return; }
    setStatus('モデルをロード中…');
    try {
      const resp = await fetch('/model/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: sel.model }),
      });
      if (!resp.ok) {
        let detail = String(resp.status);
        try { detail = (await resp.json()).detail || detail; } catch (_e) {}
        throw new Error(detail);
      }
      setStatus('ロードを開始しました。状態を監視します…', 'ok');
      pollModelStatus();
    } catch (err) {
      setStatus('ロード開始に失敗: ' + (err && err.message ? err.message : 'error'), 'error');
    }
  }

  let _modelPollTimer = null;
  async function pollModelStatus() {
    if (_modelPollTimer) { clearTimeout(_modelPollTimer); _modelPollTimer = null; }
    let ticks = 0;
    const tick = async () => {
      ticks += 1;
      try {
        const r = await fetch('/model/status');
        const s = r.ok ? await r.json() : {};
        state.data.runtimeStatus = { status: String(s.status || ''), current_key: String(s.current_key || '') };
        if (state.tab === 'benchmark') renderActive();
        const st = String(s.status || '');
        // Stop on a terminal state or after ~2 minutes so the poll never runs forever.
        if (st === 'ready' || st === 'error' || st === 'unavailable' || ticks > 60) return;
      } catch (_e) {}
      _modelPollTimer = setTimeout(tick, 2000);
    };
    tick();
  }

  // Persist an edited context length back to the Models DB registry entry (Anvil). The runtime
  // manager uses model_db.ctx_size when it loads the model, so this is the authoritative CTX.
  async function saveAnvilModelCtx(modelId, ctx) {
    const ctxNum = normalizeCtx(ctx);
    if (!modelId || !ctxNum) { setStatus('CTX を保存できません（モデル未選択または無効な値）', 'error'); return; }
    setStatus('CTX を保存中…');
    try {
      const resp = await fetch('/models/db/' + encodeURIComponent(modelId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ctx_size: ctxNum }),
      });
      if (!resp.ok) throw new Error(String(resp.status));
      await loadLocalModels();
      setStatus('CTX を登録に保存しました: ' + ctxNum, 'ok');
    } catch (err) {
      setStatus('CTX 保存に失敗: ' + (err && err.message ? err.message : 'error'), 'error');
    }
    renderActive();
  }

  // Anvil model registry (Models DB). Same-origin endpoint owned by the core app.
  async function loadLocalModels() {
    try {
      const resp = await fetch('/models/db');
      const data = resp.ok ? await resp.json() : {};
      state.data.localModels = data.models || [];
    } catch (_e) { state.data.localModels = state.data.localModels || []; }
  }

  // LM Studio (or any local OpenAI-compatible server) model list via the Forge server-side proxy.
  async function loadLmStudioCatalog() {
    try {
      state.data.lmStudioCatalog = await api('/local-catalog?runtime_kind=lm_studio');
    } catch (err) {
      state.data.lmStudioCatalog = { status: 'error', models: [] };
    }
    renderActive();
  }

  async function runBenchmark(data) {
    const sel = state.bench;
    const preset = (data.presets || []).find((p) => p.preset_id === sel.presets[0]);
    const route = (preset && preset.recommended_routes && preset.recommended_routes[0]) || 'direct_patch';
    const stage = 'patch_generation';
    // Anvil and LM Studio both execute through the local OpenAI-compatible provider; map the
    // UI-level runtime choice to that real provider id for the arena run.
    const runtimeProviderId = (sel.provider === 'anvil' || sel.provider === 'lm_studio')
      ? 'local_openai_compatible' : sel.provider;
    setStatus('Running benchmark…');
    try {
      const record = await api('/arena/run', {
        method: 'POST',
        body: JSON.stringify({
          stage,
          specs: [{ provider_id: runtimeProviderId, model_id: sel.model, route_id: route }],
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
    const runtimeKind = String(local.runtime_kind || 'llama_cpp');
    const runtimeMgmt = settings.runtime_management || {};
    const runtimeOpt = (value, label) => (
      '<option value="' + value + '"' + (runtimeKind === value ? ' selected' : '') + '>' + escapeHtml(label) + '</option>'
    );
    return (
      // Runtime management toggle: this is where the "Forge management feature" is turned on/off.
      // When on, the benchmark Model card exposes a Load action that drives the local runtime
      // (llama-server loads the selected model). LM Studio auto-load is deferred (stated below).
      '<div class="forge-card">'
      + '<div class="forge-card-title">ランタイム管理（モデルロード）</div>'
      + '<label class="forge-check"><input type="checkbox" data-setting-runtime-mgmt-enabled' + (runtimeMgmt.enabled ? ' checked' : '') + '><span>有効化（選択モデルのロード操作を許可）</span></label>'
      + '<div class="forge-hint">有効化すると Benchmark の Anvil で選択したモデルを llama-server にロードでき、ロード中/完了を監視します。無効時は既にロード済みのモデルでベンチマークします。LM Studio のモデル自動ロードは後日対応です。</div>'
      + '<button type="button" class="forge-run-btn" data-settings-save>Save settings</button>'
      + '</div>'
      + '<div class="forge-card">'
      + '<div class="forge-card-title">Local Provider</div>'
      // Runtime kind: both llama.cpp and LM Studio expose an OpenAI-compatible /v1 API, so either can
      // be benchmarked from Forge. runtime_kind records which one so later model-load automation can
      // pick the right path (and so the Base URL preset matches the usual port).
      + '<label class="forge-label">Runtime'
      + '<select class="forge-select" data-setting-local-runtime>'
      + runtimeOpt('llama_cpp', 'llama.cpp (llama-server :8080)')
      + runtimeOpt('lm_studio', 'LM Studio (:1234)')
      + '</select></label>'
      + '<label class="forge-label">Base URL<input class="forge-input" data-setting-local-base value="' + escapeHtml(local.base_url || '') + '"></label>'
      + '<div class="forge-seg-row">'
      + '<button type="button" class="forge-seg" data-local-base-preset="http://127.0.0.1:8080">llama.cpp 8080</button>'
      + '<button type="button" class="forge-seg" data-local-base-preset="http://127.0.0.1:1234">LM Studio 1234</button>'
      + '</div>'
      + '<label class="forge-label">Model ID<input class="forge-input" data-setting-local-model value="' + escapeHtml(local.model_id || '') + '"></label>'
      + '<label class="forge-label">LLM folder<input class="forge-input" data-setting-local-dir value="' + escapeHtml(local.model_storage_dir || '') + '"></label>'
      + '<div class="forge-hint">llama.cpp はポート8080で起動中のサーバーをそのまま利用できます。LM Studio は OpenAI 互換サーバー（既定:1234）を有効化すればベンチマークで選択可能です。'
      + '<br><b>注意:</b> LM Studio の「モデル自動ロード」は現在ロードが動作しないため未対応です（後日対応予定）。それまでは LM Studio 側で対象モデルを手動ロードしてからご利用ください。</div>'
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
    // Base URL quick-fill presets. Selecting a runtime also nudges the matching default port so the
    // two stay consistent without forcing it (an explicit URL the user typed is never overwritten on save).
    content.querySelectorAll('[data-local-base-preset]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const input = content.querySelector('[data-setting-local-base]');
        if (input) input.value = btn.getAttribute('data-local-base-preset') || '';
      });
    });
    content.querySelector('[data-setting-local-runtime]')?.addEventListener('change', (e) => {
      const input = content.querySelector('[data-setting-local-base]');
      if (input && !String(input.value || '').trim()) {
        input.value = e.target.value === 'lm_studio' ? 'http://127.0.0.1:1234' : 'http://127.0.0.1:8080';
      }
    });
  }

  async function saveSettings(content) {
    const payload = {
      local_provider: {
        base_url: content.querySelector('[data-setting-local-base]')?.value || '',
        model_id: content.querySelector('[data-setting-local-model]')?.value || '',
        model_storage_dir: content.querySelector('[data-setting-local-dir]')?.value || '',
        runtime_kind: content.querySelector('[data-setting-local-runtime]')?.value || 'llama_cpp',
      },
      openrouter: {
        enabled: !!content.querySelector('[data-setting-openrouter-enabled]')?.checked,
        api_key_env: content.querySelector('[data-setting-openrouter-env]')?.value || 'OPENROUTER_API_KEY',
        base_url: content.querySelector('[data-setting-openrouter-base]')?.value || 'https://openrouter.ai/api/v1',
      },
      runtime_management: {
        enabled: !!content.querySelector('[data-setting-runtime-mgmt-enabled]')?.checked,
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
      const data = { status, providers: [], loadouts: [], profiles: [], leaderboard: [], settings: {}, openrouterCatalog: null, localModels: [], lmStudioCatalog: null };
      // Anvil (local model registry) is the core app's Models DB, not a /api/forge endpoint.
      try { data.localModels = ((await (await fetch('/models/db')).json()).models) || []; } catch (_e) {}
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
