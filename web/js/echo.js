// ── ECHO / ASR / TTS DISPLAY HELPERS ──
// Display-only Echo/ASR/TTS DOM helpers split out of ui.html.
// Keep recording, playback, synthesize/transcribe API calls, Echo loop, SBV2/model load, and settings save logic in ui.html.

function syncEchoTranslateUi() {
  const enabled = !!echo.ttsTranslateEnabled;
  const toolbarToggle = document.getElementById('echo-toolbar-translate-enable');
  const toolbarLabel = document.getElementById('echo-toolbar-translate-enable-label');
  const panelChk = document.getElementById('tts-translate-enable');
  const panelLbl = document.getElementById('tts-translate-enable-label');
  if (toolbarToggle) {
    toolbarToggle.classList.toggle('enabled', enabled);
    toolbarToggle.classList.toggle('off', !enabled);
    // 以前のUI実装由来のインライン色が残っていても、状態に応じたCSSを優先させる
    toolbarToggle.style.background = '';
    toolbarToggle.style.borderColor = '';
    toolbarToggle.style.color = '';
  }
  if (toolbarLabel) toolbarLabel.textContent = enabled ? 'ON' : 'OFF';
  if (panelChk) panelChk.checked = enabled;
  if (panelLbl) panelLbl.textContent = enabled ? 'ON' : 'OFF';
  _syncEchoMinutesButtonUi();
}

function _syncEchoMinutesButtonUi() {
  const btn = document.getElementById('echo-toolbar-generate-minutes');
  if (!btn) return;
  const busy = !!echo._isStoppingOrSaving;
  btn.disabled = busy;
  const enabled = !!echo.autoGenerateMinutes && !busy;
  btn.classList.toggle('enabled', enabled);
  btn.classList.toggle('off', !enabled);
  btn.style.background = '';
  btn.style.borderColor = '';
  btn.style.color = '';
  if (busy) {
    btn.textContent = '⟳ Minutes 処理中...';
    btn.title = '保存・Minutes生成処理中です';
  } else {
    btn.textContent = echo.autoGenerateMinutes ? '📝 Minutes ON' : '📝 Minutes OFF';
    btn.title = echo.autoGenerateMinutes ? '停止時にMinutesを作成します（クリックでOFF）' : '停止時のMinutes作成を無効化中（クリックでON）';
  }
}

function _renderAsrRuntimeUi() {
  const engineWrap = document.getElementById('asr-engine-wrap');
  const deviceWrap = document.getElementById('asr-device-wrap');
  const line1 = document.getElementById('asr-runtime-line1');
  const line2 = document.getElementById('asr-runtime-line2');
  const warns = document.getElementById('asr-runtime-warnings');
  const runpod = !!asrRuntimeConfig.is_runpod;
  const windows = !!asrRuntimeConfig.is_windows;
  if (engineWrap) engineWrap.style.display = (!runpod && windows) ? '' : 'none';
  if (deviceWrap) deviceWrap.style.display = runpod ? '' : 'none';
  if (line1) line1.textContent = `ASR: ${asrRuntimeConfig.effective_engine || 'faster_whisper'} / ${asrRuntimeConfig.model || 'large-v3-turbo'} (${asrRuntimeConfig.effective_backend || 'cpu'})`;
  if (line2) line2.textContent = (asrRuntimeConfig.ffmpeg_available ? 'input conversion: ffmpeg available' : 'input conversion: ffmpeg missing');
  if (warns) warns.innerHTML = ((asrRuntimeConfig.warnings || []).map(w => `⚠ ${esc(String(w))}`).join('<br>'));
}

function _echoSetStatus(text) {
  if (window.EchoUI?.setEchoStatus) window.EchoUI.setEchoStatus(text);
  else { const el = document.getElementById('echo-status'); if (el) el.textContent = text; }
  _echoSyncBusyStatus(text || '');
  _syncEchoMinutesButtonUi();
}

function _echoSyncBusyStatus(statusText = '') {
  const busyEl = document.getElementById('echo-busy-status');
  if (!busyEl) return;
  const busyNow = !!echo.recording
    || !!echo._isStoppingOrSaving
    || echo._connState === 'reconnecting'
    || /(文字起こし中|保存中|議事録作成中|再接続中)/.test(statusText || '');
  busyEl.textContent = busyNow ? 'busy' : 'idle';
  busyEl.classList.toggle('busy', busyNow);
  busyEl.title = busyNow ? `処理中: ${statusText || '-'}` : '待機中';
}

