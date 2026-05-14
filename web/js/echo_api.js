(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  function getApiBase() {
    return root.API || root.location.origin;
  }
  function resolveUrl(path) {
    if (typeof path === "string" && (path.startsWith("http://") || path.startsWith("https://"))) return path;
    return `${getApiBase()}${path}`;
  }
  function getFetcher() {
    return typeof root.fetchWithTimeout === "function" ? root.fetchWithTimeout : root.fetch;
  }
  async function request(path, options) {
    const fetcher = getFetcher();
    return fetcher(resolveUrl(path), options || {});
  }
  async function requestJson(path, options) {
    const response = await request(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = (data && (data.detail || data.error || data.message)) || response.statusText || `HTTP ${response.status}`;
      throw new Error(message);
    }
    return data;
  }
  function withQuery(path, params) {
    if (!params || typeof params !== "object") return path;
    const search = new URLSearchParams();
    Object.keys(params).forEach((key) => {
      const value = params[key];
      if (value === undefined || value === null || value === "") return;
      search.set(key, String(value));
    });
    const query = search.toString();
    return query ? `${path}?${query}` : path;
  }
  const api = {
    name: "echo_api",
    loaded: true,
    request,
    requestJson,
    getVoiceStatus: function getVoiceStatus() {
      return requestJson("/voice/status");
    },
    getAsrConfig: function getAsrConfig() {
      return requestJson("/asr/config");
    },
    getAudioRuntimeDebug: function getAudioRuntimeDebug() {
      return requestJson("/audio/runtime/debug");
    },
    getTtsStatus: function getTtsStatus() {
      return requestJson("/tts/status");
    },
    synthesizeTts: function synthesizeTts(payload) {
      return request("/tts/synthesize", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload || {}),
      });
    },
    synthesizeTtsBatch: function synthesizeTtsBatch(payload) {
      return request("/tts/synthesize-batch", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload || {}),
      });
    },
    listStyleBertVits2Models: function listStyleBertVits2Models() {
      return requestJson("/api/tts/style-bert-vits2/models");
    },
    previewStyleBertVits2Normalization: function previewStyleBertVits2Normalization(payload) {
      return requestJson("/api/tts/style-bert-vits2/preview-normalization", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload || {}),
      });
    },
    listEchoSessions: function listEchoSessions(params) {
      return requestJson(withQuery("/echo/sessions", params));
    },
    getEchoSaveStatus: function getEchoSaveStatus() {
      return requestJson("/echo/save-status");
    },
  };
  registry.echoApi = Object.assign(registry.echoApi || {}, api);
  root.EchoAPI = Object.assign(root.EchoAPI || {}, api);
}());
