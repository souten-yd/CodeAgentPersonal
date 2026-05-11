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
window.isNexusAdvancedSettingsOpen = isNexusAdvancedSettingsOpen;
window.collectNexusAdvancedOverrides = collectNexusAdvancedOverrides;
window.bindNexusAdvancedSettingsToggleState = bindNexusAdvancedSettingsToggleState;

function detectNexusLongContext() {
  if (typeof window !== 'undefined' && window.__nexusLongContext === true) return true;
  if (typeof document === 'undefined') return false;
  const text = [
    document.getElementById('nexus-deep-status')?.textContent || '',
    document.getElementById('nexus-deep-answer')?.textContent || '',
  ].join(' ');
  const match = text.match(/(?:ctx|max_context_tokens|context)\D{0,12}(\d{5,6})/i);
  return Boolean(match && Number(match[1]) >= 60000);
}

function resolveNexusResearchAutoSettings({ searchType, depth } = {}) {
  const type = String(searchType || 'general').trim().toLowerCase();
  const key = String(depth || 'standard').trim().toLowerCase();
  const long64k = detectNexusLongContext();
  const byDepth = {
    quick: { max_queries: 2, max_results_per_query: 5, max_sources: 12, max_downloads: 6, recursive_search: false, max_iterations: 1, max_followup_queries: 4, confidence_threshold: 0.72, continue_on_download_error: true, stop_when_sufficient: true },
    standard: { max_queries: 4, max_results_per_query: 6, max_sources: 24, max_downloads: 10, recursive_search: false, max_iterations: 1, max_followup_queries: 4, confidence_threshold: 0.76, continue_on_download_error: true, stop_when_sufficient: true },
    deep: { max_queries: long64k ? 8 : 6, max_results_per_query: long64k ? 10 : 8, max_sources: 100, max_downloads: 48, target_candidate_count: 180, target_valid_source_count: 35, target_evidence_count: long64k ? 120 : 100, target_high_quality_source_count: 10, target_official_source_count: 6, target_pdf_source_count: 6, max_retrieval_rounds: 4, adaptive_retrieval_enabled: true, recursive_search: true, max_iterations: 2, max_followup_queries: long64k ? 6 : 4, confidence_threshold: long64k ? 0.82 : 0.78, continue_on_download_error: true, stop_when_sufficient: true },
    exhaustive: { max_queries: long64k ? 10 : 8, max_results_per_query: 12, max_sources: 160, max_downloads: 72, target_candidate_count: 300, target_valid_source_count: 55, target_evidence_count: long64k ? 180 : 160, target_high_quality_source_count: 16, target_official_source_count: 10, target_pdf_source_count: 10, max_retrieval_rounds: 5, adaptive_retrieval_enabled: true, recursive_search: true, max_iterations: 3, max_followup_queries: long64k ? 8 : 5, confidence_threshold: 0.85, continue_on_download_error: true, stop_when_sufficient: true },
  };
  const typeMap = {
    general: { scope: 'web', source_profile: 'web', prefer_pdf: true, official_first: true },
    technical_research: { scope: 'academic', source_profile: 'academic', prefer_pdf: true, official_first: true },
    news_scan: { scope: 'news', source_profile: 'news', prefer_pdf: false, official_first: false },
    market_research: { scope: 'news', source_profile: 'news', prefer_pdf: false, official_first: false },
    standards_legal: { scope: 'official', source_profile: 'official', prefer_pdf: true, official_first: true },
    official: { scope: 'official', source_profile: 'official', prefer_pdf: true, official_first: true },
  };
  return { ...(byDepth[key] || byDepth.standard), ...(typeMap[type] || typeMap.general) };
}


function isNexusAdvancedSettingsOpen() {
  const el = document.getElementById('nexus-research-advanced');
  return !!(el && el.open);
}

