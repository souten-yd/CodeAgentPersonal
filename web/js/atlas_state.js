(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  registry.atlasState = Object.assign(registry.atlasState || {}, {
    name: "atlas_state",
    loaded: true
  });
})();