function _echoSetConn(state) {
  // state: 'connected' | 'disconnected' | 'reconnecting' | 'error'
  if (window.EchoUI?.setEchoConnectionState) window.EchoUI.setEchoConnectionState(state);
  const el = document.getElementById('echo-conn-status');
  if (!el) return;
  const map = {
    connected:    ['● 接続済み', 'echo-conn-ok'],
    disconnected: ['● 未接続',   'echo-conn-off'],
    reconnecting: ['● 再接続中…','echo-conn-off'],
    error:        ['● 接続エラー','echo-conn-err'],
  };
  const [text, cls] = map[state] || map.disconnected;
  echo._connState = state;
  if (!window.EchoUI?.setEchoConnectionState) { el.textContent = text; el.className = cls; }
  if (state === 'disconnected' && !echo._isStoppingOrSaving && !echo.recording) {
    _echoVaultSetInfo('');
  }
  _echoSyncBusyStatus(document.getElementById('echo-status')?.textContent || '');
}

function _echoUpdateSentenceCount() {
  const el = document.getElementById('echo-sentence-count');
  if (el) el.textContent = `出力回数: ${echo.sentences.length}`;
}

function _echoUpdateDuration() {
  if (!echo.startTime) return;
  const sec = Math.floor((Date.now() - echo.startTime) / 1000);
  const mm = String(Math.floor(sec / 60)).padStart(2, '0');
  const ss = String(sec % 60).padStart(2, '0');
  const el = document.getElementById('echo-duration');
  if (el) el.textContent = mm + ':' + ss;
}

function _echoRefreshStatusLine() {
  const el = document.getElementById('echo-status');
  if (!el) return;
  const outMap = {same:'Same',ja:'Japanese',en:'English'};
  el.textContent = `Ready · ASR: ${echo.asrLanguage || echo.asrLang || 'auto'} · Output: ${outMap[echo.outputLanguage || 'same'] || 'Same'} · TTS: ${echo.ttsLanguage || 'auto'}`;
}

function _echoUploadSetStatus(msg = '', tone = 'info', showRetry = false, transcriptFilename = '') {
  const el = document.getElementById('echo-upload-status');
  if (!el) return;
  if (!msg) {
    el.style.display = 'none';
    el.textContent = '';
    return;
  }
  el.style.display = '';
  const safe = esc(msg);
  const retryBtn = showRetry && transcriptFilename
    ? `<button onclick="_echoVaultGenerateMinutes(decodeURIComponent('${encodeURIComponent(transcriptFilename)}'))" style="margin-left:8px;font-size:10px;padding:3px 7px;border:1px solid var(--accent-border);background:var(--accent-bg);color:var(--accent);border-radius:4px;cursor:pointer">議事録を再試行</button>`
    : '';
  el.innerHTML = `<span>${safe}</span>${retryBtn}`;
  if (tone === 'error') {
    el.style.borderColor = 'var(--red)';
    el.style.background = 'rgba(255,77,109,.12)';
    el.style.color = 'var(--red)';
  } else if (tone === 'ok') {
    el.style.borderColor = 'var(--green,#4caf50)';
    el.style.background = 'rgba(76,175,80,.12)';
    el.style.color = 'var(--text2)';
  } else {
    el.style.borderColor = 'var(--border)';
    el.style.background = 'var(--bg1)';
    el.style.color = 'var(--text2)';
  }
}

function _echoVaultSetInfo(msg = '', tone = 'warn') {
  if (window.EchoUI?.setEchoVaultInfo) return window.EchoUI.setEchoVaultInfo(msg, tone);
  const el = document.getElementById('echo-vault-info');
  if (!el) return;
  if (!msg) { el.style.display = 'none'; el.textContent = ''; return; }
  el.style.display = ''; el.textContent = msg;
  if (tone === 'ok') { el.style.borderColor = 'var(--green,#4caf50)'; el.style.background = 'rgba(76,175,80,.12)'; }
  else { el.style.borderColor = 'var(--amber)'; el.style.background = 'rgba(255,184,0,.12)'; }
}

window.syncEchoTranslateUi = syncEchoTranslateUi;
window._syncEchoMinutesButtonUi = _syncEchoMinutesButtonUi;
window._renderAsrRuntimeUi = _renderAsrRuntimeUi;
window._echoSetStatus = _echoSetStatus;
window._echoSyncBusyStatus = _echoSyncBusyStatus;
window._echoSetConn = _echoSetConn;
window._echoUpdateSentenceCount = _echoUpdateSentenceCount;
window._echoUpdateDuration = _echoUpdateDuration;
window._echoRefreshStatusLine = _echoRefreshStatusLine;
window._echoUploadSetStatus = _echoUploadSetStatus;
window._echoVaultSetInfo = _echoVaultSetInfo;
