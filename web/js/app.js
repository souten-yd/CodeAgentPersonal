window.KASANE_UI_BOOTSTRAP_LOADED = true;

// ── SKILL MANAGEMENT ──

function showTaskOptions(ev, jobId) {
  const options = ev.options || [];
  const autoChosen = ev.auto_chosen;
  const autoReason = ev.auto_reason || '';
  const taskId  = ev.task_id;
  const w = messages();
  const d = document.createElement('div');
  d.className = 'msg system';
  d.id = `task-options-${taskId}`;

  const diffColor = {'easy':'var(--accent)','medium':'var(--amber)','hard':'var(--red)'};
  // 自動選択済みの場合はハイライト表示
  const optHtml = options.map((o,i) => `
    <div style="border:1px solid var(--border2);border-radius:6px;padding:10px 12px;margin-bottom:8px;background:var(--bg2)">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span style="font-size:12px;font-weight:700;color:var(--text)">${esc(o.title)}</span>
        <span style="font-size:10px;padding:1px 6px;border-radius:10px;border:1px solid ${diffColor[o.difficulty]||'var(--border2)'};color:${diffColor[o.difficulty]||'var(--text3)'}">${o.difficulty||''}</span>
      </div>
      <div style="font-size:11px;color:var(--text2);margin-bottom:8px">${esc(o.description||'')}</div>
      <button onclick="chooseTaskOption('${jobId}',${taskId},${i})"
        style="width:100%;padding:6px;font-size:11px;font-weight:700;background:var(--accent);border:none;border-radius:4px;color:var(--bg);cursor:pointer">
        ▶ この案で実行
      </button>
    </div>`).join('');

  const autoNote = autoChosen
    ? `<div style="font-size:11px;padding:6px 8px;background:var(--accent-bg);border:1px solid var(--accent-border);border-radius:4px;margin-bottom:8px;color:var(--accent)">🤖 プランナーLLMが案${autoChosen}を自動選択: ${esc(autoReason)}</div>`
    : '';
  const selectionLabel = autoChosen ? '確認・変更（実行済み）' : '対応案を選択してください';
  d.innerHTML = `
    <div class="msg-role" style="color:${autoChosen ? 'var(--accent)' : 'var(--amber)'}">
      ${autoChosen ? '🤖 自動選択して実行' : '⚠ 対応案の選択が必要'}
    </div>
    <div style="padding:10px 12px">
      <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:4px">タスク: ${esc(ev.title||'')}</div>
      <div style="font-size:11px;color:var(--red);margin-bottom:8px;word-break:break-all">${esc((ev.error||'').slice(0,120))}</div>
      ${autoNote}
      <div style="font-size:11px;font-weight:700;color:var(--text2);margin-bottom:8px;text-transform:uppercase;letter-spacing:.06em">${selectionLabel}</div>
      ${optHtml}
    </div>`;
  w.appendChild(d);
  scrollMsgs();

  // プログレスカードを「選択待ち」に更新
  if (typeof progCard !== 'undefined' && progCard) {
    setCard(progCard, {action: '⏸ ユーザー選択待ち: ' + esc(ev.title||'')});
  }
}

async function chooseTaskOption(jobId, taskId, optIdx) {
  const card = document.getElementById(`task-options-${taskId}`);
  if (!card) return;
  const btns = card.querySelectorAll('button');
  const btn = btns[optIdx];
  if (!btn) return;

  // 選択したオプションデータを取得
  // task_optionsイベントのoptionsは_taskOptionsMapに保存しておく
  const opts = _taskOptionsMap[`${jobId}_${taskId}`] || [];
  const chosen = opts[optIdx];
  if (!chosen) return;

  btn.disabled = true;
  btn.textContent = '⟳ 送信中...';
  btns.forEach((b,i) => { if(i!==optIdx) b.disabled = true; });

  try {
    await fetch(API+`/jobs/${jobId}/respond`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        task_id: taskId,
        option: chosen,
        project: currentProject
      })
    });
    btn.textContent = '✓ 選択済み';
    card.style.opacity = '0.6';
    addLog('ok','task', `選択: ${chosen.title}`);
  } catch(e) {
    btn.textContent = 'エラー';
    addLog('err','task', `option send error: ${e.message}`);
  }
}

var _taskOptionsMap = window._taskOptionsMap || {};  // jobId_taskId -> options array

async function refreshSkills() {
  try {
    const r = await fetch(API+'/skills');
    const d = await r.json();
    renderSkills(d.skills || [], d);
  } catch(e) { console.warn('skills fetch error', e); }
}

