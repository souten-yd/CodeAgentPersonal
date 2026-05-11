// ── NEXUS DISPLAY HELPERS ──
// Display-only Nexus DOM helpers split out of ui.html.
// Keep API/job/research execution logic in ui.html.

function ensureNexusMobileMarkdownContainmentStyles() {
  if (document.getElementById('nexus-mobile-markdown-containment-style')) return;
  const style = document.createElement('style');
  style.id = 'nexus-mobile-markdown-containment-style';
  style.textContent = `
    .nexus-col,
    .nexus-col * {
      min-width: 0;
      box-sizing: border-box;
    }
    .nexus-body,
    .nexus-tab,
    .nexus-card,
    .nexus-result-panel,
    .nexus-result-item,
    .nexus-detail-panel,
    .nexus-report-preview,
    .nexus-markdown,
    .nexus-answer,
    .nexus-answer-markdown,
    .nexus-research-answer,
    .nexus-research-answer-markdown,
    [data-nexus-answer],
    [data-nexus-markdown] {
      max-width: 100%;
      min-width: 0;
      overflow-wrap: anywhere;
      word-break: normal;
    }
    .nexus-body :where(h1, h2, h3, h4, h5, h6) {
      max-width: 100%;
      overflow-wrap: anywhere;
      word-break: normal;
      line-height: 1.28;
      margin: 0.72em 0 0.38em;
    }
    .nexus-body :where(h1) { font-size: 18px; }
    .nexus-body :where(h2) { font-size: 16px; }
    .nexus-body :where(h3) { font-size: 14px; }
    .nexus-body :where(h4, h5, h6) { font-size: 12px; }
    .nexus-body :where(p, li, blockquote, dd, dt) {
      max-width: 100%;
      overflow-wrap: anywhere;
      word-break: normal;
      line-height: 1.65;
    }
    .nexus-body :where(img, svg, canvas, video) {
      max-width: 100%;
      height: auto;
    }
    .nexus-body :where(pre, table, .nexus-table-wrap, .nexus-source-list, .nexus-reference-list, .nexus-sources, .nexus-references) {
      max-width: 100%;
      overflow-x: auto;
      overflow-y: hidden;
      -webkit-overflow-scrolling: touch;
    }
    .nexus-body :where(pre) {
      white-space: pre;
      font-size: 11px;
      line-height: 1.45;
    }
    .nexus-body :where(code) {
      max-width: 100%;
      overflow-wrap: anywhere;
      word-break: break-word;
      font-size: 0.92em;
    }
    .nexus-body :where(pre code) {
      overflow-wrap: normal;
      word-break: normal;
      white-space: pre;
    }
    .nexus-body :where(table) {
      width: max-content;
      min-width: 100%;
      border-collapse: collapse;
    }
    @media (max-width: 768px) {
      .nexus-body {
        width: 100%;
        max-width: 100vw;
        overflow-x: hidden;
        padding-left: 8px;
        padding-right: 8px;
      }
      .nexus-topbar,
      .nexus-subtabs {
        max-width: 100%;
        min-width: 0;
      }
      .nexus-body :where(h1) { font-size: 16px; }
      .nexus-body :where(h2) { font-size: 15px; }
      .nexus-body :where(h3) { font-size: 13px; }
      .nexus-body :where(p, li, blockquote) { font-size: 12px; }
      .nexus-body :where(pre, table, .nexus-table-wrap, .nexus-source-list, .nexus-reference-list, .nexus-sources, .nexus-references) {
        max-width: calc(100vw - 24px);
      }
    }
  `;
  document.head.appendChild(style);
}

ensureNexusMobileMarkdownContainmentStyles();

function updateNexusJobBanner(text, isErr = false) {
  const el = document.getElementById('nexus-lib-job');
  if (!el) return;
  el.textContent = text;
  el.style.color = isErr ? 'var(--red)' : 'var(--amber)';
}

function renderNexusDocumentDetail(doc = null) {
  const el = document.getElementById('nexus-lib-detail');
  if (!el) return;
  if (!doc) {
    el.innerHTML = '<div class="nexus-empty">文書を選択すると詳細を表示します</div>';
    return;
  }
  const created = String(doc.created_at || '').replace('T', ' ').slice(0, 19) || '-';
  const metadata = doc.metadata || {
    content_type: doc.content_type || '-',
    has_extracted_text: !!doc.has_extracted_text,
    has_markdown: !!doc.has_markdown,
  };
  el.innerHTML = `
    <div class="nexus-detail-row"><b>ID:</b> ${esc(doc.id || '-')}</div>
    <div class="nexus-detail-row"><b>作成日時:</b> ${esc(created)}</div>
    <div class="nexus-detail-row"><b>chunk数:</b> ${Number(doc.chunk_count || 0)}</div>
    <div class="nexus-detail-row"><b>サイズ:</b> ${esc(formatBytes(doc.size || 0))}</div>
    <div class="nexus-detail-row"><b>メタデータ:</b></div>
    <pre class="nexus-detail-pre">${esc(JSON.stringify(metadata, null, 2))}</pre>
  `;
}

