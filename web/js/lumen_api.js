(function () {
  const FORBIDDEN_PAYLOAD_KEYS = [
    'approved_tasks',
    'recommended_model',
    'auto_select_option',
    'auto_skill_generation',
  ];

  function apiBase() {
    if (typeof API !== 'undefined') return API;
    return '';
  }

  function sanitizeSubmitPayload(payload) {
    const clean = Object.assign({}, payload || {});
    FORBIDDEN_PAYLOAD_KEYS.forEach((key) => { delete clean[key]; });
    clean.mode = 'chat';
    if (!clean.project) clean.project = 'default';
    if (!Array.isArray(clean.chat_history)) clean.chat_history = [];
    if (!clean.tool_policy) clean.tool_policy = 'auto';
    if (!clean.search_policy) clean.search_policy = 'auto';
    if (clean.location === undefined || clean.location === null) clean.location = '';
    if (!clean.search_budget) {
      clean.search_budget = {
        max_queries: 3,
        max_results_per_query: 5,
        max_fetch_pages: 3,
        max_total_chars: 12000,
        timeout_sec: 20,
      };
    }
    if (!clean.weather_budget) {
      clean.weather_budget = {
        max_geocoding_results: 3,
        forecast_days: 3,
        timeout_sec: 10,
      };
    }
    if (!clean.news_budget) {
      clean.news_budget = {
        max_providers: 3,
        max_queries: 2,
        max_results_per_provider: 5,
        max_total_items: 15,
        max_fetch_pages: 0,
        timeout_sec: 20,
        save_to_nexus: false,
      };
    }
    return clean;
  }

  async function postJson(path, payload) {
    const res = await fetch(apiBase() + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    });
    let data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) {
      const err = new Error((data && (data.detail || data.error)) || `HTTP ${res.status}`);
      err.status = res.status;
      err.payload = data;
      throw err;
    }
    return data;
  }

  async function getJson(path) {
    const res = await fetch(apiBase() + path);
    let data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) {
      const err = new Error((data && (data.detail || data.error)) || `HTTP ${res.status}`);
      err.status = res.status;
      err.payload = data;
      throw err;
    }
    return data;
  }

  async function submitLumenMessage(payload) {
    const clean = sanitizeSubmitPayload(payload);
    try {
      return await postJson('/lumen/submit', clean);
    } catch (err) {
      if (err && (err.status === 404 || err.status === 405 || err instanceof TypeError)) {
        return await postJson('/jobs/submit', clean);
      }
      throw err;
    }
  }

  function pollLumenJob(jobId, project, after) {
    const params = new URLSearchParams();
    params.set('project', project || 'default');
    if (after !== undefined && after !== null) params.set('after', String(after));
    return getJson(`/jobs/${encodeURIComponent(jobId)}/poll?${params.toString()}`);
  }

  function getLumenToolStatus() {
    return getJson('/lumen/tools/status');
  }

  function runLumenWeatherTool(payload) {
    return postJson('/lumen/tools/weather', payload || {});
  }

  function runLumenNewsTool(payload) {
    return postJson('/lumen/tools/news', payload || {});
  }

  window.LumenAPI = {
    submitLumenMessage,
    pollLumenJob,
    getLumenToolStatus,
    runLumenWeatherTool,
    runLumenNewsTool,
    _sanitizeSubmitPayload: sanitizeSubmitPayload,
  };
}());
