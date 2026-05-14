(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});

  const KEYS = Object.freeze({
    lastSubview: "atlas:lastSubview",
    lastRunId: "atlas:lastRunId",
    requirementInput: "atlas:requirementInput",
  });

  const state = {
    planWorkflowState: null,
  };

  function safeGet(key, fallback = "") {
    try {
      return root.localStorage.getItem(key) || fallback;
    } catch (_err) {
      return fallback;
    }
  }

  function safeSet(key, value) {
    try {
      root.localStorage.setItem(key, String(value ?? ""));
      return true;
    } catch (_err) {
      return false;
    }
  }

  function safeRemove(key) {
    try {
      root.localStorage.removeItem(key);
      return true;
    } catch (_err) {
      return false;
    }
  }

  function getLastSubview() {
    return safeGet(KEYS.lastSubview, "start");
  }

  function setLastSubview(value) {
    return safeSet(KEYS.lastSubview, value || "start");
  }

  function getLastRunId() {
    return safeGet(KEYS.lastRunId, "");
  }

  function setLastRunId(value) {
    return safeSet(KEYS.lastRunId, value || "");
  }

  function getRequirementInput() {
    return safeGet(KEYS.requirementInput, "");
  }

  function setRequirementInput(value) {
    return safeSet(KEYS.requirementInput, value || "");
  }

  function clearRequirementInput() {
    return safeRemove(KEYS.requirementInput);
  }

  function getPlanWorkflowState() {
    return state.planWorkflowState;
  }

  function setPlanWorkflowState(nextState) {
    state.planWorkflowState = nextState || null;
    return state.planWorkflowState;
  }

  const api = {
    name: "atlas_state",
    loaded: true,
    KEYS,
    safeGet,
    safeSet,
    safeRemove,
    getLastSubview,
    setLastSubview,
    getLastRunId,
    setLastRunId,
    getRequirementInput,
    setRequirementInput,
    clearRequirementInput,
    getPlanWorkflowState,
    setPlanWorkflowState,
  };

  registry.atlasState = Object.assign(registry.atlasState || {}, api);
  root.AtlasState = Object.assign(root.AtlasState || {}, api);
}());
