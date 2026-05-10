(function () {
  const pollTimers = new Map();
  const jobState = new Map();
  const LUMEN_DEBUG_TOOL_CARDS = false;
  // Weather/News/Search compact history remains active when !LUMEN_DEBUG_TOOL_CARDS.

  function getProject() {
    if (typeof currentProject !== 'undefined' && currentProject) return currentProject;
    return 'default';
  }

  function getHistory() {
    if (typeof chatHistory !== 'undefined' && Array.isArray(chatHistory)) return chatHistory;
    return [];
  }

  function setUiBusy(value) {
    if (typeof setBusy === 'function') setBusy(value);
  }

  function log(level, scope, message) {
    if (typeof addLog === 'function') addLog(level, scope, message);
  }

  function renderUserMessage(message) {
    if (typeof addMsg === 'function') addMsg('user', message);
    if (typeof addToHistory === 'function') addToHistory('user', message);
  }

  function looksLikePythonDictNewsOutput(raw) {
    return raw.startsWith("{'") && /(summary_title|news_topics|points)/.test(raw);
  }

  function cleanupDictText(value) {
    return String(value || '')
      .replace(/\\n/g, ' ')
      .replace(/\s+/g, ' ')
      .replace(/^[\s:：,、。-]+|[\s,、。]+$/g, '')
      .trim();
  }

  function formatPythonDictLikeNewsOutput(raw) {
    const lines = [];
    const titleMatch = raw.match(/['"]summary_title['"]\s*:\s*['"]([^'"]+)['"]/);
    if (titleMatch?.[1]) lines.push(cleanupDictText(titleMatch[1]));

    const topicPattern = /['"](?:title|headline|summary|detail|description|point)['"]\s*:\s*['"]([^'"]+)['"]/g;
    const seen = new Set();
    let match = topicPattern.exec(raw);
    while (match) {
      const value = cleanupDictText(match[1]);
      if (value && !seen.has(value) && value !== lines[0]) {
        seen.add(value);
        lines.push(`- ${value}`);
      }
      match = topicPattern.exec(raw);
    }

    if (lines.length) return lines.join('\n');

    const fallback = raw
      .replace(/[{}\[\]]/g, ' ')
      .replace(/['"](?:summary_title|news_topics|points|title|headline|summary|detail|description|point)['"]\s*:\s*/g, '')
      .replace(/['"]/g, '')
      .replace(/,\s*/g, '\n- ')
      .split('\n')
      .map((line) => cleanupDictText(line.replace(/^-\s*/, '')))
      .filter(Boolean);
    return fallback.length ? fallback.join('\n') : cleanupDictText(raw);
  }

  function formatAssistantOutput(text) {
    const raw = String(text ?? '').trim();
    if (looksLikePythonDictNewsOutput(raw)) return formatPythonDictLikeNewsOutput(raw);
    if (!raw.startsWith('{') || !raw.endsWith('}')) return text;
    try {
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object' || (!Object.prototype.hasOwnProperty.call(parsed, 'summary') && !Object.prototype.hasOwnProperty.call(parsed, 'topics'))) return text;
      const lines = [];
      if (parsed.summary) lines.push(String(parsed.summary));
      const topics = Array.isArray(parsed.topics) ? parsed.topics : [];
      topics.forEach((topic) => {
        if (typeof topic === 'string') {
          lines.push(`- ${topic}`);
          return;
        }
        if (topic && typeof topic === 'object') {
          const title = topic.title || topic.headline || topic.topic || topic.summary || '';
          const detail = topic.detail || topic.description || topic.summary || '';
          const line = [title, detail && detail !== title ? detail : ''].filter(Boolean).join(': ');
          if (line) lines.push(`- ${line}`);
        }
      });
      return lines.length ? lines.join('\n') : text;
    } catch (_err) {
      return text;
    }
  }

  function renderAssistantMessage(message) {
    const formatted = formatAssistantOutput(message);
    if (typeof addMsg === 'function') addMsg('assistant', formatted);
    if (typeof addToHistory === 'function') addToHistory('assistant', formatted);
    return formatted;
  }

  function renderSystemMessage(message) {
    if (typeof addMsg === 'function') addMsg('system', message);
  }

  function collectChatHistory() {
    return getHistory().slice(-10).map((item) => ({
      role: item.role || 'user',
      text: item.text || item.content || '',
    }));
  }

  function buildSubmitPayload(message) {
    return {
      project: getProject(),
      mode: 'chat',
      message: message || '',
      chat_history: collectChatHistory(),
      tool_policy: window.LumenTools?.getToolPolicy ? window.LumenTools.getToolPolicy() : 'auto',
      search_policy: window.LumenTools?.getSearchPolicy ? window.LumenTools.getSearchPolicy() : 'auto',
      location: window.LumenTools?.getLocation ? window.LumenTools.getLocation() : '',
      search_budget: window.LumenTools?.getSearchBudget ? window.LumenTools.getSearchBudget() : {},
      weather_budget: window.LumenTools?.getWeatherBudget ? window.LumenTools.getWeatherBudget() : {},
      news_budget: window.LumenTools?.getNewsBudget ? window.LumenTools.getNewsBudget() : {},
    };
  }

  function updateProgress(state, text) {
    if (state?.progressCard && typeof setCard === 'function') setCard(state.progressCard, { action: text });
  }

  function rememberStep(state, event) {
    if (!state) return;
    if (!Array.isArray(state.steps)) state.steps = [];
    state.steps.push(event);
  }

  function toolNameFromEvent(event) {
    return String(event?.tool || event?.action || event?.name || '').toLowerCase();
  }

  function isHiddenUserFacingToolResult(event) {
    const tool = toolNameFromEvent(event);
    return tool === 'weather' || tool === 'news';
  }

  function rememberToolHistory(state, event) {
    if (!state) return;
    if (!Array.isArray(state.toolHistory)) state.toolHistory = [];
    const tool = toolNameFromEvent(event);
    if (!tool) return;
    const result = window.LumenTools?.unwrapToolPayload
      ? window.LumenTools.unwrapToolPayload(event)
      : event;
    const itemCount = Number(
      result.item_count
      ?? result.metadata?.item_count
      ?? result.total
      ?? result.total_results
      ?? 0
    );
    let label = '';
    if (tool === 'weather') {
      const loc =
        result.location?.name
        || result.location_name
        || result.resolved_location?.name
        || result.location_hint
        || result.query
        || '';
      label = `Weather ✓${loc ? ' ' + loc : ''}`;
    } else if (tool === 'news') {
      label = itemCount > 0 ? `News ✓ ${itemCount}件` : 'News 結果なし';
    } else if (tool === 'search') {
      label = itemCount > 0 ? `Search ✓ ${itemCount}件` : 'Search 結果なし';
    } else {
      label = `${tool} ✓`;
    }
    if (!state.toolHistory.includes(label)) {
      state.toolHistory.push(label);
    }
  }

  function renderToolHistory(state) {
    if (!state?.toolHistory?.length) return;
    const output = document.getElementById('output') || document.getElementById('chat');
    if (!output) return;
    const row = document.createElement('div');
    row.className = 'lumen-tool-history';
    row.textContent = `TOOLS: ${state.toolHistory.join(' / ')}`;
    output.appendChild(row);
  }

  function handleJobEvent(event, stateOverride) {
    const state = stateOverride || jobState.get(event?.job_id) || null;
    if (!event || !event.type) return;

    if (event.type === 'tool_plan') {
      updateProgress(state, '🧰 ツール確認中...');
      log('info', 'lumen', `tool_plan: ${(event.tools || event.plan || []).length || 0}`);
    } else if (event.type === 'tool_call') {
      rememberStep(state, event);
      updateProgress(state, `🔧 ${(event.action || event.tool || 'tool')} 実行中...`);
    } else if (event.type === 'tool_result') {
      rememberToolHistory(state, event);
      if (state?.steps && typeof attachToolResult === 'function') {
        attachToolResult(state.steps, event);
      }
      const tool = String(event.tool || event.action || event.name || '').toLowerCase();
      if (tool === 'weather') {
        updateProgress(state, '天気情報を取得しました');
        return;
      }
      if (tool === 'news') {
        updateProgress(state, 'ニュース情報を取得しました');
        return;
      }
      if (tool === 'search' || event.tool === 'search') {
        const result = window.LumenTools?.unwrapToolPayload
          ? window.LumenTools.unwrapToolPayload(event)
          : event;
        const count = Number(result.item_count ?? result.metadata?.item_count ?? 0);
        if (count === 0) {
          updateProgress(state, '検索結果なし');
          return;
        }
        updateProgress(state, `検索結果 ${count}件`);
        return;
      }
      const text = window.LumenTools?.renderToolResult ? window.LumenTools.renderToolResult(event) : 'tool_result received';
      if (text) renderSystemMessage(text);
      updateProgress(state, `✓ ${(event.action || event.tool || 'tool')} 完了`);
    } else if (event.type === 'chat_step' || event.type === 'llm_thinking') {
      updateProgress(state, event.label || event.message || `🤔 考え中... ${event.step_num || ''}/${event.max_steps || ''}`);
    } else if (event.type === 'progress') {
      updateProgress(state, event.label || 'Working...');
    } else if (event.type === 'model_switching') {
      if (state?.progressCard && typeof setCard === 'function') setCard(state.progressCard, { label: event.message || 'Switching model...', action: `eta ${event.eta_sec || '?'}s` });
    } else if (event.type === 'model_ready') {
      if (state?.progressCard && typeof setCard === 'function') setCard(state.progressCard, { label: 'Working...', action: '' });
    } else if (event.type === 'done') {
      if (state) state.result = event.result || event.output || event.message || '';
    } else if (event.type === 'error') {
      if (state) state.error = event.error || event.message || 'Unknown error';
      renderSystemMessage('[Error] ' + (event.error || event.message || 'Unknown error'));
    }
  }

  async function finishJob(jobId, state, timedOut) {
    stopPolling(jobId);
    if (state?.progressCard?.remove) state.progressCard.remove();
    if (typeof stopTimer === 'function') stopTimer();
    if (timedOut) {
      if (typeof addMsg === 'function') addMsg('error', 'Job timed out or failed');
    } else if (state?.error) {
      if (typeof addMsg === 'function') addMsg('error', state.error);
    } else {
      const out = state?.result || '(no output)';
      const formattedOut = renderAssistantMessage(out);
      renderToolHistory(state);
      if (typeof playTTS === 'function') playTTS(formattedOut, 'chat');
      if (state?.steps?.length) {
        if (typeof addStepsBlock === 'function') addStepsBlock(state.steps);
        if (typeof renderStepsToOutput === 'function') renderStepsToOutput(state.steps);
      }
    }
    jobState.delete(jobId);
    setUiBusy(false);
  }

  function startPolling(jobId, project) {
    const state = jobState.get(jobId) || { steps: [], toolHistory: [], lastSeq: -1, pollCount: 0 };
    jobState.set(jobId, state);
    const maxPoll = 480;
    const tick = async () => {
      state.pollCount += 1;
      try {
        const pollData = await window.LumenAPI.pollLumenJob(jobId, project || getProject(), state.lastSeq);
        (pollData.steps || []).forEach((step) => {
          state.lastSeq = step.seq;
          const event = Object.assign({}, step.data || {}, { type: step.type, seq: step.seq, job_id: jobId });
          handleJobEvent(event, state);
        });
        if (pollData.status === 'done' || pollData.status === 'error') {
          await finishJob(jobId, state, false);
          return;
        }
      } catch (err) {
        console.warn('lumen poll error', err);
      }
      if (state.pollCount >= maxPoll) {
        await finishJob(jobId, state, true);
        return;
      }
      const timer = setTimeout(tick, 500);
      pollTimers.set(jobId, timer);
    };
    const timer = setTimeout(tick, 500);
    pollTimers.set(jobId, timer);
  }

  function stopPolling(jobId) {
    const timer = pollTimers.get(jobId);
    if (timer) clearTimeout(timer);
    pollTimers.delete(jobId);
  }

  async function submitCurrentMessage(messageOverride) {
    if (typeof busy !== 'undefined' && busy) return;
    const input = document.getElementById('input');
    const message = String(messageOverride !== undefined ? messageOverride : (input?.value || '')).trim();
    if (!message) return;
    if (input && messageOverride === undefined) {
      input.value = '';
      input.style.height = 'auto';
    }

    renderUserMessage(message);
    log('info', 'send', `[Lumen][${getProject()}] ${message}`);
    setUiBusy(true);
    const progressCard = typeof addProgressCard === 'function' ? addProgressCard('Working...') : null;
    if (typeof startTimer === 'function') startTimer();

    try {
      const submitData = await window.LumenAPI.submitLumenMessage(buildSubmitPayload(message));
      const jobId = submitData.job_id;
      if (!jobId) throw new Error('Lumen submit did not return job_id');
      if (typeof _currentJobId !== 'undefined') _currentJobId = jobId;
      const state = { progressCard, steps: [], toolHistory: [], lastSeq: -1, pollCount: 0, result: null, error: null };
      jobState.set(jobId, state);
      log('ok', 'lumen', `Chat job: ${jobId}`);
      startPolling(jobId, getProject());
    } catch (err) {
      if (progressCard?.remove) progressCard.remove();
      if (typeof stopTimer === 'function') stopTimer();
      if (typeof addMsg === 'function') addMsg('error', 'Request failed: ' + (err.message || String(err)));
      setUiBusy(false);
    }
  }

  function init() {
    if (window.LumenTools?.init) window.LumenTools.init();
  }

  window.Lumen = {
    init,
    submitCurrentMessage,
    buildSubmitPayload,
    collectChatHistory,
    renderUserMessage,
    renderAssistantMessage,
    renderSystemMessage,
    formatAssistantOutput,
    isHiddenUserFacingToolResult,
    rememberToolHistory,
    renderToolHistory,
    handleJobEvent,
    startPolling,
    stopPolling,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
}());
