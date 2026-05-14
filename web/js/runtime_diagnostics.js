(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});

  const DEFAULT_ENDPOINTS = Object.freeze([
    "/health",
    "/system/summary",
    "/models/db/status",
    "/model/status",
    "/debug/model-startup",
    "/audio/runtime/debug",
    "/nexus/web/status",
    "/nexus/jobs/active?limit=20",
  ]);

  function getApiBase() {
    return root.API || (root.location ? root.location.origin : "");
  }

  function resolveUrl(path) {
    if (typeof path === "string" && (path.startsWith("http://") || path.startsWith("https://"))) {
      return path;
    }
    return `${getApiBase()}${path}`;
  }

  function getFetcher() {
    return typeof root.fetchWithTimeout === "function" ? root.fetchWithTimeout : root.fetch;
  }

  async function fetchJson(path, options) {
    const opts = options || {};
    const fetcher = getFetcher();
    const timeoutMs = Number(opts.timeoutMs || 3500);
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = controller ? setTimeout(function () { controller.abort(); }, timeoutMs) : null;
    try {
      const response = await fetcher(resolveUrl(path), {
        method: "GET",
        signal: controller ? controller.signal : undefined,
      });
      const data = await response.json().catch(function () { return {}; });
      return {
        ok: response.ok,
        status: response.status,
        path: path,
        data: data,
      };
    } catch (error) {
      return {
        ok: false,
        status: 0,
        path: path,
        error: String(error && (error.message || error)),
      };
    } finally {
      if (timer) {
        clearTimeout(timer);
      }
    }
  }

  function maskSecrets(value) {
    if (Array.isArray(value)) {
      return value.map(maskSecrets);
    }
    if (value && typeof value === "object") {
      const out = {};
      Object.keys(value).forEach(function (key) {
        const lower = key.toLowerCase();
        if (
          lower.includes("token") ||
          lower.includes("secret") ||
          lower.includes("password") ||
          lower.includes("api_key") ||
          lower.includes("apikey") ||
          lower.includes("authorization") ||
          lower.includes("cookie")
        ) {
          out[key] = "***masked***";
        } else {
          out[key] = maskSecrets(value[key]);
        }
      });
      return out;
    }
    if (typeof value === "string") {
      return value.replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer ***masked***");
    }
    return value;
  }

  async function collectDiagnostics(options) {
    const opts = options || {};
    const startedAt = new Date().toISOString();
    const endpoints = Array.isArray(opts.endpoints) ? opts.endpoints : DEFAULT_ENDPOINTS;
    const timeoutMs = Number(opts.timeoutMs || 3500);
    const results = {};
    await Promise.all(endpoints.map(async function (path) {
      results[path] = await fetchJson(path, { timeoutMs: timeoutMs });
    }));
    return maskSecrets({
      generated_at: startedAt,
      app: "KasaneCore",
      user_agent: root.navigator ? root.navigator.userAgent : "",
      location_path: root.location ? root.location.pathname : "",
      endpoints: results,
    });
  }

  function formatDiagnosticBundle(bundle, mode) {
    const safe = maskSecrets(bundle || {});
    const targetMode = mode || "detailed";
    if (targetMode === "short") {
      return JSON.stringify({
        generated_at: safe.generated_at,
        app: safe.app,
        endpoints: Object.fromEntries(
          Object.entries(safe.endpoints || {}).map(function (entry) {
            const path = entry[0];
            const result = entry[1] || {};
            return [path, { ok: !!result.ok, status: result.status || 0, error: result.error || "" }];
          })
        ),
      }, null, 2);
    }
    return JSON.stringify(safe, null, 2);
  }

  const api = {
    name: "runtime_diagnostics",
    loaded: true,
    DEFAULT_ENDPOINTS: DEFAULT_ENDPOINTS,
    fetchJson: fetchJson,
    maskSecrets: maskSecrets,
    collectDiagnostics: collectDiagnostics,
    formatDiagnosticBundle: formatDiagnosticBundle,
  };

  registry.runtimeDiagnostics = Object.assign(registry.runtimeDiagnostics || {}, api);
  root.RuntimeDiagnostics = Object.assign(root.RuntimeDiagnostics || {}, api);
}());
