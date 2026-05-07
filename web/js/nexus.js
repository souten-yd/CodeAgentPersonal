// ── NEXUS DISPLAY HELPERS ──
// Display-only Nexus DOM helpers split out of ui.html.
// Keep API/job/research execution logic in ui.html.

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

window.updateNexusJobBanner = updateNexusJobBanner;
window.renderNexusDocumentDetail = renderNexusDocumentDetail;
window.renderNexusTimeline = renderNexusTimeline;
window.pushNexusTimelineEvent = pushNexusTimelineEvent;
window.renderNexusDocuments = renderNexusDocuments;
window.renderNexusJobs = renderNexusJobs;
window.setNexusDropzoneActive = setNexusDropzoneActive;
