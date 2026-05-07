// ── SETTINGS MODAL ──
function openSettings() {
  document.getElementById('settings-modal').classList.add('open');
  loadSettingsFromDb();       // 開くたびにDBから最新値を反映
  loadOrchestrationSettings();
  loadGhRepoConfig();         // GitHub設定も読み込む
  refreshEnsembleVramStatus();
  if (ensembleVramTimer) clearInterval(ensembleVramTimer);
  ensembleVramTimer = setInterval(refreshEnsembleVramStatus, 5000);
  _ttsInitSettingsUI();       // TTS設定をフォームに反映
  _echoInitSettingsUI();      // Echoモード設定をフォームに反映
  applyUiFontSettings();      // UI文字サイズをフォームと画面に反映
}
function closeSettings() {
  document.getElementById('settings-modal').classList.remove('open');
  if (ensembleVramTimer) {
    clearInterval(ensembleVramTimer);
    ensembleVramTimer = null;
  }
}


// ── SETTINGS UI HELPERS ──
function applyOrchFeatureModeUi() {
  const mode = document.getElementById('orch-feature-mode')?.value || 'model_orchestration';
  const note = document.getElementById('orch-feature-note');
  const orchBody = document.getElementById('orch-settings-body');
  const ensWrap = document.getElementById('ensemble-settings-wrap');
  const ensControls = [
    document.getElementById('ensemble-execution-mode'),
    document.getElementById('ensemble-auto-switch'),
    document.querySelector('button[onclick="saveEnsembleSettings(true)"]'),
    document.querySelector('button[onclick="refreshEnsembleVramStatus()"]')
  ].filter(Boolean);
  const orchControls = [
    document.getElementById('orch-policy'),
    document.getElementById('orch-quality-enabled')
  ].filter(Boolean);
  if (mode === 'ensemble') {
    if (note) note.textContent = 'Ensembleモード選択中。現時点ではModel Orchestrationが推奨です。';
    if (orchBody) orchBody.style.opacity = '0.45';
    orchControls.forEach(el => el.disabled = true);
    if (ensWrap) ensWrap.style.opacity = '1';
    ensControls.forEach(el => el.disabled = false);
  } else {
    if (note) note.textContent = 'Model Orchestrationモード: 既存の昇格再実行ロジックを使用します。';
    if (orchBody) orchBody.style.opacity = '1';
    orchControls.forEach(el => el.disabled = false);
    if (ensWrap) ensWrap.style.opacity = '0.45';
    ensControls.forEach(el => el.disabled = true);
  }
}

function updateCtxLabel(val) {
  const n = parseInt(val);
  const el = document.getElementById('ctx-label');
  if (el) el.textContent = n.toLocaleString();
}

function applySearchUI(enabled) {
  searchEnabled = enabled;
  const chk = document.getElementById('search-chk');
  const label = document.getElementById('search-label');
  if (chk) chk.checked = enabled;
  if (label) label.textContent = enabled ? 'ON' : 'OFF';
}

function applyStreamingUI(enabled) {
  streamingEnabled = enabled;
  const chk = document.getElementById('streaming-chk');
  const label = document.getElementById('streaming-label');
  if (chk) chk.checked = enabled;
  if (label) label.textContent = enabled ? 'ON' : 'OFF';
}

window.openSettings = openSettings;
window.closeSettings = closeSettings;
window.applyOrchFeatureModeUi = applyOrchFeatureModeUi;
window.updateCtxLabel = updateCtxLabel;
window.applySearchUI = applySearchUI;
window.applyStreamingUI = applyStreamingUI;
