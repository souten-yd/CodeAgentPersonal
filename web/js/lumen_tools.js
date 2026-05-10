(function () {
  function readValue(id, fallback) {
    const el = document.getElementById(id);
    if (!el) return fallback;
    if (el.type === 'checkbox') return el.checked ? 'auto' : 'off';
    const value = String(el.value || '').trim();
    return value || fallback;
  }

  function getToolPolicy() {
    return readValue('lumen-tool-policy', 'auto');
  }

  function getSearchPolicy() {
    if (typeof searchEnabled !== 'undefined') return searchEnabled ? 'auto' : 'off';
    return readValue('lumen-search-policy', 'auto');
  }

  function getLocation() {
    return readValue('lumen-location', '');
  }

  function getSearchBudget() {
    return {
      max_queries: 3,
      max_results_per_query: 5,
      max_fetch_pages: 3,
      max_total_chars: 12000,
      timeout_sec: 20,
    };
  }

  function getWeatherBudget() {
    return {
      max_geocoding_results: 3,
      forecast_days: 3,
      timeout_sec: 10,
    };
  }

  function getNewsBudget() {
    return {
      max_providers: 3,
      max_queries: 2,
      max_results_per_provider: 5,
      max_total_items: 15,
      max_fetch_pages: 0,
      timeout_sec: 20,
      save_to_nexus: false,
    };
  }

  function asArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function pickResult(event) {
    if (!event) return {};
    return event.result || event.output || event.data || event.tool_result || event;
  }

  function renderProviderStatusSummary(providerStatus) {
    const entries = Array.isArray(providerStatus)
      ? providerStatus
      : Object.entries(providerStatus || {}).map(([provider, value]) => Object.assign({ provider }, value || {}));
    if (!entries.length) return '';
    return entries.slice(0, 6).map((item) => {
      const name = item.provider || item.name || item.provider_name || 'provider';
      const status = item.status || (item.ok ? 'ok' : item.error ? 'failed' : 'unknown');
      const count = item.item_count ?? item.items_count ?? item.count ?? 0;
      return `${name}: ${status} (${count})`;
    }).join(', ');
  }

  function renderWeatherResult(result) {
    const data = result || {};
    const current = data.current || data.current_weather || data.now || {};
    const location = data.location || data.resolved_location || data.place || data.city || data.query || '';
    const temp = current.temperature_c ?? current.temp_c ?? data.temperature_c ?? data.temp_c ?? data.current_temperature_c;
    const condition = current.condition || current.weather || data.condition || data.summary || data.weather || '';
    const precipitation = current.precipitation_probability ?? current.precip_probability ?? data.precipitation_probability ?? data.precipitation_probability_max;
    const fetchedAt = data.fetched_at || data.generated_at || data.timestamp || current.time || '';
    const lines = ['🌤 Weather'];
    if (location) lines.push(`地域: ${location}`);
    if (temp !== undefined || condition) lines.push(`現在: ${temp !== undefined ? `${temp}°C` : '-'}${condition ? ` / ${condition}` : ''}`);
    if (precipitation !== undefined) lines.push(`降水確率: ${precipitation}%`);
    if (fetchedAt) lines.push(`取得時刻: ${fetchedAt}`);
    return lines.join('\n');
  }

  function newsItems(result) {
    return asArray(result.items || result.results || result.articles || result.headlines || result.news);
  }

  function renderNewsResult(result) {
    const data = result || {};
    const items = newsItems(data);
    const status = data.status || data.metadata?.status || 'ok';
    const providerStatus = data.provider_status || data.metadata?.provider_status || {};
    const providerSummary = renderProviderStatusSummary(providerStatus);
    const providers = data.providers || data.provider_names || Object.keys(providerStatus || {});
    const lines = ['📰 News', `status: ${status}`, `取得件数: ${data.item_count ?? data.total ?? items.length}`];
    if (providers && providers.length) lines.push(`主なprovider: ${providers.slice(0, 6).join(', ')}`);
    else if (providerSummary) lines.push(`provider: ${providerSummary}`);
    items.slice(0, 3).forEach((item, index) => {
      const title = item.title || item.headline || item.summary || item.text || '(no headline)';
      lines.push(`${index + 1}. ${String(title).slice(0, 160)}`);
    });
    lines.push('注意: headline/summary only。全文取得はしていません。');
    return lines.join('\n');
  }

  function renderSearchResult(result) {
    const data = result || {};
    const items = asArray(data.items || data.results || data.sources);
    const lines = ['🔎 Search', `取得件数: ${data.total ?? data.item_count ?? items.length}`];
    items.slice(0, 3).forEach((item, index) => {
      const title = item.title || item.name || item.url || item.snippet || '(no title)';
      lines.push(`${index + 1}. ${String(title).slice(0, 160)}`);
    });
    return lines.join('\n');
  }

  function renderToolResult(event) {
    const action = String(event?.action || event?.tool || event?.name || '').toLowerCase();
    const result = pickResult(event);
    if (action.includes('weather') || result.forecast || result.current_weather) return renderWeatherResult(result);
    if (action.includes('news') || result.articles || result.headlines) return renderNewsResult(result);
    if (action.includes('search') || result.sources || result.results) return renderSearchResult(result);
    const providerSummary = renderProviderStatusSummary(result.provider_status || result.metadata?.provider_status || {});
    const summary = result.summary || result.message || event?.summary || event?.thought || 'tool_result received';
    return [`🔧 Tool result`, `tool: ${event?.action || event?.tool || 'unknown'}`, String(summary).slice(0, 500), providerSummary ? `provider: ${providerSummary}` : ''].filter(Boolean).join('\n');
  }

  function init() {
    if (window.LumenAPI && window.LumenAPI.getLumenToolStatus) {
      window.LumenAPI.getLumenToolStatus().catch(() => null);
    }
  }

  window.LumenTools = {
    init,
    getToolPolicy,
    getSearchPolicy,
    getLocation,
    getSearchBudget,
    getWeatherBudget,
    getNewsBudget,
    renderToolResult,
    renderWeatherResult,
    renderNewsResult,
    renderProviderStatusSummary,
  };
}());
