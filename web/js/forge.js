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
    tab: 'benchmark',
    data: { status: {}, providers: [], loadouts: [], profiles: [], leaderboard: [], presets: [], settings: {}, openrouterCatalog: null },
    // Benchmark selector state. Depth defaults to 'standard' — full/deep is never forced.
    // ctx is the context length for the chosen local/LM-Studio model (persisted to the model
    // registry for Anvil models; used at load time by the runtime manager — see enable/monitor).
    bench: { presets: [], depth: 'standard', provider: '', model: '', ctx: '', result: null, subtab: 'benchmark', injectionSweep: null, injectionObjective: 'min_sufficient', port: '8080', twinResult: null, running: false },
    twinAssist: { cases: [], result: null, subtab: 'evaluation' },
  };

  // The benchmark "LLM management tool": Anvil surfaces the local model registry (Models DB);
  // LM Studio surfaces a running LM Studio server's models. Both run through the local
  // OpenAI-compatible provider, so they are offered as provider choices alongside the backend ones.
  const LOCAL_RUNTIME_PROVIDERS = [
    { provider_id: 'anvil', label: 'Anvil（ローカルモデル管理）' },
    { provider_id: 'local_openai_compatible', label: 'ローカルサーバ（ポート指定）' },
    { provider_id: 'lm_studio', label: 'LM Studio' },
  ];

  function normalizeCtx(value) {
    const n = parseInt(value, 10);
    return Number.isFinite(n) && n > 0 ? n : '';
  }

  // Anvil per-model llama-server launch parameters, mirrored in the Models DB columns.
  // type 'num'  -> datalist combo (choices + free numeric input); '' means 未指定 (-> -1 on save).
  // type 'text' -> datalist combo (choices + free text); '' kept as-is (omitted at launch).
  // type 'tri'  -> <select> 未指定/ON/OFF mapping to ''/1/0 (stored -1/1/0).
  // The runtime manager (main.py _try_start_once) omits any field left 未指定.
  const ANVIL_PARAM_FIELDS = [
    { key: 'ctx_size', label: 'CTX (context length)', type: 'num', opts: [4096, 8192, 16384, 32768, 65536, 131072] },
    { key: 'gpu_layers', label: 'n-gpu-layers', type: 'num', opts: [0, 999] },
    { key: 'n_cpu_moe', label: 'n-cpu-moe', type: 'num', opts: [0, 8, 14, 24, 36] },
    { key: 'threads', label: 'threads', type: 'num', opts: [4, 8, 12, 16, 24] },
    { key: 'parallel', label: 'parallel', type: 'num', opts: [1, 2, 4] },
    { key: 'batch_size', label: 'batch-size', type: 'num', opts: [512, 1024, 2048, 4096] },
    { key: 'ubatch_size', label: 'ubatch-size', type: 'num', opts: [128, 256, 512] },
    { key: 'cache_type_k', label: 'cache-type-k', type: 'text', opts: ['f16', 'q8_0', 'q4_0'] },
    { key: 'cache_type_v', label: 'cache-type-v', type: 'text', opts: ['f16', 'q8_0', 'q4_0'] },
    { key: 'flash_attn', label: 'flash-attn', type: 'tri' },
    { key: 'no_mmap', label: 'no-mmap', type: 'tri' },
    { key: 'jinja', label: 'jinja', type: 'tri' },
    { key: 'reasoning', label: 'reasoning', type: 'text', opts: ['off', 'on', 'auto'] },
    { key: 'spec_type', label: 'spec-type', type: 'text', opts: ['draft-mtp', 'draft-model'] },
    { key: 'spec_draft_n_max', label: 'spec-draft-n-max', type: 'num', opts: [1, 2, 3, 4] },
    { key: 'spec_draft_p_min', label: 'spec-draft-p-min', type: 'num', opts: [0.5, 0.75, 0.9] },
    { key: 'temp', label: 'temp', type: 'num', opts: [0, 0.3, 0.7, 1.0] },
    { key: 'top_p', label: 'top-p', type: 'num', opts: [0.8, 0.9, 0.95, 1.0] },
    { key: 'top_k', label: 'top-k', type: 'num', opts: [0, 20, 40] },
    { key: 'min_p', label: 'min-p', type: 'num', opts: [0, 0.05, 0.1] },
    { key: 'presence_penalty', label: 'presence-penalty', type: 'num', opts: [0, 1.0, 1.5] },
    { key: 'repeat_penalty', label: 'repeat-penalty', type: 'num', opts: [1.0, 1.1] },
  ];

  // Convert a stored Models DB value to the UI input value. Sentinel -1 / null / '' -> '' (未指定).
  function anvilParamToInput(field, raw) {
    if (field.type === 'text') return String(raw == null ? '' : raw);
    // numeric & tri: -1 / null / '' all mean 未指定.
    if (raw == null || raw === '' || Number(raw) === -1) return '';
    return String(raw);
  }

  // Convert UI input values to the PUT payload. '' -> -1 for num/tri, '' kept for text.
  function anvilParamsToPayload(params) {
    const out = {};
    ANVIL_PARAM_FIELDS.forEach((f) => {
      const v = params[f.key];
      if (f.type === 'text') {
        out[f.key] = String(v == null ? '' : v).trim();
      } else if (v === '' || v == null) {
        out[f.key] = -1;
      } else {
        const n = Number(v);
        out[f.key] = Number.isFinite(n) ? n : -1;
      }
    });
    return out;
  }

  // One parameter field for the per-model 詳細設定 drawer. Everything is a <select> pulldown:
  //   tri  -> 未指定/ON/OFF
  //   num/text -> 未指定 + curated choices + "カスタム…" (reveals a free-input box).
  // A stored value that is not among the choices preselects カスタム… with the value filled in,
  // so custom context lengths etc. round-trip through the dropdown UI.
  function anvilConfigFieldHtml(f, rawVal) {
    const val = anvilParamToInput(f, rawVal); // '' (未指定) or the stored value as a string
    if (f.type === 'tri') {
      const opt = (v, lbl) => '<option value="' + v + '"' + (val === v ? ' selected' : '') + '>' + lbl + '</option>';
      return '<label class="forge-label">' + escapeHtml(f.label)
        + '<select class="forge-select" data-anvil-param="' + f.key + '">'
        + opt('', '未指定（既定）') + opt('1', 'ON') + opt('0', 'OFF')
        + '</select></label>';
    }
    const opts = (f.opts || []).map(String);
    const isCustom = val !== '' && opts.indexOf(val) < 0;
    const optionHtml = ['<option value=""' + (val === '' ? ' selected' : '') + '>未指定（既定）</option>']
      .concat(opts.map((o) => '<option value="' + escapeHtml(o) + '"'
        + (!isCustom && val === o ? ' selected' : '') + '>' + escapeHtml(o) + '</option>'))
      .concat(['<option value="__custom__"' + (isCustom ? ' selected' : '') + '>カスタム…</option>'])
      .join('');
    const inputType = f.type === 'num' ? ' inputmode="decimal"' : '';
    const customStyle = isCustom ? '' : ' style="display:none"';
    return '<label class="forge-label">' + escapeHtml(f.label)
      + '<select class="forge-select" data-anvil-param="' + f.key + '">' + optionHtml + '</select>'
      + '<input class="forge-input" data-anvil-custom="' + f.key + '"' + inputType + customStyle
      + ' placeholder="カスタム値" value="' + escapeHtml(isCustom ? val : '') + '">'
      + '</label>';
  }

  // The full per-model parameter form (all llama-server launch params as pulldowns), grouped for
  // scannability. Shown inside the 詳細設定 drawer; also exported for render tests.
  function renderAnvilConfigForm(model) {
    model = model || {};
    const group = (keys) => '<div class="forge-check-grid">' + keys.map((k) => {
      const f = ANVIL_PARAM_FIELDS.find((x) => x.key === k);
      return f ? anvilConfigFieldHtml(f, model[f.key]) : '';
    }).join('') + '</div>';
    return '<div class="forge-anvil-config" data-anvil-config-form>'
      + '<div class="forge-card-title">基本</div>'
      + group(['ctx_size', 'gpu_layers', 'n_cpu_moe', 'threads', 'parallel', 'batch_size', 'ubatch_size',
               'cache_type_k', 'cache_type_v', 'flash_attn', 'no_mmap', 'jinja'])
      + '<div class="forge-card-title" style="margin-top:10px">思考 / 投機デコード</div>'
      + group(['reasoning', 'spec_type', 'spec_draft_n_max', 'spec_draft_p_min'])
      + '<div class="forge-card-title" style="margin-top:10px">サンプリング</div>'
      + group(['temp', 'top_p', 'top_k', 'min_p', 'presence_penalty', 'repeat_penalty'])
      + '</div>';
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
    // Evaluation hub: capability Benchmark + Twin Assist (run as a section here, not a tab).
    const subtab = state.bench.subtab || 'benchmark';
    const subnav = '<div class="forge-card-title forge-section-title">Evaluation</div>'
      + '<div class="forge-subnav">'
      + '<button type="button" class="forge-tab' + (subtab === 'benchmark' ? ' active' : '') + '" data-bench-subtab="benchmark">Benchmark</button>'
      + '<button type="button" class="forge-tab' + (subtab === 'twin-assist' ? ' active' : '') + '" data-bench-subtab="twin-assist">Twin Assist</button>'
      + '</div>';
    return subnav + (subtab === 'twin-assist' ? twinAssistHtml() : _benchmarkBody(data));
  }

  function _benchmarkBody(data) {
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
    const isLocalPort = sel.provider === 'local_openai_compatible';
    let modelSelect = '';
    let modelNote = '';
    let ctxField = '';
    if (isLocalPort) {
      // An already-running local OpenAI-compatible server (llama.cpp etc.) addressed by port.
      // Fetch /v1/models from that port to populate the model list; no Forge registry needed.
      const cat = data.localPortCatalog || {};
      const models = cat.models || [];
      ctxField = '<label class="forge-label">ポート (localhost)'
        + '<input class="forge-input" type="number" min="1" max="65535" data-bench-port value="'
        + escapeHtml(String(sel.port || '8080')) + '"></label>'
        + '<button type="button" class="forge-seg" data-bench-fetch-local>モデル一覧を取得</button>';
      modelSelect = '<select class="forge-select" data-bench-model-select>'
        + '<option value="">起動中モデルを選択…</option>'
        + models.map((m) => {
          const id = String(m.model_id || m.id || m.name || '');
          return '<option value="' + escapeHtml(id) + '"' + (sel.model === id ? ' selected' : '') + '>'
            + escapeHtml(id) + '</option>';
        }).join('') + '</select>';
      const st = String(cat.status || '');
      if (st && st !== 'ready') {
        modelNote = '<div class="forge-hint">ローカルサーバ（127.0.0.1:' + escapeHtml(String(sel.port || '8080'))
          + '）に接続できません（' + escapeHtml(st) + '）。起動状態とポートを確認してください。</div>';
      } else if (!models.length) {
        modelNote = '<div class="forge-hint">「モデル一覧を取得」を押すと、127.0.0.1:'
          + escapeHtml(String(sel.port || '8080')) + ' の起動中モデルを読み込みます。</div>';
      }
    } else if (isAnvil) {
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
      // Each registered model gets a 詳細設定 button that opens the per-model parameter drawer
      // (all llama-server launch params as pulldowns). This is independent of the benchmark target
      // selected above, so any model can be configured.
      if (!models.length) {
        ctxField = '<div class="forge-empty">登録モデルがありません。Models タブでスキャン/追加してください。</div>';
      } else {
        ctxField = '<div class="forge-card-title" style="margin-top:8px">登録モデルの詳細設定</div>'
          + '<div class="forge-anvil-model-list">'
          + models.map((m) => {
            const id = String(m.id || '');
            const key = String(m.model_key || m.name || '');
            const ctx = normalizeCtx(m.ctx_size);
            return '<div class="forge-anvil-model-row">'
              + '<span class="forge-anvil-model-name">' + escapeHtml(m.name || key)
              + (ctx ? ' <span class="forge-anvil-model-ctx">ctx ' + ctx + '</span>' : '') + '</span>'
              + '<button type="button" class="forge-seg" data-anvil-config data-model-id="' + escapeHtml(id) + '">⚙ 詳細設定</button>'
              + '</div>';
          }).join('')
          + '</div>';
      }
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
    const freeTextModel = (isAnvil || isLmStudio || isLocalPort)
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
    const canRun = sel.presets.length > 0 && sel.provider && sel.model && !sel.running;
    const result = sel.result
      ? '<div class="forge-bench-result">' + escapeHtml(sel.result) + '</div>'
      : '';
    const runLabel = sel.running ? '実行中…' : 'Run benchmark + 注入スイープ + Twin評価';
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
      + injectionObjectiveControl()
      + '<div class="forge-hint">1回の実行でベンチマーク・注入スイープ・Twin評価をまとめて行います。</div>'
      + '<button type="button" class="forge-run-btn" data-bench-run' + (canRun ? '' : ' disabled') + '>'
      + escapeHtml(runLabel) + '</button>'
      + result
      + injectionSweepInlineHtml()
      + twinAssistInlineHtml()
      + '</div>'
      + methodComparisonHtml(data)
    );
  }

  // Distinct reasons a Twin case could not be measured (e.g. missing fixtures), so an unavailable
  // run is shown honestly instead of as a misleading 0.000.
  function twinUnavailableReasons(rep) {
    const reasons = new Set();
    (rep.comparisons || []).forEach((c) => {
      const attempts = [c.baseline].concat(c.assisted || []);
      attempts.forEach((a) => (a && a.unavailable_reasons ? a.unavailable_reasons : []).forEach((r) => reasons.add(r)));
    });
    return Array.from(reasons);
  }

  // Full Twin-assist result shown inline in the Benchmark tab (consolidated here; the Twin Assist
  // subtab is read-only). Honest about unavailable runs — never renders 0.000 as if it were measured.
  function twinAssistInlineHtml() {
    const rep = state.bench.twinResult;
    if (!rep) return '';
    const agg = rep.aggregate_scores || {};
    const scored = Number(agg.scored_case_count || 0) > 0 && rep.status !== 'unavailable';
    const fmt = (v) => escapeHtml(v == null ? 'unavailable' : (typeof v === 'number' ? v.toFixed(3) : String(v)));
    const head = '<div class="forge-card-title">Twin assist 評価（今回の実行）</div>';
    if (!scored) {
      const reasons = twinUnavailableReasons(rep);
      const fixtureMissing = reasons.some((r) => String(r).startsWith('fixture_missing'));
      return (
        '<div class="forge-card">' + head
        + '<div class="forge-warn">Twin評価は実行されませんでした（status: ' + escapeHtml(rep.status || 'unavailable')
        + '）。スコアは測定値ではありません。</div>'
        + (reasons.length ? '<div class="forge-kv"><span>理由</span><b>' + escapeHtml(reasons.join(', ')) + '</b></div>' : '')
        + (fixtureMissing ? '<div class="forge-hint">Twin評価ケースのフィクスチャ（ca_data/model_forge/twin_assist_fixtures）が未配置のため、'
          + 'モデルは呼び出されていません。フィクスチャを配置すると評価が走ります。</div>' : '')
        + '</div>'
      );
    }
    const rows = (rep.comparisons || []).map((item) => {
      const baseline = item.baseline && item.baseline.score != null ? item.baseline.score : 'unavailable';
      const best = item.best_score != null ? item.best_score : 'unavailable';
      const lift = item.lift != null ? item.lift : 'unavailable';
      return '<tr><td>' + escapeHtml(item.case_id) + '</td><td>' + escapeHtml(baseline) + '</td><td>'
        + escapeHtml(best) + '</td><td>' + escapeHtml(lift) + '</td><td>'
        + escapeHtml(item.best_assist_mode || 'unavailable') + '</td><td>'
        + (item.harm_detected ? '<span class="forge-warn-pill">harm</span>' : 'no') + '</td></tr>';
    }).join('');
    const tips = forgeTipsHtml([
      '<b>mean best score（0–1）</b>: 補助ありで出せた最高スコアの平均。高いほど能力が高い。',
      '<b>mean lift</b>: 補助なし→ありのスコア上昇分。プラスが大きいほどTwinが効く。0付近＝補助不要。',
      '<b>harm rate</b>: 補助で逆に悪化した割合。低いほど良い（0が理想）。',
      '<b>recommended injection level（0–4）</b>: 低いほど少ない補助で足りる＝モデルが優秀。',
    ]);
    return (
      '<div class="forge-card">' + head + tips
      + '<div class="forge-kv"><span>mean best score（高いほど能力↑）</span><b>' + fmt(agg.mean_best_score) + '</b></div>'
      + '<div class="forge-kv"><span>mean lift（補助の効き）</span><b>' + fmt(agg.mean_lift) + '</b></div>'
      + '<div class="forge-kv"><span>harm rate（低いほど良い）</span><b>' + fmt(agg.harm_rate) + '</b></div>'
      + '<div class="forge-kv"><span>recommended assist</span><b>'
      + escapeHtml((rep.recommended_assist_modes || []).join(', ') || 'none') + '</b></div>'
      + '<div class="forge-kv"><span>recommended injection level</span><b>'
      + fmt(rep.recommended_twin_injection_level) + '</b></div>'
      + '<div class="forge-table-wrap"><table><thead><tr><th>case</th><th>baseline</th><th>assisted</th>'
      + '<th>lift</th><th>best mode</th><th>harm</th></tr></thead><tbody>' + rows + '</tbody></table></div>'
      + '<div class="forge-card-title" style="margin-top:8px">Assist Effect (補助有無)</div>'
      + assistEffectRadarHtml(rep.comparisons || [])
      + '<div class="forge-hint">評価のみ。ファイル適用や本番ルーティングは変更しません。</div>'
      + '</div>'
    );
  }

  // Twin injection sweep: benchmark capability across injection levels 0..4 and plot the curve so
  // the optimal injection amount is visible. Advisory — the measured optimum feeds ExecutionPolicy
  // as a CEILING (never below a route's safety floor); it never changes routing directly here.
  const INJECTION_SWEEP_DIMENSIONS = [
    'structured_output_fidelity', 'patch_protocol_fidelity', 'edit_intent_quality', 'anchor_selection_quality',
  ];

  const INJECTION_OBJECTIVES = [
    ['min_sufficient', 'Min injection'],
    ['max_score', 'Max score'],
  ];

  // Injection objective switch (Min injection / Max score). Lives in the Benchmark Model card —
  // the sweep itself runs as part of the single Benchmark action, not a separate button.
  function injectionObjectiveControl() {
    const objective = state.bench.injectionObjective || 'min_sufficient';
    const objBtns = INJECTION_OBJECTIVES.map(([id, label]) => (
      '<button type="button" class="forge-seg' + (objective === id ? ' active' : '')
      + '" data-injection-objective="' + id + '">' + escapeHtml(label) + '</button>'
    )).join('');
    return '<div class="forge-label">注入方針（Twin injection objective）</div>'
      + '<div class="forge-seg-row">' + objBtns + '</div>'
      + '<div class="forge-hint"><b>Min injection</b>=ピーク許容内で最小の注入（弱モデル向け・天井として適用）／'
      + '<b>Max score</b>=最高スコアの注入レベル（床として適用）。助言のみ。</div>';
  }

  // Injection-sweep RESULT, rendered inline under Benchmark (consolidated; no separate sweep panel).
  function injectionSweepInlineHtml() {
    const rec = state.bench.injectionSweep;
    if (!rec) return '';
    return '<div class="forge-card"><div class="forge-card-title">Twin injection sweep（今回の実行）</div>'
      + injectionSweepResult(rec) + '</div>';
  }

  // Collapsible "how to read this" tips block, so the metrics' DIRECTION is never ambiguous.
  function forgeTipsHtml(lines) {
    return '<details class="forge-tips"><summary>📖 読み方（数値の見方）</summary><ul>'
      + lines.map((l) => '<li>' + l + '</li>').join('') + '</ul></details>';
  }

  // Autonomy index: a higher-is-better restatement of the injection level so it reads in the SAME
  // direction as the capability scores (less injection needed -> more capable -> bigger number).
  function autonomyIndex(rec) {
    const levels = (rec.levels || []);
    const maxLevel = levels.length ? Math.max.apply(null, levels) : 4;
    const sel = rec.selected_injection_level;
    if (sel == null || maxLevel <= 0) return null;
    return Math.max(0, Math.min(1, (maxLevel - sel) / maxLevel));
  }

  function injectionSweepResult(rec) {
    const fmt = (v) => escapeHtml(v == null ? 'unavailable' : String(v));
    const pct = (v) => (typeof v === 'number' ? Math.round(v * 100) + '%' : 'unavailable');
    const peak = rec.per_dimension_optimal || {};
    const minSuf = rec.per_dimension_min_sufficient_level || {};
    const dims = Object.keys(peak).sort();
    const dimRows = dims.map((dim) => (
      '<div class="forge-kv"><span>' + escapeHtml(dim) + '</span><b>'
      + fmt(minSuf[dim]) + ' <span class="forge-dim-peak">(peak ' + fmt(peak[dim]) + ')</span></b></div>'
    )).join('');
    const autonomy = autonomyIndex(rec);
    const tips = forgeTipsHtml([
      '<b>スコア（0–100%）</b>: 高いほど能力が高い。グラフは曲線が上＝優秀。',
      '<b>注入レベル（0–4）</b>: 低いほど少ない補助で動く＝モデルが優秀。0 = 補助なしでも能力を発揮（最良）。',
      '<b>自律度</b>: 注入レベルを「高いほど良い」に言い換えた指標（自律度=（最大-選択）/最大）。能力スコアと同じ向きで読めます。',
      '<b>min sufficient</b>: ここまで注入を下げても能力を（tolerance内で）維持できる最小レベル。',
      '<b>peak</b>: 最高スコアになる注入レベル。<b>tolerance</b>: peak から何点下までを「十分」とみなすか。',
    ]);
    return (
      '<div class="forge-injection-sweep">'
      + tips
      // Headline capability readings, oriented so "higher = more capable".
      + '<div class="forge-kv"><span>best score（最高スコア）</span><b>' + pct(rec.best_mean_score) + '</b></div>'
      + '<div class="forge-kv"><span>自律度（高いほど能力↑）</span><b>' + pct(autonomy) + '</b></div>'
      + '<div class="forge-kv"><span>objective</span><b>' + fmt(rec.objective) + '</b></div>'
      + '<div class="forge-kv"><span>selected injection level（低いほど優秀）</span><b>'
      + fmt(rec.selected_injection_level) + '</b></div>'
      // Both readings shown regardless of objective.
      + '<div class="forge-kv"><span>min sufficient injection level</span><b>'
      + fmt(rec.min_sufficient_injection_level) + '</b></div>'
      + '<div class="forge-kv"><span>peak (max-score) level</span><b>'
      + fmt(rec.recommended_injection_level) + '</b></div>'
      + '<div class="forge-kv"><span>tolerance</span><b>' + fmt(rec.tolerance) + '</b></div>'
      + injectionSweepChart(rec)
      + '<div class="forge-card-title" style="margin-top:8px">Per-dimension min sufficient level（低いほど優秀）</div>'
      + (dimRows || '<div class="forge-empty">No measured dimensions.</div>')
      + methodSubstitutionHtml(rec)
      + '</div>'
    );
  }

  // When a weakness can't be fixed by more injection (injection-resistant), the platform proposes a
  // DIFFERENT generation method — so "injection didn't help" becomes actionable
  // ("edit_intent is weak -> use deterministic_text_patch instead").
  function methodSubstitutionHtml(rec) {
    const subs = rec.method_substitutions || [];
    if (!subs.length) return '';
    const rows = subs.map((s) => (
      '<div class="forge-subst-row"><div class="forge-subst-dim">⚠ ' + escapeHtml(s.dimension)
      + ' <span class="forge-dim-peak">（注入では直らない）</span></div>'
      + '<div class="forge-kv"><span>避ける手法</span><b>' + escapeHtml((s.avoid || []).join(', ')) + '</b></div>'
      + '<div class="forge-kv"><span>代わりに使う手法</span><b>' + escapeHtml((s.prefer || []).join(' → ')) + '</b></div>'
      + '<div class="forge-hint">' + escapeHtml(s.why || '') + '</div></div>'
    )).join('');
    return '<div class="forge-card-title" style="margin-top:8px">注入では直らない弱点 → 別の補助手法を提案</div>' + rows;
  }

  // Inline SVG line chart of the mean dimension score per injection level (no chart library).
  // X = injection level, Y = mean score 0..1. Null means (only unavailable evidence) are gaps.
  function injectionSweepChart(rec) {
    const levels = (rec.levels || []).slice().sort((a, b) => a - b);
    const means = rec.level_means || {};
    if (!levels.length) return '';
    const W = 320, H = 160, padL = 32, padR = 12, padT = 12, padB = 24;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const xAt = (i) => padL + (levels.length === 1 ? plotW / 2 : (plotW * i) / (levels.length - 1));
    const yAt = (v) => padT + (1 - Math.max(0, Math.min(1, v))) * plotH;
    // Emphasise the level the chosen objective selected; fall back to min-sufficient, then peak.
    const highlight = rec.selected_injection_level != null ? rec.selected_injection_level
      : (rec.min_sufficient_injection_level != null
        ? rec.min_sufficient_injection_level : rec.recommended_injection_level);
    // Y gridlines + labels at 0, 0.5, 1.
    const grid = [0, 0.5, 1].map((v) => (
      '<line x1="' + padL + '" y1="' + yAt(v).toFixed(1) + '" x2="' + (W - padR) + '" y2="' + yAt(v).toFixed(1)
      + '" class="forge-chart-grid"></line>'
      + '<text x="' + (padL - 4) + '" y="' + (yAt(v) + 3).toFixed(1) + '" class="forge-chart-axis" text-anchor="end">'
      + v.toFixed(1) + '</text>'
    )).join('');
    // Sufficiency threshold = peak mean - tolerance. Levels whose mean sits on/above it are "enough".
    let threshold = '';
    if (typeof rec.best_mean_score === 'number' && typeof rec.tolerance === 'number') {
      const ty = yAt(rec.best_mean_score - rec.tolerance);
      threshold = '<line x1="' + padL + '" y1="' + ty.toFixed(1) + '" x2="' + (W - padR) + '" y2="' + ty.toFixed(1)
        + '" class="forge-chart-threshold"><title>sufficiency threshold (peak − tolerance)</title></line>';
    }
    const pts = [];
    const dots = [];
    const xLabels = [];
    levels.forEach((lvl, i) => {
      const m = means[String(lvl)];
      const x = xAt(i);
      xLabels.push('<text x="' + x.toFixed(1) + '" y="' + (H - 6) + '" class="forge-chart-axis" text-anchor="middle">'
        + escapeHtml(String(lvl)) + '</text>');
      if (typeof m === 'number') {
        const y = yAt(m);
        pts.push(x.toFixed(1) + ',' + y.toFixed(1));
        const isRec = lvl === highlight;
        dots.push('<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="' + (isRec ? 5 : 3)
          + '" class="forge-chart-dot' + (isRec ? ' is-recommended' : '') + '">'
          + '<title>level ' + escapeHtml(String(lvl)) + ': mean ' + m.toFixed(3) + '</title></circle>');
      }
    });
    const line = pts.length > 1
      ? '<polyline points="' + pts.join(' ') + '" class="forge-chart-line" fill="none"></polyline>' : '';
    return (
      '<svg class="forge-chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" '
      + 'aria-label="Mean capability score per Twin injection level">'
      + grid + threshold + line + dots.join('') + xLabels.join('')
      + '<text x="' + (W / 2) + '" y="' + H + '" class="forge-chart-axis" text-anchor="middle">injection level</text>'
      + '</svg>'
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
    content.querySelector('[data-bench-port]')?.addEventListener('input', (e) => {
      state.bench.port = e.target.value;
    });
    content.querySelector('[data-bench-fetch-local]')?.addEventListener('click', () => loadLocalPortCatalog());
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
    // Per-model 詳細設定 button: open the parameter drawer for that registered model.
    content.querySelectorAll('[data-anvil-config]').forEach((btn) => {
      btn.addEventListener('click', () => openAnvilConfig(btn.getAttribute('data-model-id')));
    });
    content.querySelector('[data-bench-load]')?.addEventListener('click', () => loadSelectedModel());
    content.querySelector('[data-bench-run]')?.addEventListener('click', () => runBenchmark(data));
    content.querySelectorAll('[data-injection-objective]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.bench.injectionObjective = btn.getAttribute('data-injection-objective');
        renderActive();
      });
    });
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

  // Open the per-model 詳細設定 drawer: all llama-server launch params as pulldowns, prefilled
  // from the model's Models DB row. Reuses the shared forge-drawer overlay.
  function openAnvilConfig(modelId) {
    const model = (state.data.localModels || []).find((m) => String(m.id || '') === String(modelId));
    if (!model) { setStatus('モデルが見つかりません', 'error'); return; }
    let drawer = $('forge-drawer');
    if (!drawer) {
      drawer = document.createElement('div');
      drawer.id = 'forge-drawer';
      drawer.className = 'forge-drawer';
      document.body.appendChild(drawer);
    }
    drawer.innerHTML = (
      '<div class="forge-drawer-inner">'
      + '<div class="forge-drawer-head"><span>詳細設定 · ' + escapeHtml(model.name || model.model_key || String(modelId)) + '</span>'
      + '<button type="button" class="forge-drawer-close" aria-label="Close">×</button></div>'
      + '<div class="forge-drawer-sub">llama-server 起動パラメータ。プルダウンで選択（「カスタム…」で自由入力）。未指定の項目は起動時に省略されます。</div>'
      + '<div class="forge-drawer-body">' + renderAnvilConfigForm(model) + '</div>'
      + '<div class="forge-drawer-foot">'
      + '<button type="button" class="forge-run-btn" data-anvil-save data-model-id="' + escapeHtml(String(modelId)) + '">保存</button>'
      + '<div class="forge-hint">保存後、対象モデルを再ロードすると反映されます。</div>'
      + '</div></div>'
    );
    drawer.classList.add('open');
    drawer.querySelector('.forge-drawer-close')?.addEventListener('click', closeModelDrawer);
    drawer.addEventListener('click', (e) => { if (e.target === drawer) closeModelDrawer(); });
    // Reveal the free-input box only when その項目の「カスタム…」が選ばれたとき。
    drawer.querySelectorAll('select[data-anvil-param]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const key = sel.getAttribute('data-anvil-param');
        const custom = drawer.querySelector('[data-anvil-custom="' + key + '"]');
        if (custom) custom.style.display = sel.value === '__custom__' ? '' : 'none';
      });
    });
    drawer.querySelector('[data-anvil-save]')?.addEventListener('click', (e) => {
      saveAnvilConfig(drawer, e.target.getAttribute('data-model-id'));
    });
  }

  // Persist the drawer's parameters back to the Models DB registry entry (Anvil). The runtime
  // manager reads these columns when it loads the model (main.py _runtime_spec_from_row), so this
  // is the authoritative per-model launch configuration.
  async function saveAnvilConfig(drawer, modelId) {
    if (!modelId || !drawer) { setStatus('保存できません（モデル未選択）', 'error'); return; }
    const params = {};
    ANVIL_PARAM_FIELDS.forEach((f) => {
      const sel = drawer.querySelector('select[data-anvil-param="' + f.key + '"]');
      if (!sel) { params[f.key] = ''; return; }
      let v = sel.value;
      if (v === '__custom__') {
        const custom = drawer.querySelector('[data-anvil-custom="' + f.key + '"]');
        v = custom ? custom.value : '';
      }
      params[f.key] = v;
    });
    const payload = anvilParamsToPayload(params);
    const ctxNum = normalizeCtx(payload.ctx_size);
    if (!ctxNum) { setStatus('CTX が無効です（512 以上の数値を指定してください）', 'error'); return; }
    setStatus('詳細設定を保存中…');
    try {
      const resp = await fetch('/models/db/' + encodeURIComponent(modelId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(String(resp.status));
      await loadLocalModels();
      setStatus('詳細設定を保存しました', 'ok');
      closeModelDrawer();
    } catch (err) {
      setStatus('詳細設定の保存に失敗: ' + (err && err.message ? err.message : 'error'), 'error');
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

  function localPortBaseUrl() {
    const port = String(state.bench.port || '8080').trim() || '8080';
    return 'http://127.0.0.1:' + port;
  }

  // Models advertised by an already-running local server at the chosen port (no Forge registry).
  async function loadLocalPortCatalog() {
    setStatus('ローカルサーバのモデルを取得中…');
    try {
      state.data.localPortCatalog = await api(
        '/local-catalog?runtime_kind=llama_cpp&base_url=' + encodeURIComponent(localPortBaseUrl()));
      const st = String(state.data.localPortCatalog.status || '');
      setStatus(st === 'ready' ? 'モデル一覧を取得しました' : ('取得結果: ' + st), st === 'ready' ? 'ok' : 'error');
    } catch (err) {
      state.data.localPortCatalog = { status: 'error', models: [] };
      setStatus('モデル取得に失敗: ' + (err && err.message ? err.message : 'error'), 'error');
    }
    renderActive();
  }

  // Anvil and LM Studio both execute through the local OpenAI-compatible provider; map the
  // UI-level runtime choice to that real provider id. local_openai_compatible passes through.
  function runtimeProviderId() {
    const p = state.bench.provider;
    return (p === 'anvil' || p === 'lm_studio') ? 'local_openai_compatible' : p;
  }

  function injectionSweepBaseUrl(data) {
    const sel = state.bench;
    const settings = data.settings || {};
    if (sel.provider === 'openrouter') return (settings.openrouter || {}).base_url || '';
    // Local server addressed by port: build the URL directly from the chosen port.
    if (sel.provider === 'local_openai_compatible') return localPortBaseUrl();
    // Anvil / LM Studio fall back to the configured local base URL (server resolves when blank).
    return (settings.local_provider || {}).base_url || '';
  }

  // The single Benchmark action: run the capability benchmark, the injection sweep, and the Twin
  // assist evaluation in one go, all against the same provider/model/base_url. Each step is
  // independent — a failure in one is reported but does not abort the others.
  async function runBenchmark(data) {
    const sel = state.bench;
    if (!sel.presets.length || !sel.provider || !sel.model) {
      setStatus('プリセット・プロバイダ・モデルを選択してください', 'error'); return;
    }
    sel.running = true; renderActive();
    setStatus('実行中: ベンチマーク…');
    const notes = [];
    notes.push(await runArenaCore(data));
    setStatus('実行中: 注入スイープ…');
    notes.push(await runInjectionSweepCore(data));
    setStatus('実行中: Twin評価…');
    notes.push(await runTwinAssistCore(data));
    sel.running = false;
    const failed = notes.filter((n) => !n.ok);
    setStatus(failed.length ? ('一部失敗: ' + failed.map((n) => n.msg).join(' / '))
      : 'ベンチマーク＋注入スイープ＋Twin評価 完了', failed.length ? 'error' : 'ok');
    renderActive();
  }

  function isLocalProvider() {
    const p = state.bench.provider;
    return p === 'anvil' || p === 'lm_studio' || p === 'local_openai_compatible';
  }

  async function runArenaCore(data) {
    const sel = state.bench;
    const preset = (data.presets || []).find((p) => p.preset_id === sel.presets[0]);
    const route = (preset && preset.recommended_routes && preset.recommended_routes[0]) || 'direct_patch';
    try {
      const body = {
        stage: 'patch_generation',
        specs: [{ provider_id: runtimeProviderId(), model_id: sel.model, route_id: route }],
        preset_id: sel.presets[0],
        preset_ids: sel.presets.slice(),
        depth: sel.depth,
      };
      // Local-by-port: tell the arena which running server to use and probe it (avoids
      // health_unavailable from an unprobed local provider).
      if (isLocalProvider()) {
        body.base_url = injectionSweepBaseUrl(data);
        body.runtime_kind = sel.provider === 'lm_studio' ? 'lm_studio' : 'llama_cpp';
      }
      const record = await api('/arena/run', { method: 'POST', body: JSON.stringify(body) });
      const cand = (record.candidates || [])[0] || {};
      sel.result = 'Arena run ' + record.arena_run_id + ' — candidate ' + (cand.adoption_state || 'not_applied')
        + ' (Safe Apply required before any adoption). See the Arena tab for candidates.';
      try { state.data.arena = await api('/arena/runs/' + record.arena_run_id); }
      catch (_e) { state.data.arena = record; }
      return { ok: true, msg: 'benchmark' };
    } catch (err) {
      sel.result = 'Run failed: ' + (err && err.message ? err.message : 'error');
      return { ok: false, msg: 'ベンチマーク' };
    }
  }

  async function runInjectionSweepCore(data) {
    const sel = state.bench;
    try {
      sel.injectionSweep = await api('/evaluation/injection-sweep', {
        method: 'POST',
        body: JSON.stringify({
          provider_id: runtimeProviderId(),
          model_id: sel.model,
          base_url: injectionSweepBaseUrl(data),
          dimensions: INJECTION_SWEEP_DIMENSIONS,
          objective: sel.injectionObjective || 'min_sufficient',
        }),
      });
      return { ok: true, msg: 'injection_sweep' };
    } catch (err) {
      return { ok: false, msg: '注入スイープ(' + (err && err.message ? err.message : 'error') + ')' };
    }
  }

  async function runTwinAssistCore(data) {
    const sel = state.bench;
    try {
      const cases = await api('/twin-assist/cases?pack_id=quick');
      sel.twinResult = await api('/twin-assist/run', {
        method: 'POST',
        body: JSON.stringify({
          provider_id: runtimeProviderId(),
          model_id: sel.model,
          base_url: injectionSweepBaseUrl(data),
          case_ids: (cases.cases || []).map((item) => item.case_id),
          assist_modes: ['twin_localized_slot', 'twin_deterministic_anchor'],
          run_baseline: true,
        }),
      });
      state.twinAssist.result = sel.twinResult;  // keep the read-only subtab in sync
      return { ok: true, msg: 'twin_assist' };
    } catch (err) {
      return { ok: false, msg: 'Twin評価(' + (err && err.message ? err.message : 'error') + ')' };
    }
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
      + '<button type="button" class="forge-detail-btn" data-candidate-detail="'
      + escapeHtml(c.candidate_id) + '">Details</button>'
      + '<button type="button" class="forge-detail-btn" data-policy-recommendation="'
      + escapeHtml(c.candidate_id) + '">Policy</button>'
      + '<button type="button" class="forge-adopt-btn" data-candidate-proposal="'
      + escapeHtml(c.candidate_id) + '"' + (eligible ? '' : ' disabled')
      + ' title="' + escapeHtml(btnTitle) + '">' + escapeHtml(btnLabel) + '</button>'
      + '<span class="forge-cand-metric">approval required; requires Safe Apply</span>'
      + '</div>'
      + '</div>'
    );
  }

  const RADAR_GROUPS = {
    Capability: ['impact_analysis', 'contract_preservation', 'test_generation'],
    Method: ['structured_output_fidelity', 'patch_protocol_fidelity', 'fallback_recovery'],
    Safety: ['scope_boundary_discipline', 'evidence_discipline', 'repair_discipline'],
    Speed: ['speed', 'latency_efficiency'],
  };

  function radarEntries(candidate, filterName) {
    const score = candidate.evaluator_score || {};
    const values = score.radar_scores || {};
    const unavailable = new Set(score.unavailable_dimensions || []);
    let keys = filterName === 'All'
      ? Object.keys(values)
      : (RADAR_GROUPS[filterName] || []);
    keys = keys.filter((key) => Object.prototype.hasOwnProperty.call(values, key) || unavailable.has(key));
    return keys.map((key) => ({
      key,
      unavailable: unavailable.has(key) || values[key] === null || values[key] === undefined,
      value: typeof values[key] === 'number' ? Math.max(0, Math.min(1, values[key])) : null,
    }));
  }

  function radarHtml(candidate, filterName) {
    const active = filterName || 'All';
    const entries = radarEntries(candidate, active);
    const filters = ['Capability', 'Method', 'Safety', 'Speed', 'All'].map((name) => (
      '<button type="button" class="forge-radar-filter' + (name === active ? ' active' : '')
      + '" data-radar-filter="' + name + '">' + name + '</button>'
    )).join('');
    if (!entries.length) {
      return '<div class="forge-radar"><div class="forge-radar-filters">' + filters + '</div>'
        + '<div class="forge-empty">No radar evidence for this filter.</div></div>';
    }
    const cx = 120; const cy = 110; const radius = 76;
    const outer = entries.map((_entry, index) => {
      const angle = (-Math.PI / 2) + (Math.PI * 2 * index / entries.length);
      return (cx + radius * Math.cos(angle)).toFixed(1) + ',' + (cy + radius * Math.sin(angle)).toFixed(1);
    }).join(' ');
    const points = entries.map((entry, index) => {
      const angle = (-Math.PI / 2) + (Math.PI * 2 * index / entries.length);
      const distance = entry.unavailable ? 0 : radius * entry.value;
      return (cx + distance * Math.cos(angle)).toFixed(1) + ',' + (cy + distance * Math.sin(angle)).toFixed(1);
    }).join(' ');
    const labels = entries.map((entry, index) => {
      const angle = (-Math.PI / 2) + (Math.PI * 2 * index / entries.length);
      const x = cx + (radius + 22) * Math.cos(angle);
      const y = cy + (radius + 22) * Math.sin(angle);
      const value = entry.unavailable ? 'unavailable' : Math.round(entry.value * 100) + '%';
      return '<text x="' + x.toFixed(1) + '" y="' + y.toFixed(1)
        + '" class="forge-radar-label' + (entry.unavailable ? ' is-unavailable' : '') + '">'
        + escapeHtml(entry.key) + ' · ' + value + '</text>';
    }).join('');
    const missing = entries.filter((entry) => entry.unavailable).length;
    // Optional "without assist" baseline overlay (補助有無). When the candidate score carries
    // baseline_radar_scores, draw a second dashed polygon + legend so the Twin effect is visible.
    const baselineMap = (candidate.evaluator_score || {}).baseline_radar_scores || {};
    const hasBaseline = entries.some((entry) => typeof baselineMap[entry.key] === 'number');
    const baselinePoints = entries.map((entry, index) => {
      const angle = (-Math.PI / 2) + (Math.PI * 2 * index / entries.length);
      const raw = baselineMap[entry.key];
      const distance = typeof raw === 'number' ? radius * Math.max(0, Math.min(1, raw)) : 0;
      return (cx + distance * Math.cos(angle)).toFixed(1) + ',' + (cy + distance * Math.sin(angle)).toFixed(1);
    }).join(' ');
    const legend = hasBaseline
      ? '<div class="forge-radar-legend"><span class="forge-radar-key forge-radar-key--assisted">with assist (補助あり)</span>'
        + '<span class="forge-radar-key forge-radar-key--baseline">without assist (補助なし)</span></div>'
      : '';
    return '<div class="forge-radar"><div class="forge-radar-filters">' + filters + '</div>' + legend
      + '<div class="forge-radar-note">面積が大きいほど能力が高い（各軸0–100%、高いほど優秀）</div>'
      + '<svg class="forge-radar-svg" viewBox="0 0 240 220" role="img" aria-label="Candidate radar">'
      + '<polygon class="forge-radar-grid" points="' + outer + '"></polygon>'
      + (hasBaseline ? '<polygon class="forge-radar-shape forge-radar-shape--baseline" points="' + baselinePoints + '"></polygon>' : '')
      + '<polygon class="forge-radar-shape' + (hasBaseline ? ' forge-radar-shape--assisted' : '') + '" points="' + points + '"></polygon>' + labels + '</svg>'
      + (missing ? '<div class="forge-radar-unavailable">Unavailable is missing evidence, not a zero score.</div>' : '')
      + '</div>';
  }

  function assistEffectRadarHtml(comparisons) {
    // Overlay radar that visualizes the Twin assist effect: one polygon WITHOUT assist
    // (baseline) and one WITH assist (best assisted score), per evaluated case.
    const entries = (comparisons || []).filter((c) => c && c.case_id).slice(0, 8).map((c) => ({
      key: c.case_id,
      baseline: (c.baseline && typeof c.baseline.score === 'number') ? Math.max(0, Math.min(1, c.baseline.score)) : null,
      assisted: typeof c.best_score === 'number' ? Math.max(0, Math.min(1, c.best_score)) : null,
    }));
    if (entries.length < 3) {
      return '<div class="forge-empty">Need at least 3 evaluated cases to draw the assist-effect radar.</div>';
    }
    const cx = 120; const cy = 110; const radius = 76;
    const ring = (series) => entries.map((entry, index) => {
      const angle = (-Math.PI / 2) + (Math.PI * 2 * index / entries.length);
      const value = entry[series];
      const distance = typeof value === 'number' ? radius * value : 0;
      return (cx + distance * Math.cos(angle)).toFixed(1) + ',' + (cy + distance * Math.sin(angle)).toFixed(1);
    }).join(' ');
    const outer = entries.map((_entry, index) => {
      const angle = (-Math.PI / 2) + (Math.PI * 2 * index / entries.length);
      return (cx + radius * Math.cos(angle)).toFixed(1) + ',' + (cy + radius * Math.sin(angle)).toFixed(1);
    }).join(' ');
    const labels = entries.map((entry, index) => {
      const angle = (-Math.PI / 2) + (Math.PI * 2 * index / entries.length);
      const x = cx + (radius + 20) * Math.cos(angle);
      const y = cy + (radius + 20) * Math.sin(angle);
      return '<text x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" class="forge-radar-label">' + escapeHtml(entry.key) + '</text>';
    }).join('');
    return '<div class="forge-radar">'
      + '<div class="forge-radar-legend"><span class="forge-radar-key forge-radar-key--assisted">with assist (補助あり)</span>'
      + '<span class="forge-radar-key forge-radar-key--baseline">without assist (補助なし)</span></div>'
      + '<div class="forge-radar-note">面積が大きいほど能力が高い（各軸0–100%）。補助ありの面積が大きい＝Twinが効いている</div>'
      + '<svg class="forge-radar-svg" viewBox="0 0 240 220" role="img" aria-label="Assist effect radar (with vs without Twin)">'
      + '<polygon class="forge-radar-grid" points="' + outer + '"></polygon>'
      + '<polygon class="forge-radar-shape forge-radar-shape--baseline" points="' + ring('baseline') + '"></polygon>'
      + '<polygon class="forge-radar-shape forge-radar-shape--assisted" points="' + ring('assisted') + '"></polygon>'
      + labels + '</svg></div>';
  }

  function openCandidateDrawer(candidateId, filterName) {
    const candidate = ((state.data.arena || {}).candidates || []).find((item) => item.candidate_id === candidateId);
    if (!candidate) return;
    let drawer = $('forge-drawer');
    if (!drawer) {
      drawer = document.createElement('div'); drawer.id = 'forge-drawer'; drawer.className = 'forge-drawer';
      document.body.appendChild(drawer);
    }
    drawer.innerHTML = '<div class="forge-drawer-inner"><div class="forge-drawer-head"><span>'
      + escapeHtml(candidate.model_id) + '</span><button type="button" class="forge-drawer-close">×</button></div>'
      + '<div class="forge-drawer-sub">' + escapeHtml(candidate.route_id) + ' · '
      + escapeHtml(candidate.method_variant || 'method unavailable') + '</div><div class="forge-drawer-body">'
      + radarHtml(candidate, filterName || 'All') + fallbackGraphHtml(candidate) + '</div></div>';
    drawer.classList.add('open');
    drawer.querySelector('.forge-drawer-close')?.addEventListener('click', closeModelDrawer);
    drawer.querySelectorAll('[data-radar-filter]').forEach((button) => button.addEventListener('click', () => (
      openCandidateDrawer(candidateId, button.getAttribute('data-radar-filter'))
    )));
  }

  function fallbackGraphHtml(candidate) {
    const primary = candidate.method_variant || 'method unavailable';
    const configured = candidate.method_fallbacks || [];
    const attempted = ((candidate.result || {}).fallback_attempts || []).map(String);
    const nodes = [primary].concat(configured).map((method, index) => {
      const used = index > 0 && attempted.indexOf(String(method)) >= 0;
      const label = index === 0 ? 'primary' : (used ? 'attempted' : 'available');
      return '<div class="forge-fallback-node' + (used ? ' is-attempted' : '') + '"><span>'
        + escapeHtml(method) + '</span><small>' + label + '</small></div>';
    });
    if (!configured.length) {
      nodes.push('<div class="forge-fallback-node is-unavailable"><span>fallback unavailable</span>'
        + '<small>no configured evidence</small></div>');
    }
    return '<section class="forge-fallback-graph"><div class="forge-card-title">Fallback graph</div>'
      + '<div class="forge-fallback-chain">' + nodes.join('<span class="forge-fallback-arrow">→</span>')
      + '</div><div class="forge-hint">Graph is observational; it does not execute or apply a method.</div></section>';
  }

  function methodComparisonHtml(data) {
    const candidates = ((data || {}).arena || {}).candidates || [];
    if (!candidates.length) return '';
    const rows = candidates.map((candidate) => {
      const result = candidate.result || {};
      const score = candidate.evaluator_score || {};
      const fallbacks = candidate.method_fallbacks || [];
      const contract = result.contract_valid === true ? 'valid'
        : (result.contract_valid === false ? 'invalid' : 'unavailable');
      return '<tr><td>' + escapeHtml(candidate.model_id) + '</td><td>'
        + escapeHtml(candidate.method_variant || 'unavailable') + '</td><td>'
        + escapeHtml(fallbacks.length ? fallbacks.join(' → ') : 'unavailable') + '</td><td>'
        + contract + '</td><td>' + escapeHtml(score.final_score ?? 'unavailable') + '</td></tr>';
    }).join('');
    return '<div class="forge-card forge-method-comparison"><div class="forge-card-title">Method comparison</div>'
      + '<div class="forge-table-wrap"><table><thead><tr><th>Model</th><th>Primary method</th>'
      + '<th>Fallbacks</th><th>Contract</th><th>Score</th></tr></thead><tbody>' + rows
      + '</tbody></table></div></div>';
  }

  function policyRecommendationHtml(candidate) {
    const score = candidate.evaluator_score || {};
    const contractValid = (candidate.result || {}).contract_valid === true;
    const blocked = candidate.blocked_reasons || [];
    const recommendation = contractValid && !blocked.length ? 'eligible_for_proposal_review' : 'retain_current_policy';
    return '<div class="forge-policy-recommendation"><div class="forge-card-title">Policy recommendation</div>'
      + '<div class="forge-kv"><span>Status</span><b>advisory_not_applied</b></div>'
      + '<div class="forge-kv"><span>Recommendation</span><b>' + recommendation + '</b></div>'
      + '<div class="forge-kv"><span>Primary method</span><b>'
      + escapeHtml(candidate.method_variant || 'unavailable') + '</b></div>'
      + '<div class="forge-kv"><span>Score evidence</span><b>'
      + escapeHtml(score.final_score ?? 'unavailable') + '</b></div>'
      + (blocked.length ? '<div class="forge-cand-blocked">Blocked: ' + escapeHtml(blocked.join('; ')) + '</div>' : '')
      + '<div class="forge-warn">Recommendation cannot change routing. Proposal, Safe Apply, and Verification remain required.</div></div>';
  }

  function openPolicyRecommendationDrawer(candidateId) {
    const candidate = ((state.data.arena || {}).candidates || []).find((item) => item.candidate_id === candidateId);
    if (!candidate) return;
    let drawer = $('forge-drawer');
    if (!drawer) {
      drawer = document.createElement('div'); drawer.id = 'forge-drawer'; drawer.className = 'forge-drawer';
      document.body.appendChild(drawer);
    }
    drawer.innerHTML = '<div class="forge-drawer-inner"><div class="forge-drawer-head"><span>Policy recommendation</span>'
      + '<button type="button" class="forge-drawer-close">×</button></div><div class="forge-drawer-body">'
      + policyRecommendationHtml(candidate) + '</div></div>';
    drawer.classList.add('open');
    drawer.querySelector('.forge-drawer-close')?.addEventListener('click', closeModelDrawer);
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
      + twinAdvancedHtml(data)
    );
  }

  function twinAdvancedHtml(data) {
    const payload = data.twinSettings || {};
    const settings = payload.settings || {};
    const profiles = (data.twinProfiles || {}).profiles || [];
    const settingRows = Object.keys(settings).sort().map((key) => (
      '<div class="forge-kv"><span>' + escapeHtml(key) + '</span><b>'
      + escapeHtml(String(settings[key])) + '</b></div>'
    )).join('');
    const profileRows = profiles.map((profile) => (
      '<div class="forge-twin-profile"><b>' + escapeHtml(profile.model_id || 'unknown') + '</b><span>'
      + escapeHtml(profile.provider_id || 'unknown') + ' · samples ' + escapeHtml(profile.sample_count ?? 0)
      + '</span></div>'
    )).join('');
    return '<details class="forge-adv" open><summary>Twin Settings</summary>'
      + '<div class="forge-hint">Read-only snapshot through the Forge Twin facade. Reversible: '
      + escapeHtml(String(payload.reversible === true)) + '.</div>'
      + (settingRows || '<div class="forge-empty">Twin settings unavailable.</div>')
      + '<div class="forge-card-title forge-twin-subtitle">Capability profiles</div>'
      + (profileRows || '<div class="forge-empty">No Twin profiles.</div>') + '</details>'
      + '<details class="forge-adv" open><summary>Read-only Twin Inspector</summary>'
      + '<div class="forge-twin-inspector-grid">'
      + '<form data-twin-context-form><div class="forge-card-title">Context slice</div>'
      + '<input class="forge-input" name="project_id" placeholder="project id" required>'
      + '<input class="forge-input" name="objective" placeholder="objective" required>'
      + '<select class="forge-select" name="phase"><option>planning</option><option>generation</option>'
      + '<option>verification</option><option>repair</option></select>'
      + '<input class="forge-input" name="target_refs" placeholder="target refs (comma separated)">'
      + '<button class="forge-run-btn" type="submit">Inspect context</button></form>'
      + '<form data-twin-impact-form><div class="forge-card-title">Impact</div>'
      + '<input class="forge-input" name="project_id" placeholder="project id" required>'
      + '<input class="forge-input" name="changed_refs" placeholder="changed refs (comma separated)" required>'
      + '<input class="forge-input" name="change_kind" value="edit" placeholder="change kind" required>'
      + '<button class="forge-run-btn" type="submit">Inspect impact</button></form></div>'
      + '<pre class="forge-twin-result" data-twin-result>Inspector has not run. No apply or execute action is exposed.</pre>'
      + '</details>';
  }

  function wireAdvanced(content) {
    content.querySelectorAll('[data-stage]').forEach((sel) => {
      sel.addEventListener('change', () => changeStageMode(sel.getAttribute('data-stage'), sel.value));
    });
    content.querySelector('[data-twin-context-form]')?.addEventListener('submit', (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      runTwinInspection(content, '/twin/inspect/context', {
        project_id: form.elements.project_id.value,
        objective: form.elements.objective.value,
        phase: form.elements.phase.value,
        target_refs: commaValues(form.elements.target_refs.value),
        token_budget: 4000,
      });
    });
    content.querySelector('[data-twin-impact-form]')?.addEventListener('submit', (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      runTwinInspection(content, '/twin/inspect/impact', {
        project_id: form.elements.project_id.value,
        changed_refs: commaValues(form.elements.changed_refs.value),
        change_kind: form.elements.change_kind.value,
      });
    });
  }

  function commaValues(value) {
    return String(value || '').split(',').map((item) => item.trim()).filter(Boolean);
  }

  async function runTwinInspection(content, path, payload) {
    const output = content.querySelector('[data-twin-result]');
    if (output) output.textContent = 'Inspecting read-only Twin evidence...';
    try {
      const result = await api(path, { method: 'POST', body: JSON.stringify(payload) });
      if (output) output.textContent = JSON.stringify(result, null, 2);
    } catch (err) {
      if (output) output.textContent = 'Twin inspection unavailable: ' + (err && err.message ? err.message : 'error');
    }
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
      // Providers & status moved here from the removed Overview tab (config is the natural home).
      + '<div class="forge-card">'
      + '<div class="forge-card-title">Providers & status</div>'
      + '<div class="forge-kv"><span>Forge</span><b>' + escapeHtml((data.status && data.status.forge_enabled) ? 'On' : 'Off (legacy primary)') + '</b></div>'
      + '<div class="forge-kv"><span>Source mode</span><b>' + escapeHtml((data.status || {}).source_mode || '') + '</b></div>'
      + '<div class="forge-kv"><span>Profiles</span><b>' + escapeHtml(String((data.status || {}).profile_count || 0)) + '</b></div>'
      + ((data.providers || []).map(providerCard).join('') || '<div class="forge-empty">No providers registered.</div>')
      + '</div>'
    );
  }

  function wireSettings(content) {
    content.querySelector('[data-settings-save]')?.addEventListener('click', () => saveSettings(content));
    content.querySelectorAll('[data-provider-probe]').forEach((btn) => {
      btn.addEventListener('click', () => probeProvider(btn.getAttribute('data-provider-probe')));
    });
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

  function twinAssistHtml() {
    const report = state.twinAssist.result;
    const readiness = state.twinAssist.readiness;
    const rtpolicy = state.twinAssist.runtimePolicy;
    const modelProfile = state.twinAssist.modelProfile;
    const rows = report ? (report.comparisons || []).map((item, index) => {
      const baseline = item.baseline && item.baseline.score != null ? item.baseline.score : 'unavailable';
      const best = item.best_score != null ? item.best_score : 'unavailable';
      const lift = item.lift != null ? item.lift : 'unavailable';
      return '<tr><td>' + escapeHtml(item.case_id) + '</td><td>' + escapeHtml(baseline) + '</td><td>' + escapeHtml(best)
        + '</td><td>' + escapeHtml(lift) + '</td><td>' + escapeHtml(item.best_assist_mode || 'unavailable')
        + '</td><td>' + (item.harm_detected ? '<span class="forge-warn-pill">harm</span>' : 'no')
        + '</td><td><button class="forge-probe-btn" data-twin-detail="' + index + '">Detail</button></td></tr>';
    }).join('') : '';
    const subtab = state.twinAssist.subtab || 'evaluation';

    // Sub-section 1: Evaluation (read-only). The run is now part of the single Benchmark action;
    // there is no separate Twin-eval button. Results render here and inline under Benchmark.
    const evaluationSection = '<div class="forge-card"><div class="forge-card-title">Twin Assist Evaluation</div>'
      + '<div class="forge-hint">Twin評価は Benchmark の「Run benchmark + 注入スイープ + Twin評価」で一括実行されます。'
      + 'ここは結果の参照専用です（ファイル適用や本番ルーティングは変更しません）。</div></div>'
      + (report ? '<div class="forge-card"><div class="forge-card-title">Results</div><div class="forge-kv"><span>Run</span><b>' + escapeHtml(report.run_id) + '</b></div>'
        + '<div class="forge-table-wrap"><table><thead><tr><th>case</th><th>baseline</th><th>assisted</th><th>lift</th><th>best mode</th><th>harm</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div></div>'
        + '<div class="forge-card"><div class="forge-card-title">Assist Effect (補助有無)</div>'
        + '<div class="forge-hint">Baseline vs Twin-assisted score per case — the visible Twin effect.</div>'
        + assistEffectRadarHtml(report.comparisons) + '</div>'
        : '<div class="forge-card"><div class="forge-empty">まだ評価結果がありません。Benchmark タブで実行してください。</div></div>')
      + '<div id="forge-twin-detail" class="forge-twin-result" style="display:none"></div>';

    // Sub-section 2: Readiness.
    const readinessSection = (readiness ? '<div class="forge-card"><div class="forge-card-title">Twin Readiness</div><div class="forge-kv"><span>score</span><b>' + escapeHtml(readiness.overall_score == null ? 'unavailable' : readiness.overall_score) + '</b></div><div class="forge-kv"><span>level</span><b>' + escapeHtml(readiness.readiness_level) + '</b></div><div class="forge-kv"><span>max assist</span><b>' + escapeHtml(readiness.recommended_max_assist_mode) + '</b></div></div>'
      : '<div class="forge-card"><div class="forge-card-title">Twin Readiness</div><div class="forge-empty">Run a Twin Assist evaluation to populate Twin readiness.</div></div>');

    // Sub-section 3: Runtime Policy Preview.
    const runtimePolicySection = '<div class="forge-card"><div class="forge-card-title">Runtime Policy Preview</div>'
      + '<div class="forge-hint">Preview why this model/task/change-class would get a route/method/Twin injection. Advisory; does not change production routing.</div>'
      + '<label class="forge-label">Change class<select id="forge-rtpolicy-change" class="forge-select">' + ['trivial','micro','small','medium','large','critical','greenfield'].map((c) => '<option value="' + c + '"' + (c === 'medium' ? ' selected' : '') + '>' + c + '</option>').join('') + '</select></label>'
      + '<label class="forge-check"><input type="checkbox" id="forge-rtpolicy-optimal" checked>optimal routing enabled</label>'
      + '<button id="forge-rtpolicy-run" class="forge-run-btn">Preview Runtime Policy</button>'
      + (rtpolicy ? '<div class="forge-kv"><span>selection mode</span><b>' + escapeHtml(rtpolicy.selection_mode) + '</b></div>'
        + '<div class="forge-kv"><span>optimal routing enabled</span><b>' + escapeHtml(String(rtpolicy.optimal_routing_enabled)) + '</b></div>'
        + '<div class="forge-kv"><span>profile available</span><b>' + escapeHtml(String(rtpolicy.profile_available)) + '</b></div>'
        + '<div class="forge-kv"><span>route fitness applied</span><b>' + escapeHtml(String(rtpolicy.route_fitness_applied)) + '</b></div>'
        + '<div class="forge-kv"><span>route</span><b>' + escapeHtml(rtpolicy.fallback_recommendation.route) + '</b></div>'
        + '<div class="forge-kv"><span>method variant</span><b>' + escapeHtml(rtpolicy.fallback_recommendation.method_variant) + '</b></div>'
        + '<div class="forge-kv"><span>method fallbacks</span><b>' + escapeHtml((rtpolicy.fallback_recommendation.method_fallbacks || []).join(', ')) + '</b></div>'
        + '<div class="forge-kv"><span>twin injection level</span><b>' + escapeHtml(String(rtpolicy.fallback_recommendation.twin_injection_level)) + '</b></div>'
        + '<div class="forge-kv"><span>instruction style</span><b>' + escapeHtml(rtpolicy.fallback_recommendation.instruction_style) + '</b></div>'
        + '<div class="forge-kv"><span>why selected</span><b>' + escapeHtml(rtpolicy.fallback_recommendation.reason) + '</b></div>' : '')
      + '</div>'
      // Benchmark capability that drives the route/method/injection above — shown together
      // so "benchmark -> Twin injection / route / method" is one consolidated view.
      + '<div class="forge-card"><div class="forge-card-title">Benchmark capability</div>'
      + '<div class="forge-hint">The benchmark profile these route/method/injection recommendations are derived from.</div>'
      + ((modelProfile && modelProfile.available && modelProfile.capability_profile)
        ? '<div class="forge-kv"><span>mode</span><b>' + escapeHtml(modelProfile.capability_profile.mode) + '</b></div>'
          + Object.keys(modelProfile.capability_profile.capability_scores || {}).sort().map((dim) =>
              '<div class="forge-kv"><span>' + escapeHtml(dim) + '</span><b>' + scoreBar(modelProfile.capability_profile.capability_scores[dim]) + '</b></div>'
            ).join('')
          + (((modelProfile.capability_profile.known_weaknesses || []).length)
              ? '<div class="forge-kv"><span>known weaknesses</span><b>' + escapeHtml(modelProfile.capability_profile.known_weaknesses.join(', ')) + '</b></div>' : '')
        : '<div class="forge-empty">No benchmark profile for this model yet. Run a benchmark, then preview to see the derived route/method/injection.</div>')
      + '</div>';

    // One coherent Twin Assist tab with a sub-navigation instead of a long card stack.
    const subtabs = [['evaluation', 'Evaluation'], ['readiness', 'Readiness'], ['runtime-policy', 'Runtime Policy']];
    const subnav = '<div class="forge-subnav">' + subtabs.map(([id, label]) =>
      '<button type="button" class="forge-tab' + (id === subtab ? ' active' : '') + '" data-twin-subtab="' + id + '">' + label + '</button>'
    ).join('') + '</div>';
    const activeSection = subtab === 'readiness' ? readinessSection
      : subtab === 'runtime-policy' ? runtimePolicySection : evaluationSection;
    return '<div class="forge-card-title forge-section-title">Twin Assist</div>' + subnav + activeSection;
  }

  async function previewRuntimePolicy() {
    // Use the model selected in Benchmark (the Twin run form was removed; everything is driven there).
    const body = {
      provider_id: runtimeProviderId() || 'local_openai_compatible',
      model_id: state.bench.model,
      change_class: $('forge-rtpolicy-change').value,
      optimal_routing: $('forge-rtpolicy-optimal').checked,
    };
    setStatus('Previewing runtime generation policy…');
    state.twinAssist.runtimePolicy = await api('/atlas-generation-policy/preview', { method: 'POST', body: JSON.stringify(body) });
    // Pull the benchmark capability the policy derives from, so both are shown together.
    try {
      state.twinAssist.modelProfile = await api('/evaluation/model-profile?provider_id='
        + encodeURIComponent(body.provider_id) + '&model_id=' + encodeURIComponent(body.model_id));
    } catch (_e) { state.twinAssist.modelProfile = null; }
    setStatus('Runtime policy preview ready', 'ok');
    renderActive();
  }

  function wireTwinAssist(content) {
    content.querySelectorAll('[data-twin-subtab]').forEach((btn) => btn.addEventListener('click', () => {
      state.twinAssist.subtab = btn.getAttribute('data-twin-subtab');
      renderActive();
    }));
    content.querySelector('#forge-rtpolicy-run')?.addEventListener('click', () => previewRuntimePolicy().catch((err) => setStatus('Runtime policy preview failed: ' + err.message, 'error')));
    content.querySelectorAll('[data-twin-detail]').forEach((button) => button.addEventListener('click', () => {
      const detail = $('forge-twin-detail');
      detail.style.display = 'block';
      detail.textContent = JSON.stringify(state.twinAssist.result.comparisons[Number(button.getAttribute('data-twin-detail'))], null, 2);
    }));
  }

  // Overview and the standalone Twin Assist tab were removed: status/providers live in
  // Settings, and Twin Assist now runs as a section inside Benchmark (the evaluation hub).
  const VIEWS = {
    skills: skillsHtml, benchmark: benchmarkHtml,
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
      + '<div class="forge-drawer-body">' + rows
      + '<div class="forge-card-title forge-twin-subtitle">Recommended Twin Assist</div>'
      + '<div class="forge-kv"><span>mode</span><b>' + escapeHtml(profile.recommended_twin_assist_mode || 'unavailable') + '</b></div>'
      + '<div class="forge-kv"><span>injection level</span><b>' + escapeHtml(profile.recommended_twin_injection_level == null ? 'unavailable' : profile.recommended_twin_injection_level) + '</b></div>'
      + '</div>'
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
    const builder = VIEWS[state.tab] || benchmarkHtml;
    content.innerHTML = builder(state.data);
    if (state.tab === 'skills') {
      content.querySelectorAll('[data-model]').forEach((row) => {
        row.addEventListener('click', () => openModelDrawer(row.getAttribute('data-model')));
      });
    } else if (state.tab === 'benchmark') {
      // Benchmark is the evaluation hub: a sub-nav switches between capability Benchmark and
      // Twin Assist (which runs as a section here, not a standalone tab).
      content.querySelectorAll('[data-bench-subtab]').forEach((btn) => btn.addEventListener('click', () => {
        state.bench.subtab = btn.getAttribute('data-bench-subtab');
        renderActive();
      }));
      if ((state.bench.subtab || 'benchmark') === 'twin-assist') {
        wireTwinAssist(content);
      } else {
        wireBenchmark(content, state.data);
      }
    } else if (state.tab === 'arena') {
      content.querySelectorAll('[data-candidate-detail]').forEach((btn) => {
        btn.addEventListener('click', () => openCandidateDrawer(btn.getAttribute('data-candidate-detail'), 'All'));
      });
      content.querySelectorAll('[data-policy-recommendation]').forEach((btn) => {
        btn.addEventListener('click', () => openPolicyRecommendationDrawer(btn.getAttribute('data-policy-recommendation')));
      });
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
      const data = { status, providers: [], loadouts: [], profiles: [], leaderboard: [], settings: {}, openrouterCatalog: null, localModels: [], lmStudioCatalog: null, localPortCatalog: null, twinSettings: {}, twinProfiles: { profiles: [], count: 0 } };
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
      try { data.twinSettings = await api('/twin/settings'); } catch (_e) {}
      try { data.twinProfiles = await api('/twin/profiles'); } catch (_e) {}
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
    _anvilConfigFormHtml: renderAnvilConfigForm,
    _arenaHtml: arenaHtml,
    _twinAssistHtml: twinAssistHtml,
    _radarHtml: radarHtml,
    _fallbackGraphHtml: fallbackGraphHtml,
    _methodComparisonHtml: methodComparisonHtml,
    _policyRecommendationHtml: policyRecommendationHtml,
    _advancedHtml: advancedHtml,
    _twinAdvancedHtml: twinAdvancedHtml,
    _loadoutsHtml: loadoutsHtml,
    _settingsHtml: settingsHtml,
    _runBenchmark: runBenchmark,
    _state: state,
  };
})();
