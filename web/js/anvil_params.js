/*
 * Anvil per-model llama-server parameters — single source of truth.
 *
 * Both UIs that edit a registered model's parameters render from this one definition:
 *   - the Forge "⚙ 詳細設定" drawer (web/js/forge.js), and
 *   - the Models tab Anvil parameter modal (inline script in ui.html).
 * They have different call sites and markup styles, but the same Models DB columns, so the
 * field list + value conversions live here once: adding or changing a field updates both UIs
 * at the same time. The fields mirror the Models DB columns consumed by main.py's
 * _runtime_spec_from_row / register_atlas_llm_json_adapter.
 *
 * Field types:
 *   num / text -> pulldown of curated choices + 「カスタム…」 free input
 *   tri        -> 未指定 / ON / OFF
 * '' / -1 / null all mean 未指定 (the runtime manager omits the flag when launching).
 */
(function (root) {
  'use strict';

  const GROUPS = [
    { group: '基本', items: [
      { key: 'ctx_size', label: 'CTX (context length)', type: 'num', opts: [4096, 8192, 16384, 32768, 65536, 131072, 262144] },
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
    ] },
    { group: '思考 / 投機デコード', items: [
      { key: 'reasoning', label: 'reasoning (think)', type: 'text', opts: ['off', 'on', 'auto'] },
      { key: 'spec_type', label: 'spec-type (MTP)', type: 'text', opts: ['draft-mtp', 'draft-model'] },
      { key: 'spec_draft_n_max', label: 'spec-draft-n-max (先読み数)', type: 'num', opts: [1, 2, 3, 4] },
      { key: 'spec_draft_p_min', label: 'spec-draft-p-min', type: 'num', opts: [0.5, 0.75, 0.9] },
    ] },
    { group: 'サンプリング', items: [
      { key: 'temp', label: 'temp', type: 'num', opts: [0, 0.3, 0.7, 1.0] },
      { key: 'top_p', label: 'top-p', type: 'num', opts: [0.8, 0.9, 0.95, 1.0] },
      { key: 'top_k', label: 'top-k', type: 'num', opts: [0, 20, 40] },
      { key: 'min_p', label: 'min-p', type: 'num', opts: [0, 0.05, 0.1] },
      { key: 'presence_penalty', label: 'presence-penalty', type: 'num', opts: [0, 1.0, 1.5] },
      { key: 'repeat_penalty', label: 'repeat-penalty', type: 'num', opts: [1.0, 1.1] },
    ] },
    { group: '生成', items: [
      // Per-request generation cap (max_tokens), NOT a llama-server launch arg. Atlas codegen reads
      // this so large files aren't truncated at the default and then endlessly regenerated.
      { key: 'max_output_tokens', label: '出力トークン上限 (max_tokens)', type: 'num', opts: [2048, 4096, 8192, 16384, 32768, 65536, 131072] },
    ] },
  ];

  const FLAT = GROUPS.reduce((acc, g) => acc.concat(g.items), []);

  // Stored Models DB value -> input string. Sentinel -1 / null / '' -> '' (未指定).
  function storedToInput(field, raw) {
    if (field && field.type === 'text') return String(raw == null ? '' : raw);
    if (raw == null || raw === '' || Number(raw) === -1) return '';
    return String(raw);
  }

  // Input value -> PUT payload value. '' -> -1 for num/tri; trimmed string for text.
  function toPayloadValue(field, value) {
    if (field && field.type === 'text') return String(value == null ? '' : value).trim();
    if (value === '' || value == null) return -1;
    const n = Number(value);
    return Number.isFinite(n) ? n : -1;
  }

  root.AnvilParams = { GROUPS, FLAT, storedToInput, toPayloadValue };
})(typeof window !== 'undefined' ? window : globalThis);