function renderNexusTimeline() {
  const el = document.getElementById('nexus-lib-timeline');
  if (!el) return;
  if (!nexusEventTimeline.length) {
    el.innerHTML = '<div class="nexus-empty">No timeline events</div>';
    return;
  }
  el.innerHTML = nexusEventTimeline.slice(0, 50).map((row) => `
    <div class="nexus-tl-item">
      <div class="nexus-tl-head">${esc(row.time)} · ${esc(row.job_id)}</div>
      <div class="nexus-tl-body">${esc(row.label)}</div>
    </div>
  `).join('');
}

function pushNexusTimelineEvent(jobId, label, ts = '') {
  const timeRaw = ts || new Date().toISOString();
  const time = String(timeRaw).replace('T', ' ').slice(0, 19);
  nexusEventTimeline.unshift({ job_id: String(jobId || '-'), label: String(label || '-'), time });
  if (nexusEventTimeline.length > 120) nexusEventTimeline = nexusEventTimeline.slice(0, 120);
  renderNexusTimeline();
}

function renderNexusDocuments(items = []) {
  const el = document.getElementById('nexus-lib-list');
  if (!el) return;
  if (!items.length) {
    el.innerHTML = '<div class="nexus-empty">No documents</div>';
    renderNexusDocumentDetail(null);
    return;
  }
  el.innerHTML = items.map((doc) => {
    const dt = String(doc.created_at || '').replace('T', ' ').slice(0, 16);
    return `<div class="nexus-doc-item">
      <div>
        <div style="font-size:12px;font-weight:700">${esc(doc.filename || 'untitled')}</div>
        <div class="nexus-doc-meta">
          <span>created: ${esc(dt)}</span>
          <span>size: ${esc(formatBytes(doc.size))}</span>
          <span>chunks: ${doc.chunk_count || 0}</span>
          <span>metadata: ${esc(doc.content_type || '-')}</span>
        </div>
      </div>
      <div class="nexus-doc-actions">
        <button onclick="event.stopPropagation();downloadNexusDocument('${esc(doc.id)}')">Original download</button>
        <button onclick="event.stopPropagation();downloadNexusExtractedText('${esc(doc.id)}')">Extracted text download</button>
        <button class="danger" onclick="event.stopPropagation();deleteNexusDocument('${esc(doc.id)}')">Delete</button>
      </div>
    </div>`;
  }).join('');
  Array.from(el.querySelectorAll('.nexus-doc-item')).forEach((node, idx) => {
    const doc = items[idx];
    const isActive = nexusSelectedDocumentId === doc.id;
    node.classList.toggle('active', isActive);
    node.onclick = () => selectNexusDocument(doc.id);
  });
  if (!nexusSelectedDocumentId && items[0]?.id) selectNexusDocument(items[0].id);
}

function renderNexusJobs(jobs = []) {
  const el = document.getElementById('nexus-lib-jobs');
  if (!el) return;
  if (!jobs.length) {
    el.innerHTML = '<div class="nexus-empty">No active jobs</div>';
    return;
  }
  el.innerHTML = jobs.map((job) => {
    const st = esc(job.status || '-');
    const msg = esc(job.message || '');
    const updated = esc(String(job.updated_at || '').replace('T', ' ').slice(0, 19));
    return `<div class="nexus-job-item"><div class="nexus-job-item-title">${esc(job.job_id || '')}</div><div class="nexus-job-item-meta">${st} ${msg ? '· ' + msg : ''} · ${updated}</div></div>`;
  }).join('');
}

function setNexusDropzoneActive(active) {
  const dz = document.getElementById('nexus-lib-dropzone');
  if (!dz) return;
  dz.classList.toggle('active', !!active);
}

window.ensureNexusMobileMarkdownContainmentStyles = ensureNexusMobileMarkdownContainmentStyles;
window.updateNexusJobBanner = updateNexusJobBanner;
window.renderNexusDocumentDetail = renderNexusDocumentDetail;
window.renderNexusTimeline = renderNexusTimeline;
window.pushNexusTimelineEvent = pushNexusTimelineEvent;
window.renderNexusDocuments = renderNexusDocuments;
window.renderNexusJobs = renderNexusJobs;
window.setNexusDropzoneActive = setNexusDropzoneActive;
