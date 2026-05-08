// ── PANEL TABS ──
function switchTab(name) {
  if (typeof saveLastSubtab === 'function') saveLastSubtab(mode === 'echo' ? 'echo' : 'chat', name);
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

