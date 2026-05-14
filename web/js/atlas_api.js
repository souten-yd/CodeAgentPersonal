(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});

  function getApiBase() {
    return root.API || root.location.origin;
  }

  function resolveUrl(path) {
    if (typeof path === 'string' && (path.startsWith('http://') || path.startsWith('https://'))) return path;
    return `${getApiBase()}${path}`;
  }

  function getFetcher() {
    return typeof root.fetchWithTimeout === 'function' ? root.fetchWithTimeout : root.fetch;
  }

  async function request(path, options) {
    const fetcher = getFetcher();
    return fetcher(resolveUrl(path), options || {});
  }

  async function requestJson(path, options) {
    const response = await request(path, options);
    const data = await response.json();
    if (!response.ok) {
      const message = (data && (data.detail || data.error || data.message)) || response.statusText || `HTTP ${response.status}`;
      throw new Error(message);
    }
    return data;
  }

  async function createAutopilotPreview(payload) {
    return requestJson('/api/atlas/autopilot/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    });
  }

  async function generateAutopilotTaskPlan(autopilotId, taskId) {
    return requestJson(`/api/atlas/autopilot/${encodeURIComponent(autopilotId)}/tasks/${encodeURIComponent(taskId)}/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
  }

  async function prepareAutopilotExecutionPreview(autopilotId, taskId) {
    return requestJson(`/api/atlas/autopilot/${encodeURIComponent(autopilotId)}/tasks/${encodeURIComponent(taskId)}/execution-preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
  }

  async function listAtlasRuns(limit) {
    const n = typeof limit === 'number' ? limit : 20;
    return requestJson(`/api/atlas/runs?limit=${encodeURIComponent(String(n))}`);
  }

  async function getRunPatchDashboardResponse(runId) {
    return request(`/api/runs/${encodeURIComponent(runId)}/patch-dashboard`);
  }

  async function getRunPatchDashboard(runId) {
    return requestJson(`/api/runs/${encodeURIComponent(runId)}/patch-dashboard`);
  }

  async function getRunPatches(runId) {
    return requestJson(`/api/runs/${encodeURIComponent(runId)}/patches`);
  }

  async function getRunReport(runId) {
    return requestJson(`/api/runs/${encodeURIComponent(runId)}/report`);
  }

  async function getRunLog(runId) {
    return requestJson(`/api/runs/${encodeURIComponent(runId)}/log`);
  }

  registry.atlasApi = Object.assign(registry.atlasApi || {}, {
    name: 'atlas_api',
    loaded: true,
    request,
    requestJson,
    createAutopilotPreview,
    generateAutopilotTaskPlan,
    prepareAutopilotExecutionPreview,
    listAtlasRuns,
    getRunPatchDashboard,
    getRunPatchDashboardResponse,
    getRunPatches,
    getRunReport,
    getRunLog,
  });

  root.AtlasAPI = Object.assign(root.AtlasAPI || {}, {
    request,
    requestJson,
    createAutopilotPreview,
    generateAutopilotTaskPlan,
    prepareAutopilotExecutionPreview,
    listAtlasRuns,
    getRunPatchDashboard,
    getRunPatchDashboardResponse,
    getRunPatches,
    getRunReport,
    getRunLog,
  });
}());