function renderSkills(skills, meta = {}) {
  const el = document.getElementById('skills-list');
  if (!el) return;
  const pathInfo = document.getElementById('skills-path-info');
  const paths = meta.paths || {};
  const activePath = paths.active || './ca_data/skills';
  const runtime = paths.runtime || 'local';
  const skillMdPath = (base) => /[A-Za-z]:\\/.test(base) ? `${base}\\スキル名\\SKILL.md` : `${base}/スキル名/SKILL.md`;
  if (pathInfo) {
    pathInfo.innerHTML = `📁 <code style="background:var(--bg3);padding:1px 4px;border-radius:3px">${esc(skillMdPath(activePath))}</code><br>
      現在の構成: <b>${esc(runtime)}</b> / 共有資産: ユーザー追加・KasaneCore提案スキルを同じフォルダで管理`;
  }
  if (!skills.length) {
    el.innerHTML = `<div style="font-size:11px;color:var(--text3);padding:8px;line-height:1.8">
      スキルなし。<br>
      追加方法: 環境変数 <code style="background:var(--bg3);padding:1px 5px;border-radius:3px">CODEAGENT_SKILLS_DIR</code> を設定し、<br>
      <code style="background:var(--bg3);padding:1px 5px;border-radius:3px">スキル名/SKILL.md</code> を配置してください。
    </div>`;
    return;
  }
  el.innerHTML = skills.map(s => {
    const isCa = s.source === 'codeagent';
    const srcBadge = isCa
      ? `<span style="font-size:9px;color:var(--blue);padding:1px 5px;border:1px solid rgba(68,136,255,.3);border-radius:3px">⚙ KasaneCore</span>`
      : `<span style="font-size:9px;color:var(--text3);padding:1px 5px;border:1px solid var(--border);border-radius:3px">👤 user</span>`;
    const kws = (s.keywords||[]).map(k =>
      `<span style="background:var(--bg3);padding:1px 5px;border-radius:3px;font-size:10px">${esc(k)}</span>`
    ).join(' ');
    return `
    <div style="border:1px solid var(--border);border-radius:6px;padding:10px 12px;background:var(--bg2)">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px">
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <span style="font-size:12px;font-weight:700;color:var(--accent);font-family:var(--font-mono)">${esc(s.name)}</span>
          ${srcBadge}
          <span style="font-size:9px;color:var(--text3)">v${esc(s.version||'1.0')}</span>
          <span style="font-size:9px;color:var(--green);padding:1px 5px;border:1px solid rgba(0,255,157,.24);border-radius:3px">Tool</span>
        </div>
        <div style="display:flex;gap:5px;align-items:center;flex-shrink:0">
          <span style="font-size:10px;color:var(--text3)">×${s.usage_count||0}</span>
          <button onclick="deleteSkill('${esc(s.name)}')" style="font-size:10px;padding:1px 6px;border:1px solid rgba(255,68,102,.3);background:rgba(255,68,102,.08);color:var(--red);border-radius:3px;cursor:pointer">✕</button>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text2);margin-bottom:5px">${esc(s.description)}</div>
      ${kws ? `<div style="margin-bottom:5px;display:flex;flex-wrap:wrap;gap:3px">${kws}</div>` : ''}
      <div style="display:flex;gap:5px;margin-top:5px">
        <button onclick="proposeSkillImprovement(decodeURIComponent('${encodeURIComponent(s.name)}'))" style="font-size:10px;padding:2px 8px;border:1px solid var(--border);background:var(--bg3);color:var(--text2);border-radius:3px;cursor:pointer">↑ Improve</button>
        <button onclick="testSkill(decodeURIComponent('${encodeURIComponent(s.name)}'))" style="font-size:10px;padding:2px 8px;border:1px solid var(--border);background:var(--bg3);color:var(--text2);border-radius:3px;cursor:pointer">▶ Test</button>
      </div>
      ${s.tool_code ? `<details style="margin-top:6px">
        <summary style="font-size:10px;color:var(--text3);cursor:pointer">▶ SKILL.md code</summary>
        <pre style="font-size:10px;font-family:var(--font-mono);color:var(--text2);white-space:pre-wrap;word-break:break-all;margin:4px 0 0 0;padding:6px;background:var(--bg3);border-radius:4px;overflow-x:auto;max-height:180px">${esc(s.tool_code)}</pre>
      </details>` : ''}
    </div>`;
  }).join('');
}

async function deleteSkill(name) {
  if (!confirm('Delete skill: ' + name + '?')) return;
  await fetch(API+'/skills/'+encodeURIComponent(name), {method:'DELETE'});
  refreshSkills();
}

// ── PERMANENT MEMORY ──
var _memSearchTimer = null;

async function refreshMemory() {
  try {
    const r = await fetch(API+'/memory');
    const d = await r.json();
    renderMemory(d.entries || []);
  } catch(e) { console.warn('memory fetch error', e); }
}

async function searchMemory(q) {
  clearTimeout(_memSearchTimer);
  _memSearchTimer = setTimeout(async () => {
    try {
      const url = q.trim() ? API+'/memory?q='+encodeURIComponent(q) : API+'/memory';
      const r = await fetch(url);
      const d = await r.json();
      renderMemory(d.entries || []);
    } catch(e) {}
  }, 300);
}

var _catColor = {
  error_solution: 'var(--red)',
  env_knowledge: 'var(--blue)',
  workflow: 'var(--amber)',
  general: 'var(--text3)'
};
var _catLabel = {
  error_solution: '🔧 error_solution',
  env_knowledge: '🌐 env_knowledge',
  workflow: '⚙ workflow',
  general: '📝 general'
};