function collectNexusAdvancedOverrides() {
  if (!isNexusAdvancedSettingsOpen()) return {};

  const readInt = (id, min, max) => {
    const value = document.getElementById(id)?.value;
    if (typeof clampInt === 'function') return clampInt(value, min, max);
    const num = parseInt(String(value ?? '').trim(), 10);
    if (!Number.isFinite(num)) return null;
    return Math.min(max, Math.max(min, num));
  };
  const readFloat = (id, min, max) => {
    const value = document.getElementById(id)?.value;
    if (typeof clampFloat === 'function') return clampFloat(value, min, max);
    const num = Number.parseFloat(String(value ?? '').trim());
    if (!Number.isFinite(num)) return null;
    return Math.min(max, Math.max(min, num));
  };
  const readChecked = (id, defaultValue = true) => {
    const el = document.getElementById(id);
    return el ? el.checked === true : defaultValue;
  };
  const setIfPresent = (target, key, value) => {
    if (value !== null && value !== undefined && value !== '') target[key] = value;
  };

  const overrides = {};
  const scope = (document.getElementById('nexus-deep-scope')?.value || '').trim().toLowerCase();
  setIfPresent(overrides, 'scope', scope);
  setIfPresent(overrides, 'max_queries', readInt('nexus-deep-max-queries', 1, 50));
  setIfPresent(overrides, 'max_results_per_query', readInt('nexus-deep-max-results-per-query', 1, 100));
  setIfPresent(overrides, 'max_sources', readInt('nexus-deep-max-sources', 1, 200));
  setIfPresent(overrides, 'max_download_mb', readInt('nexus-deep-max-download-mb', 1, 500));
  setIfPresent(overrides, 'max_total_download_mb', readInt('nexus-deep-max-total-download-mb', 1, 2048));
  setIfPresent(overrides, 'max_downloads', readInt('nexus-deep-max-downloads', 1, 200));
  setIfPresent(overrides, 'download_timeout_sec', readInt('nexus-deep-download-timeout-sec', 1, 600));
  overrides.continue_on_download_error = readChecked('nexus-deep-continue-on-download-error', true);
  overrides.prefer_pdf = readChecked('nexus-deep-prefer-pdf', true);
  overrides.official_first = readChecked('nexus-deep-official-first', true);

  const recursiveSearch = readChecked('nexus-deep-recursive-search', false);
  const recursiveSettings = (typeof normalizeNexusRecursiveSettings === 'function')
    ? normalizeNexusRecursiveSettings({
      recursiveSearch,
      maxIterations: document.getElementById('nexus-deep-max-iterations')?.value,
      maxFollowupQueries: document.getElementById('nexus-deep-max-followup-queries')?.value,
      confidenceThreshold: document.getElementById('nexus-deep-confidence-threshold')?.value,
      stopWhenSufficient: readChecked('nexus-deep-stop-when-sufficient', true),
    })
    : {
      recursive_search: recursiveSearch,
      max_iterations: recursiveSearch ? (readInt('nexus-deep-max-iterations', 1, 5) ?? 2) : 1,
      max_followup_queries: recursiveSearch ? (readInt('nexus-deep-max-followup-queries', 1, 10) ?? 4) : 4,
      confidence_threshold: recursiveSearch ? (readFloat('nexus-deep-confidence-threshold', 0, 1) ?? 0.75) : 0.75,
      stop_when_sufficient: readChecked('nexus-deep-stop-when-sufficient', true),
    };
  overrides.recursive_search = recursiveSettings.recursive_search;
  overrides.max_iterations = recursiveSettings.max_iterations;
  overrides.max_followup_queries = recursiveSettings.max_followup_queries;
  overrides.confidence_threshold = recursiveSettings.confidence_threshold;
  overrides.stop_when_sufficient = recursiveSettings.stop_when_sufficient;
  window.__nexusAdvancedOverridesEnabled = true;
  return overrides;
}

function bindNexusAdvancedSettingsToggleState() {
  const el = document.getElementById('nexus-research-advanced');
  if (!el || el.dataset.nexusAdvancedToggleBound === 'true') return;
  el.dataset.nexusAdvancedToggleBound = 'true';
  el.addEventListener('toggle', () => {
    window.__nexusAdvancedOverridesEnabled = el.open === true;
    if (!el.open) window.__nexusAdvancedOverridesEnabled = false;
  });
}

function classifyNexusAnswerGenerationNotice(answerJson = {}) {
  const answer = (answerJson && typeof answerJson === 'object') ? answerJson : {};
  const generation = (answer.generation && typeof answer.generation === 'object') ? answer.generation : {};
  const finishReason = String(generation.final_finish_reason || generation.finish_reason || answer.finish_reason || '').trim().toLowerCase();
  const error = String(generation.error || answer.error || answer.llm_error || '').trim();
  const errorLower = error.toLowerCase();
  const outputTruncated = Boolean(answer.output_truncated ?? generation.final_output_truncated ?? generation.output_truncated);
  const outputIncomplete = Boolean(answer.output_incomplete ?? generation.final_output_incomplete ?? generation.output_incomplete);
  const generationMode = String(generation.mode || answer.generation_mode || '').trim().toLowerCase();
  const status = String(answer.output_generation_status || generation.output_generation_status || '').trim().toLowerCase();
  const hasAnswer = Boolean(String(answer.answer_markdown || answer.answer || '').trim());
  const explicitTimeout = /timeout|timed out|タイムアウト/.test(errorLower) || status === 'timeout';
  const explicitLimit = /max[_ -]?tokens|context overflow|context length|maximum context|出力上限/.test(errorLower);
  if (explicitTimeout) return { severity: 'warning', message: '回答生成がタイムアウトしました。timeoutを増やすか再実行してください。', showToUser: true };
  if (outputTruncated || finishReason === 'length' || explicitLimit || (generationMode === 'llm_answer_truncated' && finishReason !== 'stop')) {
    return { severity: 'warning', message: '回答が出力上限で途中終了しました。出力上限を増やすか再生成してください。', showToUser: true };
  }
  if (answer.user_visible_warning === true && String(answer.user_visible_warning_reason || '').trim()) {
    return { severity: 'warning', message: String(answer.user_visible_warning_reason).trim(), showToUser: true };
  }
  if (finishReason === 'stop' && !outputTruncated && !error && hasAnswer) {
    if (outputIncomplete || status === 'quality_check_failed') {
      return { severity: 'info', message: '回答品質チェックで未確認または根拠不足の項目があります。Evidence/Citation Verificationを確認してください。', showToUser: true };
    }
    return { severity: 'none', message: '', showToUser: false };
  }
  if (outputIncomplete || status === 'quality_check_failed') {
    return { severity: 'info', message: '回答品質チェックで未確認または根拠不足の項目があります。', showToUser: true };
  }
  return { severity: 'none', message: '', showToUser: false };
}

