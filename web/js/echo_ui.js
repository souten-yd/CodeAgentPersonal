(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  function byId(id) { return root.document ? root.document.getElementById(id) : null; }
  function setText(id, value) { const el = byId(id); if (el) el.textContent = value || ""; }
  function setHtml(id, value) { const el = byId(id); if (el) el.innerHTML = value || ""; }
  function setDisabled(id, disabled) { const el = byId(id); if (el) el.disabled = !!disabled; }
  function setDisplay(id, display) { const el = byId(id); if (el) el.style.display = display || ""; }
  function setEchoStatus(message) { setText('echo-status', message || ''); }
  function setEchoConnectionState(state) {
    const el = byId('echo-conn-status');
    if (!el) return;
    const map = {
      connected: ['● 接続済み', 'echo-conn-ok'], disconnected: ['● 未接続', 'echo-conn-off'],
      reconnecting: ['● 再接続中…', 'echo-conn-off'], error: ['● 接続エラー', 'echo-conn-err'],
    };
    const pair = map[state] || map.disconnected; el.textContent = pair[0]; el.className = pair[1];
  }
  function setEchoVaultInfo(message, tone) {
    const el = byId('echo-vault-info'); if (!el) return;
    if (!message) { el.style.display = 'none'; el.textContent = ''; return; }
    el.style.display = ''; el.textContent = message;
    if (tone === 'ok') { el.style.borderColor = 'var(--green,#4caf50)'; el.style.background = 'rgba(76,175,80,.12)'; }
    else { el.style.borderColor = 'var(--amber)'; el.style.background = 'rgba(255,184,0,.12)'; }
  }
  function renderStyleBertVits2Models(opts) {
    const sel = byId('tsasr-style-bert-vits2-model-sel'); if (!sel) return null;
    const models = Array.isArray(opts?.models) ? opts.models : [];
    const details = Array.isArray(opts?.details) ? opts.details : [];
    const current = String(opts?.selectedModel || '');
    const defaultModel = String(opts?.defaultModel || 'jvnv-F1-jp');
    const resolved = Array.from(new Set([defaultModel, ...models.filter(Boolean)]));
    const detailMap = new Map(); details.forEach((d)=>{ if(d&&d.model) detailMap.set(d.model,d); });
    sel.innerHTML = '';
    resolved.forEach((modelId)=>{ const meta = detailMap.get(modelId)||{}; const opt = root.document.createElement('option'); opt.value=modelId; opt.textContent=meta.is_jp_extra?`${modelId} (JP-Extra / JP only)`:modelId; if (modelId===current) opt.selected=true; sel.appendChild(opt); });
    if (!resolved.includes(current)) sel.value = defaultModel;
    setText('tsasr-style-bert-vits2-status', resolved.length ? `モデル ${models.length} 件` : 'モデルがありません');
    return sel.value;
  }
  function renderEchoVaultSessions(html) { setHtml('echovault-list', html || ''); }
  const api = {name:'echo_ui',loaded:true,byId,setText,setHtml,setDisabled,setDisplay,setEchoStatus,setEchoConnectionState,setEchoVaultInfo,renderEchoVaultSessions,renderStyleBertVits2Models};
  registry.echoUi = Object.assign(registry.echoUi || {}, api);
  root.EchoUI = Object.assign(root.EchoUI || {}, api);
}());
