(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  registry.runtimeDiagnostics = Object.assign(registry.runtimeDiagnostics || {}, {
    name: "runtime_diagnostics",
    loaded: true
  });
})();