function formatNexusResearchStatusCompact(job = {}, bundle = {}, answer = {}) {
  const health = (bundle.health && typeof bundle.health === 'object') ? bundle.health : bundle;
  const state = String(job.status || health.job_status || health.state || '').toLowerCase();
  const phase = String(health.current_phase || health.phase || '').toLowerCase();
  const progress = Math.round(Number(job.progress ?? health.progress ?? 0) * 100);
  const dl = (health.latest_download_progress && typeof health.latest_download_progress === 'object') ? health.latest_download_progress : {};
  const total = Number(health.download_total ?? dl.total ?? answer.max_sources ?? 0);
  const completed = Number(health.download_completed ?? dl.completed ?? 0);
  const degraded = Number(health.download_degraded ?? dl.degraded ?? 0);
  const failed = Number(health.download_failed ?? dl.failed ?? 0);
  const skipped = Number(health.download_skipped ?? dl.skipped ?? 0);
  const retrieval = (answer?.retrieval_summary && typeof answer.retrieval_summary === 'object') ? answer.retrieval_summary : {};
  const sources = Number(retrieval.valid_source_count ?? (Array.isArray(bundle.sources) ? bundle.sources.length : Number(health.sources_count ?? 0)));
  const chunks = Number(retrieval.evidence_count ?? answer?.generation?.compression?.chunks_used ?? answer?.compression_stats?.chunks_used ?? 0);
  const downloadLimited = Number(retrieval.skipped_due_to_download_limit_count ?? 0);
  const retrievalRounds = Array.isArray(retrieval.retrieval_rounds) ? retrieval.retrieval_rounds.length : 0;
  const terminal = ['completed', 'complete', 'done', 'degraded', 'failed', 'cancelled'].includes(state);
  const hasNotice = degraded + failed + skipped > 0 || state === 'degraded';
  let title = terminal ? '完了しました' : '調査中';
  if (state === 'failed') title = '失敗しました';
  if (terminal && hasNotice) title = '完了しました（注意あり）';
  const phaseLabel = phase.includes('download') ? 'ダウンロードと根拠抽出' : phase.includes('answer') || phase.includes('report') ? 'レポート生成' : phase.includes('source') || phase.includes('search') ? 'ソース収集中' : '調査を進行中';
  const progressText = terminal ? 'レポート生成まで完了' : (total > 0 ? `ソース収集中 ${completed}/${total}` : `${phaseLabel}${progress ? ` ${progress}%` : ''}`);
  const screeningCount = Number(retrieval?.screening_summary?.candidate_count ?? retrieval?.screening_summary?.unique_candidate_count ?? 0);
  const focusedCount = Array.isArray(retrieval?.focused_research_plan?.focused_queries) ? retrieval.focused_research_plan.focused_queries.length : 0;
  const screeningText = screeningCount ? `一次スクリーニング:${screeningCount}候補` : '';
  const planText = focusedCount ? `再検索計画:${focusedCount}クエリ` : '';
  const collection = [screeningText, planText, `有効ソース:${sources || completed || 0}件${chunks ? ` / 根拠:${chunks}件` : ''}`].filter(Boolean).join(' / ');
  const problemCount = Math.max(0, failed + degraded);
  const limitText = downloadLimited > 0 ? `取得上限で未取得${downloadLimited}件` : '';
  const problemText = problemCount > 0 ? `取得問題${problemCount}件` : '';
  const targetNotice = retrieval.targets_satisfied === false
    ? (retrievalRounds > 1 ? '目標件数に届かなかったため、追加検索を実行しました。一部の目標件数には届きませんでした。' : '一部の目標件数には届きませんでした。')
    : (retrievalRounds > 1 ? '目標件数に届かなかったため、追加検索を実行しました。' : '');
  const notice = [problemText, limitText, targetNotice].filter(Boolean).join(' / ');
  const severity = state === 'failed' ? 'error' : (hasNotice ? 'warning' : 'info');
  return { title, progress: progressText, collection, notice, severity };
}
