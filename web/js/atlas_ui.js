(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  registry.atlasUi = Object.assign(registry.atlasUi || {}, {
    name: "atlas_ui",
    loaded: true
  });
})();
