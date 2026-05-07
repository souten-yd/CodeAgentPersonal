window.KASANE_UI_BOOTSTRAP_LOADED = true;

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

window.openSettings = openSettings;
window.closeSettings = closeSettings;
