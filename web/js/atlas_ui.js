(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  const SUBVIEWS = Object.freeze(["start", "autopilot", "plan", "history", "activity", "runs", "execute", "patch", "review"]);

  function byId(id) {
    return root.document ? root.document.getElementById(id) : null;
  }

  function normalizeSubview(value) {
    const raw = String(value || "").trim();
    return SUBVIEWS.includes(raw) ? raw : "start";
  }

  function getWorkbenchRoot() {
    return byId("atlas-workbench-card");
  }

  function getLastRunIdFromDom() {
    const rootEl = getWorkbenchRoot();
    return rootEl?.dataset?.lastRunId || "";
  }

  function setRequirementStatus(message) {
    const el = byId("atlas-requirement-status");
    if (el) el.textContent = message || "Ready to start Atlas.";
  }

  function updateRequirementCharCount() {
    const input = byId("atlas-requirement-input");
    const count = byId("atlas-requirement-char-count");
    if (count) count.textContent = `${String(input?.value || "").length} chars`;
  }

  function clearRequirementInputDom(message) {
    const input = byId("atlas-requirement-input");
    if (input) input.value = "";
    updateRequirementCharCount();
    setRequirementStatus(message || "Requirement cleared.");
  }

  function updateResumeNotice(subview, options = {}) {
    const notice = byId("atlas-workbench-card-resume-notice");
    if (!notice) return;
    const current = normalizeSubview(subview || options.lastSubview);
    const labelMap = {
      start: "Start", plan: "Plan", runs: "Runs", execute: "Execute", patch: "Patch Review",
    };
    const label = labelMap[current] || "Start";
    const lastRun = String(options.lastRunId || "").trim();
    if (lastRun) {
      notice.textContent = `Atlas restored: ${label}. Last Run: ${lastRun}. Content is not auto-loaded. Use the resume buttons below.`;
    } else {
      notice.textContent = `Atlas restored: ${label}. No Last Run yet. Run Atlas once, load recent runs, or enter run_id.`;
    }
  }

  function applySubview(subview, options = {}) {
    const next = normalizeSubview(subview);
    const rootEl = getWorkbenchRoot();
    if (!rootEl) return next;
    rootEl.dataset.atlasCurrentSubview = next;
    rootEl.querySelectorAll("[data-atlas-subview-panel]").forEach((el) => {
      const active = el.getAttribute("data-atlas-subview-panel") === next;
      el.hidden = !active;
      el.style.display = active ? "" : "none";
    });
    rootEl.querySelectorAll("[data-atlas-subview-tab]").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-atlas-subview-tab") === next);
    });
    updateResumeNotice(next, options);
    if (options.focusSelector) {
      const focusEl = rootEl.querySelector(options.focusSelector);
      if (focusEl && typeof focusEl.focus === "function") focusEl.focus();
      if (focusEl && typeof focusEl.scrollIntoView === "function") focusEl.scrollIntoView({ block: "nearest" });
    }
    return next;
  }

  function updateWorkbenchSummary(summary = {}) {
    const actionEl = byId("atlas-workbench-summary-action");
    const lastRunEl = byId("atlas-workbench-summary-last-run");
    const statusEl = byId("atlas-workbench-summary-status");
    if (actionEl) actionEl.textContent = summary.nextAction || "Start Atlas";
    if (lastRunEl) lastRunEl.textContent = summary.currentRun || "-";
    if (statusEl) statusEl.textContent = summary.statusText || "pending / review pending / approval locked / job -";
  }

  function setWorkbenchCollapsed(collapsed) {
    const card = getWorkbenchRoot();
    const btn = byId("atlas-workbench-collapse-btn");
    if (!card) return;
    card.classList.toggle("is-collapsed", !!collapsed);
    card.dataset.atlasWorkbenchCollapsed = collapsed ? "true" : "false";
    if (btn) {
      btn.textContent = collapsed ? "Expand" : "Collapse";
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }
  }

  function toggleWorkbenchCollapse() {
    const card = getWorkbenchRoot();
    const collapsed = !(card?.classList.contains("is-collapsed"));
    setWorkbenchCollapsed(collapsed);
    return collapsed;
  }

  const api = {
    name: "atlas_ui",
    loaded: true,
    SUBVIEWS,
    byId,
    normalizeSubview,
    getWorkbenchRoot,
    setRequirementStatus,
    updateRequirementCharCount,
    clearRequirementInputDom,
    updateResumeNotice,
    applySubview,
    updateWorkbenchSummary,
    setWorkbenchCollapsed,
    toggleWorkbenchCollapse,
    getLastRunIdFromDom,
  };

  registry.atlasUi = Object.assign(registry.atlasUi || {}, api);
  root.AtlasUI = Object.assign(root.AtlasUI || {}, api);
}());
