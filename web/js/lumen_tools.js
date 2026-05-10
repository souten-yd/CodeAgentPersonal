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

  function unwrapToolPayload(event) {
    const base = event?.result || event?.data || event?.tool_result || {};
    const metadata = event?.metadata || base?.metadata || {};
    if (typeof base === 'string') {
      return Object.assign({}, metadata, {
        content: base,
        metadata,
      });
    }
    return Object.assign({}, base, metadata, {
      content: base.content || event?.content || metadata.context || '',
      metadata,
    });
  }

  function pickResult(event) {
    if (!event) return {};
    return unwrapToolPayload(event);
  }

  function renderProviderStatusSummary(providerStatus) {
    const entries = Array.isArray(providerStatus)
      ? providerStatus
      : Object.entries(providerStatus || {}).map(([provider, value]) => Object.assign({ provider }, value || {}));
    if (!entries.length) return '';
    return entries.slice(0, 6).map((item) => {
      const name = item.provider || item.name || item.provider_name || 'provider';
      const status = item.overall_status || item.status || (item.ok ? 'ok' : item.error ? 'failed' : 'unknown');
      const count = item.item_count ?? item.items_count ?? item.count ?? item.results_count ?? 0;
      return `${name}: ${status} (${count})`;
    }).join(', ');
  }

  function formatLocation(value) {
    if (!value) return '';
    if (typeof value === 'string') return value;
    return [value.name, value.admin1, value.region, value.prefecture, value.country].filter(Boolean).join(' / ');
  }

  function renderWeatherResult(result) {
    const data = result || {};
    const current = data.current || data.current_weather || data.now || {};
    const location = formatLocation(data.location) || formatLocation(data.resolved_location) || [data.location_name, data.admin1, data.country].filter(Boolean).join(' / ') || data.place || data.city || data.query || data.location_hint || '';
    const error = data.error || data.status_error || (!data.ok && data.status && data.status !== 'ok' ? data.status : '');
    const message = data.message || data.reason || '';
    const temp = current.temperature_c ?? current.temp_c ?? data.temperature_c ?? data.temp_c ?? data.current_temperature_c ?? data.current_temperature;
    const condition = current.weather_text || current.condition || current.weather || data.weather_text || data.condition || data.summary || data.weather || '';
    const precipitation = current.precipitation_probability ?? current.precip_probability ?? data.precipitation_probability ?? data.precipitation_probability_max;
    const windSpeed = current.wind_speed ?? current.wind_speed_kmh ?? data.wind_speed ?? data.wind_speed_kmh;
    const fetchedAt = data.fetched_at || data.generated_at || data.timestamp || current.time || '';
    const lines = ['🌤 Weather'];
    if (error) {
      lines.push(`取得できませんでした: ${error}`);
      if (location) lines.push(`地域: ${location}`);
      if (message) lines.push(String(message).slice(0, 180));
      if (error === 'location_not_found') lines.push('より広い地域名、駅名、都道府県名で再入力してください。');
      return lines.join('\n');
    }
    if (location) lines.push(`地域: ${location}`);
    if (temp !== undefined || condition) lines.push(`現在: ${temp !== undefined ? `${temp}°C` : '-'}${condition ? ` / ${condition}` : ''}`);
    if (precipitation !== undefined) lines.push(`降水確率: ${precipitation}%`);
    if (windSpeed !== undefined) lines.push(`風速: ${windSpeed}km/h`);
    if (fetchedAt) lines.push(`取得時刻: ${fetchedAt}`);
    if (lines.length === 1 && data.content) lines.push(String(data.content).slice(0, 500));
    if (lines.length === 1) lines.push('取得できませんでした: weather_result_empty');
    return lines.join('\n');
  }

  function newsItems(result) {
    return asArray(
      result.top_topics ||
      result.metadata?.top_topics ||
      result.items ||
      result.results ||
      result.articles ||
      result.headlines ||
      result.news
    );
  }

  function renderNewsResult(result) {
    const data = result || {};
    const items = newsItems(data);
    const rawStatus = data.overall_status || data.metadata?.overall_status || data.status || 'unknown';
    const itemCount = data.item_count ?? data.metadata?.item_count ?? items.length;
    const status = Number(itemCount) === 0 ? 'failed' : rawStatus;
    const providerStatus = data.provider_status || data.metadata?.provider_status || [];
    const providerSummary = renderProviderStatusSummary(providerStatus);
    const sources = asArray(data.sources || data.metadata?.sources || []);
    const providers = asArray(data.providers || data.provider_names)
      .concat(sources.map((source) => source.provider || source.name || source.domain).filter(Boolean))
      .concat(Array.isArray(providerStatus) ? providerStatus.map((item) => item.provider || item.name).filter(Boolean) : Object.keys(providerStatus || {}));
    const uniqueProviders = Array.from(new Set(providers)).filter(Boolean);
    const lines = ['📰 News', `status: ${status}`, `取得件数: ${itemCount}`];
    if (providerSummary) lines.push(`provider: ${providerSummary}`);
    if (uniqueProviders.length) lines.push(`主なprovider: ${uniqueProviders.slice(0, 6).join(', ')}`);
    if (Number(itemCount) === 0) {
      lines.push('有効なニュース記事を取得できませんでした。');
      lines.push('推測によるニュース要約は行いません。');
      return lines.join('\n');
    }
    items.slice(0, 3).forEach((item, index) => {
      const title = item.title || item.headline || item.summary || item.text || '(no headline)';
      lines.push(`${index + 1}. ${String(title).slice(0, 160)}`);
    });
    lines.push('注意: headline/summary only。全文取得はしていません。');
    return lines.join('\n');
  }

  function isPlannedOnlySearch(data, action) {
    return Boolean(
      data.planned_only ||
      data.metadata?.planned_only ||
      data.executable === false ||
      data.metadata?.executable === false ||
      (action.includes('web') && !action.includes('search') && (data.item_count ?? data.metadata?.item_count ?? 0) === 0)
    );
  }

  function renderSearchResult(result, action) {
    const data = result || {};
    const items = asArray(data.items || data.results || data.sources);
    const itemCount = data.total ?? data.item_count ?? data.metadata?.item_count ?? items.length;
    if (isPlannedOnlySearch(data, action || '')) return '';
    if (Number(itemCount) === 0) return '検索結果はありませんでした。';
    const lines = ['🔎 Search', `取得件数: ${itemCount}`];
    items.slice(0, 3).forEach((item, index) => {
      const title = item.title || item.name || item.url || item.snippet || '(no title)';
      lines.push(`${index + 1}. ${String(title).slice(0, 160)}`);
    });
    return lines.join('\n');
  }

  function renderToolResult(event) {
    const result = pickResult(event);
    const action = String(event?.action || event?.tool || event?.name || result.tool || '').toLowerCase();
    if (action.includes('weather') || result.forecast || result.current_weather || result.current || result.weather_text || result.current_temperature !== undefined || result.location_name) return renderWeatherResult(result);
    if (action.includes('news') || result.top_topics || result.articles || result.headlines || result.metadata?.top_topics) return renderNewsResult(result);
    if (action.includes('search') || action.includes('web') || result.sources || result.results) return renderSearchResult(result, action);
    const providerSummary = renderProviderStatusSummary(result.provider_status || result.metadata?.provider_status || {});
    const summary = result.summary || result.message || event?.summary || event?.thought || 'tool_result received';
    return [`🔧 Tool result`, `tool: ${event?.action || event?.tool || result.tool || 'unknown'}`, String(summary).slice(0, 500), providerSummary ? `provider: ${providerSummary}` : ''].filter(Boolean).join('\n');
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
    unwrapToolPayload,
    renderWeatherResult,
    renderNewsResult,
    renderProviderStatusSummary,
  };
}());
