/* Project Digital Twin inspection panel (PDT-13).
 *
 * Read-only client over /api/project-twin/*. The panel can inspect structure, behavior,
 * delivery, history and impact, expand nodes lazily, navigate to sources and filter by
 * confidence/status/revision. It NEVER calls a mutation or execution endpoint — it cannot
 * authorize execution, apply changes or alter workflow/approval state. Layout uses simple
 * flex/list markup so it stays usable on mobile.
 */
(function () {
  "use strict";

  const BASE = "/api/project-twin";
  const VIEWS = ["structure", "behavior", "delivery", "history", "impact"];

  // Node types grouped per view (Structure/Behavior/Delivery/History/Impact).
  const VIEW_TYPES = {
    structure: ["repository", "directory", "file", "module", "class", "function", "method", "api_route", "test", "fixture"],
    behavior: ["side_effect", "event", "action", "api_call", "behavior", "event_handler"],
    delivery: ["conversation", "message", "requirement", "constraint", "plan", "plan_item", "proposal", "run", "verification", "evidence"],
    history: ["architecture_decision", "task_outcome", "module_map", "risk", "incident", "nexus_evidence", "nexus_document", "nexus_report", "skill_activation"],
    impact: [],
  };

  async function postJson(path, body) {
    const res = await fetch(BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("project-twin request failed: " + res.status);
    return res.json();
  }

  async function getJson(path, params) {
    const qs = new URLSearchParams(params).toString();
    const res = await fetch(BASE + path + (qs ? "?" + qs : ""));
    if (!res.ok) throw new Error("project-twin request failed: " + res.status);
    return res.json();
  }

  const TwinPanel = {
    state: { projectId: "", view: "structure", minConfidence: 0, statuses: [], revisionId: null, cursor: null },

    health(projectId) {
      return getJson("/health", { project_id: projectId });
    },

    query(opts) {
      const s = this.state;
      return postJson("/query", {
        project_id: opts.projectId || s.projectId,
        node_types: opts.nodeTypes || VIEW_TYPES[opts.view || s.view] || [],
        statuses: opts.statuses || s.statuses,
        min_confidence: opts.minConfidence != null ? opts.minConfidence : s.minConfidence,
        revision_id: opts.revisionId || s.revisionId,
        limit: opts.limit || 100,
        cursor: opts.cursor || null,
      });
    },

    expandNode(projectId, canonicalRef) {
      return getJson("/node", { project_id: projectId, canonical_ref: canonicalRef });
    },

    tracePath(projectId, sourceRef, targetRef) {
      return postJson("/path", { project_id: projectId, source_ref: sourceRef, target_ref: targetRef || null });
    },

    assessImpact(projectId, changedRefs, changeKind) {
      return postJson("/impact", { project_id: projectId, changed_refs: changedRefs, change_kind: changeKind || "edit" });
    },

    context(projectId, objective, phase) {
      return postJson("/context", { project_id: projectId, objective: objective, phase: phase || "planning" });
    },

    // Render a bounded node list with lazy expansion and source navigation hooks.
    render(container, result) {
      if (!container) return;
      container.innerHTML = "";
      const list = document.createElement("ul");
      list.className = "twin-node-list";
      (result.nodes || []).forEach((n) => {
        const li = document.createElement("li");
        li.className = "twin-node twin-status-" + n.status;
        li.dataset.canonicalRef = n.canonical_ref;
        li.dataset.sourceRef = (n.source_refs && n.source_refs[0]) || n.source_ref || "";
        li.textContent = n.label + "  [" + n.node_type + " · " + n.status + " · " + Number(n.confidence).toFixed(2) + "]";
        li.addEventListener("click", () => TwinPanel._lazyExpand(li, result.project_id, n.canonical_ref));
        list.appendChild(li);
      });
      container.appendChild(list);
      if (result.truncated && result.cursor) {
        const more = document.createElement("button");
        more.className = "twin-load-more";
        more.textContent = "Load more";
        more.dataset.cursor = result.cursor;
        container.appendChild(more);
      }
    },

    async _lazyExpand(li, projectId, canonicalRef) {
      if (li.querySelector(".twin-neighbours")) return;
      const data = await TwinPanel.expandNode(projectId, canonicalRef);
      const ul = document.createElement("ul");
      ul.className = "twin-neighbours";
      (data.neighbours || []).forEach((nb) => {
        const c = document.createElement("li");
        c.textContent = (nb.direction === "out" ? "→ " : "← ") + nb.edge_type + ": " + nb.node.label;
        ul.appendChild(c);
      });
      li.appendChild(ul);
    },

    setView(view) {
      if (VIEWS.indexOf(view) === -1) return false;
      this.state.view = view;
      this.state.cursor = null;
      return true;
    },
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = TwinPanel;
  } else if (typeof window !== "undefined") {
    window.TwinPanel = TwinPanel;
  }
})();
