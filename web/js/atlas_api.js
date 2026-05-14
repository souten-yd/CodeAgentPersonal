(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  registry.atlasApi = Object.assign(registry.atlasApi || {}, {
    name: "atlas_api",
    loaded: true,
  });
}());
