// ── PANEL TABS ──
function switchTab(name, options = {}) {
  if (options.persist !== false && typeof saveLastSubtab === 'function') {
    // Persist the subtab under the active mode. Forge consolidates Models/ASR/TTS, so its subtabs
    // must be remembered under 'forge' (not coerced to 'chat') to restore correctly on re-entry.
    saveLastSubtab(mode === 'echo' ? 'echo' : (mode === 'forge' ? 'forge' : 'chat'), name);
  }
  _setPanelTabActiveButton(name);
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-'+name)?.classList.add('active');
  if (name === 'preview') refreshFileBrowser();
  if (name === 'files') refreshProjectFileManager();
  if (name === 'skills') refreshSkills();
  if (name === 'memory') refreshMemory();
  if (name === 'models') { refreshModelDb(); refreshModelRoles(); }
  if (name === 'vault') refreshEchoVault();
  if (name === 'asr') refreshAsrTab();
  if (name === 'tts') refreshTtsTab();
}

window.switchTab = switchTab;

