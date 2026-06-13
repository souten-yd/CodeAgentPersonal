// ── PANEL TABS ──
function switchTab(name, options = {}) {
  if (options.persist !== false && typeof saveLastSubtab === 'function') {
    // Persist the subtab under the active mode. Forge (Models/ASR/TTS) and Nexus (Memory/Skill/Log)
    // consolidate panels, so their subtabs must be remembered under their own mode (not coerced to
    // 'chat') to restore correctly on re-entry.
    const persistMode = mode === 'echo' ? 'echo'
      : mode === 'forge' ? 'forge'
      : mode === 'nexus' ? 'nexus'
      : 'chat';
    saveLastSubtab(persistMode, name);
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

