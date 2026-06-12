/*
 * Portal mode (PR-PPC-8..11) — top-level package catalog, run, data lifecycle.
 *
 * Portal never starts its own process runner: Run goes through the public
 * Portal runtime API which delegates to the already-tested Atlas Play runtime.
 * Untrusted imported packages are Run-blocked unless the user explicitly
 * acknowledges that v1 provides no OS isolation. Package Export never includes
 * runtime data (handled server-side).
 */
(function () {
  'use strict';
  const root = (typeof window !== 'undefined' ? window : globalThis);

  function $(id) { return document.getElementById(id); }
  function api() { return root.AtlasPipelineAPI || null; }

  const state = {
    activated: false,
    loading: false,
    packages: [],
    run: null,        // { playSessionId, installationId, reconnectToken, launchKind, runMode }
    pollTimer: null,
    heartbeatTimer: null,
  };

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
    ));
  }

  function setStatus(text, kind) {
    const el = $('portal-status');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('is-error', kind === 'error');
    el.classList.toggle('is-ok', kind === 'ok');
  }

  function formatBytes(bytes) {
    const n = Number(bytes || 0);
    if (!n) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let v = n;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
    return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
  }

  // Stable installation id per package identity so Current Data persists across runs.
  function installationIdFor(pkg) {
    return `inst-${pkg.package_id}-${pkg.version}`.replace(/[^A-Za-z0-9_.-]/g, '_');
  }

  function trustLabel(trust) {
    return ({
      trusted_local_capsule: 'Trusted (local Capsule)',
      verified_publisher_package: 'Verified publisher',
      untrusted_imported_package: 'Untrusted import',
    })[trust] || trust || 'unknown';
  }

  // ---- Catalog ----

  async function refreshCatalog() {
    if (state.loading) return;
    state.loading = true;
    setStatus('Loading catalog…');
    const resp = await api()?.listPortalCatalog?.();
    state.loading = false;
    if (!resp || !resp.ok) {
      setStatus('Failed to load catalog', 'error');
      return;
    }
    state.packages = (resp.data && resp.data.packages) || [];
    renderCatalog();
    setStatus(state.packages.length ? `${state.packages.length} package(s)` : 'No packages yet', 'ok');
  }

  function renderCatalog() {
    const host = $('portal-catalog');
    if (!host) return;
    if (!state.packages.length) {
      host.innerHTML = '<div class="portal-empty">パッケージがありません。Atlas の Capsule でビルドするか、右上の Import package で取り込んでください。</div>';
      return;
    }
    host.innerHTML = state.packages.map((pkg, idx) => renderCard(pkg, idx)).join('');
  }

  function renderCard(pkg, idx) {
    const manifest = pkg.manifest || null;
    const profiles = (manifest && manifest.launch_profiles) || [];
    const name = (manifest && manifest.name) || pkg.package_id;
    const trust = pkg.trust_state || 'unknown';
    const dataBytes = pkg.current_data_bytes || 0;
    const profileOptions = profiles.length
      ? profiles.map((p) => `<option value="${escapeHtml(p.profile_id)}"${p.profile_id === (manifest && manifest.default_profile_id) ? ' selected' : ''}>${escapeHtml(p.name || p.profile_id)} · ${escapeHtml(p.kind)}</option>`).join('')
      : '';
    const profileSelect = profiles.length
      ? `<select data-portal-profile="${idx}" aria-label="Launch profile">${profileOptions}</select>`
      : `<span class="portal-card-warning">起動プロファイル情報なし</span> <button type="button" class="portal-btn" data-portal-act="repair" data-idx="${idx}">マニフェスト修復</button>`;
    const untrusted = trust === 'untrusted_imported_package';
    return `
      <div class="portal-card" data-portal-card="${idx}">
        <div class="portal-card-top">
          <div class="portal-card-icon">📦</div>
          <div style="flex:1 1 auto;min-width:0">
            <div class="portal-card-id">${escapeHtml(name)}</div>
            <div class="portal-card-meta">${escapeHtml(pkg.package_id)} · v${escapeHtml(pkg.version)}</div>
            <div class="portal-card-meta">profiles: ${profiles.length} · data: ${formatBytes(dataBytes)}</div>
            <span class="portal-trust ${escapeHtml(trust)}">${escapeHtml(trustLabel(trust))}</span>
          </div>
        </div>
        <div class="portal-card-row">
          <label>Profile</label>${profileSelect}
        </div>
        <div class="portal-card-row">
          <label>Mode</label>
          <select data-portal-runmode="${idx}" aria-label="Run mode">
            <option value="continue_current_data">Continue current data</option>
            <option value="start_empty">Start empty</option>
            <option value="start_from_snapshot">Start from snapshot</option>
            <option value="ephemeral">Ephemeral</option>
          </select>
        </div>
        <div class="portal-card-row" data-portal-snaprow="${idx}" style="display:none">
          <label>Snapshot</label>
          <select data-portal-snapshot="${idx}" aria-label="Snapshot"></select>
        </div>
        ${untrusted ? `<label class="portal-card-warning"><input type="checkbox" data-portal-ack="${idx}"> 取り込みパッケージは v1 では OS 隔離されません。承知の上で実行する場合のみチェック。</label>` : ''}
        <div class="portal-card-actions">
          <button type="button" class="portal-btn primary" data-portal-act="run" data-idx="${idx}"${profiles.length ? '' : ' disabled'}>Run</button>
          <button type="button" class="portal-btn" data-portal-act="data" data-idx="${idx}">Data</button>
          <button type="button" class="portal-btn" data-portal-act="export" data-idx="${idx}">Export Package</button>
          <button type="button" class="portal-btn" data-portal-act="fork" data-idx="${idx}">Fork to Atlas</button>
          <button type="button" class="portal-btn danger" data-portal-act="uninstall" data-idx="${idx}">Uninstall</button>
          <button type="button" class="portal-btn danger" data-portal-act="delete-data" data-idx="${idx}">Delete Data</button>
        </div>
        <div class="portal-card-meta" data-portal-cardinfo="${idx}"></div>
      </div>`;
  }

  function cardInfo(idx, text, kind) {
    const el = document.querySelector(`[data-portal-cardinfo="${idx}"]`);
    if (!el) return;
    el.textContent = text || '';
    el.style.color = kind === 'error' ? 'var(--red)' : (kind === 'ok' ? 'var(--green)' : 'var(--text3)');
  }

  // ---- Import ----

  async function importPackage() {
    // Environment-appropriate folder picker (Windows drives / RunPod /workspace …)
    // instead of asking the user to type a server path. Falls back to a manual path
    // prompt if the browse API is unavailable.
    let archivePath = '';
    if (api()?.browsePortalImport) {
      archivePath = await pickImportArchive();
    } else {
      archivePath = root.prompt('取り込む .portal.zip のサーバー上のパスを入力してください') || '';
    }
    if (!archivePath || archivePath === UPLOAD_HANDLED) return;
    archivePath = archivePath.trim();
    setStatus('Preflighting archive…');
    const pre = await api()?.preflightPortalImport?.(archivePath);
    if (!pre || !pre.ok) {
      setStatus(`Preflight rejected: ${pre?.data?.error || pre?.code || 'invalid_archive'}`, 'error');
      return;
    }
    setStatus('Importing…');
    const resp = await api()?.importPortalPackage?.(archivePath);
    if (!resp || !resp.ok) {
      setStatus(`Import failed: ${resp?.data?.error || resp?.code || 'error'}`, 'error');
      return;
    }
    setStatus('Imported (untrusted)', 'ok');
    await refreshCatalog();
  }

  const BROWSE_ERROR_LABELS = {
    directory_not_found: 'フォルダが見つかりません',
    permission_denied: 'アクセス権がありません',
    directory_unreadable: 'フォルダを読み取れません',
    unsupported_archive_extension: '.zip / .portal.zip を選択してください',
    upload_too_large: 'ファイルが大きすぎます（上限 100MB）',
    empty_upload: 'ファイルが空です',
  };

  // Sentinel: the modal already handled an upload import, so importPackage must not
  // re-import a server path.
  const UPLOAD_HANDLED = 'portal:upload-handled';

  // Modal server-side folder browser. Resolves to the selected .portal.zip path, or
  // '' if the user cancels.
  function pickImportArchive() {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'portal-browse-overlay';
      const modal = document.createElement('div');
      modal.className = 'portal-browse-modal';
      overlay.appendChild(modal);

      const close = (value) => { overlay.remove(); document.removeEventListener('keydown', onKey); resolve(value || ''); };
      const onKey = (ev) => { if (ev.key === 'Escape') close(''); };
      document.addEventListener('keydown', onKey);
      overlay.addEventListener('click', (ev) => { if (ev.target === overlay) close(''); });

      const header = document.createElement('div');
      header.className = 'portal-browse-head';
      header.innerHTML = '<span>パッケージ (.portal.zip) を選択</span>';
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'portal-browse-close';
      closeBtn.textContent = '✕';
      closeBtn.addEventListener('click', () => close(''));
      header.appendChild(closeBtn);

      const rootsBar = document.createElement('div');
      rootsBar.className = 'portal-browse-roots';
      const pathBar = document.createElement('div');
      pathBar.className = 'portal-browse-path';
      const listEl = document.createElement('div');
      listEl.className = 'portal-browse-list';
      const footer = document.createElement('div');
      footer.className = 'portal-browse-foot';

      // Mobile-friendly: upload an archive straight from the device. The file input
      // is hidden; the button proxies clicks to it.
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.accept = '.zip,.portal.zip,application/zip';
      fileInput.style.display = 'none';
      fileInput.addEventListener('change', () => {
        const f = fileInput.files && fileInput.files[0];
        fileInput.value = '';
        if (f) doUpload(f);
      });
      const uploadBtn = document.createElement('button');
      uploadBtn.type = 'button';
      uploadBtn.className = 'portal-browse-upload';
      uploadBtn.textContent = '端末からアップロード';
      uploadBtn.addEventListener('click', () => fileInput.click());

      const manualBtn = document.createElement('button');
      manualBtn.type = 'button';
      manualBtn.className = 'portal-browse-manual';
      manualBtn.textContent = 'パスを手入力';
      manualBtn.addEventListener('click', () => {
        const manual = root.prompt('取り込む .portal.zip のサーバー上のパスを入力してください') || '';
        if (manual.trim()) close(manual.trim());
      });
      footer.append(fileInput, uploadBtn, manualBtn);

      async function doUpload(file) {
        if (!api()?.uploadPortalImport) return;
        const warn = '取り込むパッケージは未検証 (untrusted) として登録されます。実行には OS 分離がなく、明示的な同意が必要です。続行しますか？';
        if (root.confirm && !root.confirm(warn)) return;
        listEl.innerHTML = '<div class="portal-browse-loading">アップロード中…</div>';
        setStatus('アップロード中…');
        const resp = await api().uploadPortalImport(file);
        if (!resp || !resp.ok) {
          const code = resp?.data?.error || resp?.code || 'error';
          listEl.innerHTML = `<div class="portal-browse-error">アップロード失敗: ${escapeHtml(BROWSE_ERROR_LABELS[code] || code)}</div>`;
          setStatus(`Import failed: ${code}`, 'error');
          return;
        }
        setStatus('Imported (untrusted)', 'ok');
        await refreshCatalog();
        close(UPLOAD_HANDLED);
      }

      modal.append(header, rootsBar, pathBar, listEl, footer);
      document.body.appendChild(overlay);

      let currentPath = '';
      async function load(path) {
        listEl.innerHTML = '<div class="portal-browse-loading">読み込み中…</div>';
        const resp = await api().browsePortalImport(path || '');
        const d = (resp && resp.ok && resp.data) ? resp.data : null;
        if (!d) {
          listEl.innerHTML = `<div class="portal-browse-error">読み込みに失敗しました: ${escapeHtml(resp?.code || 'error')}</div>`;
          return;
        }
        currentPath = d.path || '';
        renderRoots(d.roots || []);
        pathBar.textContent = currentPath || '/';
        renderEntries(d);
      }

      function renderRoots(roots) {
        rootsBar.innerHTML = '';
        roots.forEach((r) => {
          const b = document.createElement('button');
          b.type = 'button';
          b.className = 'portal-browse-root';
          b.textContent = r.label;
          b.title = r.path;
          b.addEventListener('click', () => load(r.path));
          rootsBar.appendChild(b);
        });
      }

      function renderEntries(d) {
        listEl.innerHTML = '';
        if (d.error) {
          listEl.innerHTML = `<div class="portal-browse-error">${escapeHtml(BROWSE_ERROR_LABELS[d.error] || d.error)}</div>`;
        }
        if (d.parent) {
          const up = document.createElement('div');
          up.className = 'portal-browse-item is-dir';
          up.innerHTML = '<span class="portal-browse-icon">↩</span><span>.. (上の階層)</span>';
          up.addEventListener('click', () => load(d.parent));
          listEl.appendChild(up);
        }
        const entries = d.entries || [];
        if (!entries.length && !d.error) {
          const empty = document.createElement('div');
          empty.className = 'portal-browse-empty';
          empty.textContent = 'フォルダまたは .zip がありません';
          listEl.appendChild(empty);
        }
        entries.forEach((e) => {
          const item = document.createElement('div');
          item.className = 'portal-browse-item' + (e.is_dir ? ' is-dir' : ' is-zip');
          const icon = e.is_dir ? '📁' : '📦';
          item.innerHTML = `<span class="portal-browse-icon">${icon}</span><span class="portal-browse-name"></span>`;
          item.querySelector('.portal-browse-name').textContent = e.name;
          if (e.is_dir) {
            item.addEventListener('click', () => load(e.path));
          } else {
            const select = document.createElement('button');
            select.type = 'button';
            select.className = 'portal-browse-select';
            select.textContent = '選択';
            select.addEventListener('click', (ev) => { ev.stopPropagation(); close(e.path); });
            item.appendChild(select);
            item.addEventListener('dblclick', () => close(e.path));
          }
          listEl.appendChild(item);
        });
      }

      load('');
    });
  }

  // ---- Run lifecycle ----

  async function ensureInstalled(pkg) {
    const installationId = installationIdFor(pkg);
    const resp = await api()?.installPortalPackage?.({
      package_id: pkg.package_id,
      version: pkg.version,
      content_hash: pkg.content_hash,
      installation_id: installationId,
    });
    if (!resp || !resp.ok) throw new Error(resp?.data?.error || resp?.code || 'install_failed');
    return installationId;
  }

  async function runPackage(idx) {
    const pkg = state.packages[idx];
    if (!pkg) return;
    const profileSel = document.querySelector(`[data-portal-profile="${idx}"]`);
    const modeSel = document.querySelector(`[data-portal-runmode="${idx}"]`);
    const snapSel = document.querySelector(`[data-portal-snapshot="${idx}"]`);
    const ackBox = document.querySelector(`[data-portal-ack="${idx}"]`);
    const launchProfileId = profileSel ? profileSel.value : '';
    if (!launchProfileId) { cardInfo(idx, '起動プロファイルが選択されていません', 'error'); return; }
    const runModeValue = modeSel ? modeSel.value : 'continue_current_data';
    const snapshotId = (runModeValue === 'start_from_snapshot' && snapSel) ? snapSel.value : '';
    if (runModeValue === 'start_from_snapshot' && !snapshotId) {
      cardInfo(idx, '開始するスナップショットを選択してください', 'error');
      return;
    }
    const untrusted = (pkg.trust_state === 'untrusted_imported_package');
    if (untrusted && !(ackBox && ackBox.checked)) {
      cardInfo(idx, '取り込みパッケージを実行するには警告への同意が必要です', 'error');
      return;
    }
    cardInfo(idx, 'Installing & launching…');
    let installationId;
    try {
      installationId = await ensureInstalled(pkg);
    } catch (err) {
      cardInfo(idx, `Install failed: ${err.message}`, 'error');
      return;
    }
    const resp = await api()?.runPortalPackage?.({
      installation_id: installationId,
      launch_profile_id: launchProfileId,
      run_mode: runModeValue,
      ...(snapshotId ? { snapshot_id: snapshotId } : {}),
      trust_state: pkg.trust_state,
      untrusted_override_acknowledged: !!(untrusted && ackBox && ackBox.checked),
    });
    if (!resp || !resp.ok) {
      cardInfo(idx, `Run failed: ${resp?.data?.error || resp?.code || 'error'}`, 'error');
      return;
    }
    const data = resp.data || {};
    const playSession = data.play_session || {};
    state.run = {
      playSessionId: playSession.session_id,
      installationId,
      reconnectToken: data.reconnect_token || '',
      launchKind: playSession.launch_kind || 'static_web',
      runMode: (data.runtime && data.runtime.run_mode) || (modeSel ? modeSel.value : ''),
      packageName: (pkg.manifest && pkg.manifest.name) || pkg.package_id,
    };
    cardInfo(idx, 'Running', 'ok');
    openRunSheet();
    renderRun(playSession);
    startPolling();
    startHeartbeat();
  }

  function openRunSheet() {
    const sheet = $('portal-run-sheet');
    if (sheet) { sheet.classList.add('open'); sheet.setAttribute('aria-hidden', 'false'); }
    const title = $('portal-run-title');
    if (title) title.textContent = state.run?.packageName || 'Run';
    loadForgeTrace(state.run?.installationId);
  }

  // PFG-27: show the optional Forge provenance for this run. Absent for legacy runs.
  async function loadForgeTrace(installationId) {
    const el = $('portal-run-trace');
    if (!el) return;
    el.textContent = '';
    el.style.display = 'none';
    if (!installationId) return;
    try {
      const resp = await fetch('/api/portal/installations/' + encodeURIComponent(installationId) + '/forge-trace');
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data.available || !data.trace) return;  // legacy run: no trace, render nothing
      const t = data.trace;
      const parts = [];
      if (t.model_id) parts.push(t.model_id);
      if (t.route_id) parts.push(t.route_id);
      if (t.source_mode) parts.push(t.source_mode);
      if (t.loadout_id) parts.push('loadout:' + t.loadout_id);
      if (!parts.length) return;
      el.textContent = 'Forge: ' + parts.join(' · ');
      el.style.display = '';
    } catch (_e) { /* trace is best-effort and optional */ }
  }

  function closeRunSheet() {
    const sheet = $('portal-run-sheet');
    if (sheet) { sheet.classList.remove('open'); sheet.setAttribute('aria-hidden', 'true'); }
    const frame = $('portal-run-frame');
    if (frame) frame.src = 'about:blank';
  }

  function renderRun(session) {
    const stateEl = $('portal-run-state');
    if (stateEl) stateEl.textContent = session.state || '';
    const logs = $('portal-run-logs');
    if (logs) logs.textContent = (session.log_tail || []).join('\n');
    const frame = $('portal-run-frame');
    if (frame && state.run?.playSessionId && !frame.dataset.bound) {
      const base = state.run.launchKind === 'static_web' ? 'preview' : 'proxy';
      frame.src = `/api/atlas/play/${base}/${encodeURIComponent(state.run.playSessionId)}/`;
      frame.dataset.bound = '1';
    }
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(async () => {
      if (!state.run?.playSessionId) return;
      const resp = await api()?.getPlaySession?.(state.run.playSessionId);
      if (resp && resp.ok) renderRun(resp.data || {});
    }, 2500);
  }
  function stopPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = null;
    const frame = $('portal-run-frame');
    if (frame) delete frame.dataset.bound;
  }

  function startHeartbeat() {
    stopHeartbeat();
    if (!state.run?.reconnectToken) return;
    state.heartbeatTimer = setInterval(() => {
      if (state.run?.playSessionId && state.run?.reconnectToken) {
        api()?.portalRunHeartbeat?.(state.run.playSessionId, state.run.reconnectToken);
      }
    }, 15000);
  }
  function stopHeartbeat() {
    if (state.heartbeatTimer) clearInterval(state.heartbeatTimer);
    state.heartbeatTimer = null;
  }

  async function stopRun() {
    if (!state.run?.playSessionId) return;
    await api()?.stopPortalRun?.(state.run.playSessionId);
    stopPolling();
    stopHeartbeat();
    await promptDataDecision();
  }

  async function promptDataDecision() {
    const sid = state.run?.playSessionId;
    if (!sid) { closeRunSheet(); return; }
    if (state.run.runMode === 'ephemeral') {
      await api()?.purgePortalRun?.(sid);
      finishRun('Ephemeral run discarded');
      return;
    }
    const choice = root.prompt('生成データの処理を選択: save / snapshot / discard', 'save');
    const c = (choice || '').trim().toLowerCase();
    if (c === 'save') {
      const r = await api()?.savePortalRunData?.(sid);
      finishRun(r && r.ok ? 'Saved' : 'Save failed', r && r.ok ? 'ok' : 'error');
    } else if (c === 'snapshot') {
      const r = await api()?.snapshotPortalRunData?.(sid, null);
      finishRun(r && r.ok ? 'Snapshot saved' : 'Snapshot failed', r && r.ok ? 'ok' : 'error');
    } else {
      const r = await api()?.discardPortalRunData?.(sid);
      finishRun(r && r.ok ? 'Discarded' : 'Discard failed', r && r.ok ? 'ok' : 'error');
    }
  }

  function finishRun(message, kind) {
    setStatus(message || '', kind);
    state.run = null;
    closeRunSheet();
    refreshCatalog();
  }

  // ---- Per-package actions ----

  async function showData(idx) {
    const pkg = state.packages[idx];
    if (!pkg) return;
    cardInfo(idx, 'Loading data…');
    let installationId;
    try { installationId = await ensureInstalled(pkg); } catch (err) { cardInfo(idx, `Error: ${err.message}`, 'error'); return; }
    const resp = await api()?.getPortalInstallationData?.(installationId);
    if (!resp || !resp.ok) { cardInfo(idx, 'No data summary', 'error'); return; }
    const d = resp.data || {};
    const cur = d.current_data || {};
    const snaps = d.snapshots || [];
    cardInfo(idx, `Current data: ${formatBytes(cur.bytes)} · snapshots: ${snaps.length}`, 'ok');
  }

  function exportPackage(idx) {
    const pkg = state.packages[idx];
    if (!pkg) return;
    const url = api()?.exportPortalPackageUrl?.(pkg.package_id, pkg.version, pkg.content_hash);
    if (url) root.open(url, '_blank', 'noopener');
  }

  async function forkToAtlas(idx) {
    const pkg = state.packages[idx];
    if (!pkg) return;
    const newProjectId = root.prompt('Fork 先の新しい Atlas プロジェクト名を入力', `${pkg.package_id}-fork`);
    if (!newProjectId) return;
    cardInfo(idx, 'Forking…');
    const resp = await api()?.forkPortalToAtlas?.({
      package_id: pkg.package_id,
      version: pkg.version,
      content_hash: pkg.content_hash,
      new_project_id: newProjectId.trim(),
    });
    cardInfo(idx, resp && resp.ok ? `Forked → ${newProjectId}` : `Fork failed: ${resp?.data?.error || resp?.code || 'error'}`, resp && resp.ok ? 'ok' : 'error');
  }

  async function uninstallPackage(idx) {
    const pkg = state.packages[idx];
    if (!pkg) return;
    if (!root.confirm(`Uninstall package ${pkg.package_id} v${pkg.version}? (データは別操作で削除されます)`)) return;
    const resp = await api()?.uninstallPortalPackage?.(pkg.package_id, pkg.version, pkg.content_hash);
    if (resp && resp.ok) { setStatus('Package uninstalled', 'ok'); refreshCatalog(); }
    else cardInfo(idx, `Uninstall failed: ${resp?.data?.error || resp?.code || 'error'}`, 'error');
  }

  async function deleteData(idx) {
    const pkg = state.packages[idx];
    if (!pkg) return;
    if (!root.confirm(`Delete ALL generated data for ${pkg.package_id} v${pkg.version}? この操作は取り消せません。`)) return;
    let installationId;
    try { installationId = await ensureInstalled(pkg); } catch (err) { cardInfo(idx, `Error: ${err.message}`, 'error'); return; }
    const resp = await api()?.deletePortalInstallationData?.(installationId, true);
    if (resp && resp.ok) { cardInfo(idx, 'Data deleted', 'ok'); refreshCatalog(); }
    else cardInfo(idx, `Delete failed: ${resp?.data?.error || resp?.code || 'error'}`, 'error');
  }

  // ---- Event wiring ----

  function onCatalogClick(ev) {
    const btn = ev.target.closest('[data-portal-act]');
    if (!btn) return;
    const idx = Number(btn.dataset.idx);
    switch (btn.dataset.portalAct) {
      case 'run': runPackage(idx); break;
      case 'data': showData(idx); break;
      case 'export': exportPackage(idx); break;
      case 'fork': forkToAtlas(idx); break;
      case 'uninstall': uninstallPackage(idx); break;
      case 'delete-data': deleteData(idx); break;
      case 'repair': repairManifest(idx); break;
    }
  }

  async function repairManifest(idx) {
    const pkg = state.packages[idx];
    if (!pkg || !api()?.repairPortalManifest) return;
    cardInfo(idx, 'マニフェストを修復中…');
    const resp = await api().repairPortalManifest(pkg.package_id, pkg.version, pkg.content_hash);
    if (!resp || !resp.ok || !resp.data) {
      cardInfo(idx, `修復に失敗しました: ${resp?.data?.error || resp?.code || 'error'}`, 'error');
      return;
    }
    if (resp.data.status === 'repaired') {
      cardInfo(idx, 'マニフェストを修復しました', 'ok');
      await refreshCatalog();
    } else {
      // Unrecoverable: show a safe unavailable state instead of pretending it can run.
      const reason = resp.data.reason || 'unrecoverable';
      cardInfo(idx, `このパッケージは復元できません（${escapeHtml(reason)}）。再ビルドが必要です。`, 'error');
    }
  }

  function onCatalogChange(ev) {
    const modeSel = ev.target.closest('[data-portal-runmode]');
    if (!modeSel) return;
    const idx = Number(modeSel.dataset.portalRunmode);
    const row = document.querySelector(`[data-portal-snaprow="${idx}"]`);
    if (!row) return;
    if (modeSel.value === 'start_from_snapshot') {
      row.style.display = '';
      loadSnapshotsForCard(idx);
    } else {
      row.style.display = 'none';
    }
  }

  async function loadSnapshotsForCard(idx) {
    const pkg = state.packages[idx];
    const sel = document.querySelector(`[data-portal-snapshot="${idx}"]`);
    if (!pkg || !sel || !api()?.listPortalSnapshots) return;
    sel.innerHTML = '<option value="">読み込み中…</option>';
    const resp = await api().listPortalSnapshots(installationIdFor(pkg));
    if (!resp || !resp.ok || !resp.data) {
      sel.innerHTML = '<option value="">スナップショット一覧を取得できません</option>';
      cardInfo(idx, `スナップショット一覧の取得に失敗しました: ${resp?.code || 'error'}`, 'error');
      return;
    }
    const snaps = resp.data.snapshots || [];
    if (!snaps.length) {
      sel.innerHTML = '<option value="">スナップショットがありません</option>';
      return;
    }
    sel.innerHTML = snaps.map((s) => {
      const when = String(s.last_modified || '').replace('T', ' ').slice(0, 16);
      const label = `${s.snapshot_id}${when ? ` · ${when}` : ''} · ${formatBytes(s.data_bytes || 0)}`;
      return `<option value="${escapeHtml(s.snapshot_id)}">${escapeHtml(label)}</option>`;
    }).join('');
  }

  function onRunSheetClick(ev) {
    const tab = ev.target.closest('[data-portal-tab]')?.dataset.portalTab;
    if (tab) {
      const sheet = $('portal-run-sheet');
      sheet?.querySelectorAll('[data-portal-tab]').forEach((b) => b.classList.toggle('active', b.dataset.portalTab === tab));
      sheet?.querySelectorAll('[data-portal-pane]').forEach((p) => p.classList.toggle('active', p.dataset.portalPane === tab));
    }
    const act = ev.target.closest('[data-portal-run]')?.dataset.portalRun;
    if (act === 'stop') stopRun();
    else if (act === 'close') { stopPolling(); stopHeartbeat(); closeRunSheet(); }
    else if (act === 'reload') { const f = $('portal-run-frame'); if (f && f.src && f.src !== 'about:blank') f.src = f.src; }
    else if (act === 'external') { const f = $('portal-run-frame'); if (f && f.src && f.src !== 'about:blank') root.open(f.src, '_blank', 'noopener'); }
  }

  let wired = false;
  function ensureWired() {
    if (wired) return;
    wired = true;
    $('portal-catalog')?.addEventListener('click', onCatalogClick);
    $('portal-catalog')?.addEventListener('change', onCatalogChange);
    $('portal-import-btn')?.addEventListener('click', importPackage);
    $('portal-refresh-btn')?.addEventListener('click', refreshCatalog);
    $('portal-run-sheet')?.addEventListener('click', onRunSheetClick);
  }

  function activate() {
    ensureWired();
    if (!state.activated) state.activated = true;
    refreshCatalog();
  }

  function onLeave() {
    stopPolling();
    stopHeartbeat();
  }

  root.Portal = { activate, onLeave, refreshCatalog };
})();