function renderMemory(entries) {
  const el = document.getElementById('memory-list');
  const stats = document.getElementById('memory-stats');
  if (!el) return;
  if (stats) stats.textContent = `${entries.length} entries`;
  if (!entries.length) {
    el.innerHTML = `<div style="font-size:11px;color:var(--text3);padding:8px">
      メモリなし。タスク実行後に自動的に知識が蓄積されます。</div>`;
    return;
  }
  el.innerHTML = entries.map(e => {
    const catColor = _catColor[e.category] || 'var(--text3)';
    const catLabel = _catLabel[e.category] || e.category;
    const kws = (e.keywords||[]).map(k =>
      `<span style="background:var(--bg3);padding:1px 4px;border-radius:3px;font-size:9px">${esc(k)}</span>`
    ).join(' ');
    const proj = e.source_project && e.source_project !== 'global' ? ` · ${esc(e.source_project)}` : '';
    const date = (e.updated_at||'').slice(0,10);
    return `
    <div style="border:1px solid var(--border);border-radius:6px;padding:10px 12px;background:var(--bg2)">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px">
        <div style="flex:1">
          <span style="font-size:11px;font-weight:700;color:var(--text)">${esc(e.title)}</span>
          <span style="font-size:9px;color:${catColor};margin-left:6px;padding:1px 5px;border:1px solid ${catColor};border-radius:3px;opacity:.7">${catLabel}</span>
        </div>
        <div style="display:flex;gap:4px;align-items:center;flex-shrink:0;margin-left:6px">
          <span style="font-size:9px;color:var(--text3)">×${e.usage_count||0}${proj}</span>
          <button onclick="editMemoryInline('${esc(e.id)}')" style="font-size:9px;padding:1px 5px;border:1px solid var(--border);background:var(--bg3);color:var(--text2);border-radius:3px;cursor:pointer">✏</button>
          <button onclick="deleteMemory('${esc(e.id)}')" style="font-size:9px;padding:1px 5px;border:1px solid rgba(255,68,102,.3);background:rgba(255,68,102,.08);color:var(--red);border-radius:3px;cursor:pointer">✕</button>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text2);margin-bottom:5px;line-height:1.5">${esc(e.content)}</div>
      ${kws ? `<div style="display:flex;flex-wrap:wrap;gap:3px;margin-bottom:4px">${kws}</div>` : ''}
      <div style="font-size:9px;color:var(--text3)">${date}</div>
    </div>`;
  }).join('');
}

async function deleteMemory(id) {
  if (!confirm('このメモリを削除しますか？')) return;
  await fetch(API+'/memory/'+encodeURIComponent(id), {method:'DELETE'});
  refreshMemory();
}

function showAddMemoryForm() {
  const f = document.getElementById('memory-add-form');
  if (f) { f.style.display = 'block'; document.getElementById('mem-title')?.focus(); }
}
function hideAddMemoryForm() {
  const f = document.getElementById('memory-add-form');
  if (f) f.style.display = 'none';
}

async function saveNewMemory() {
  const category = document.getElementById('mem-category')?.value || 'general';
  const title = document.getElementById('mem-title')?.value?.trim();
  const content = document.getElementById('mem-content')?.value?.trim();
  const kwRaw = document.getElementById('mem-keywords')?.value || '';
  const keywords = kwRaw.split(',').map(k=>k.trim()).filter(Boolean);
  if (!title || !content) { alert('タイトルと内容は必須です'); return; }
  await fetch(API+'/memory', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({category, title, content, keywords, source_project:'manual'})
  });
  hideAddMemoryForm();
  document.getElementById('mem-title').value = '';
  document.getElementById('mem-content').value = '';
  document.getElementById('mem-keywords').value = '';
  refreshMemory();
  addLog('ok','memory', `メモリ追加: ${title}`);
}

async function editMemoryInline(id) {
  // メモリ一覧から該当エントリを取得して編集フォームに流し込む
  try {
    const r = await fetch(API+'/memory');
    const d = await r.json();
    const e = (d.entries||[]).find(x => x.id === id);
    if (!e) return;
    const newContent = prompt('内容を編集:', e.content);
    if (newContent === null) return;
    await fetch(API+'/memory/'+encodeURIComponent(id), {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...e, content: newContent.trim()})
    });
    refreshMemory();
    addLog('ok','memory', `メモリ更新: ${e.title}`);
  } catch(ex) { console.error(ex); }
}

window.showTaskOptions = showTaskOptions;
window.chooseTaskOption = chooseTaskOption;
window._taskOptionsMap = _taskOptionsMap;
window.refreshSkills = refreshSkills;
window.renderSkills = renderSkills;
window.deleteSkill = deleteSkill;
window.refreshMemory = refreshMemory;
window.searchMemory = searchMemory;
window.renderMemory = renderMemory;
window.deleteMemory = deleteMemory;
window.showAddMemoryForm = showAddMemoryForm;
window.hideAddMemoryForm = hideAddMemoryForm;
window.saveNewMemory = saveNewMemory;
window.editMemoryInline = editMemoryInline;
window._memSearchTimer = _memSearchTimer;
window._catColor = _catColor;
window._catLabel = _catLabel;
