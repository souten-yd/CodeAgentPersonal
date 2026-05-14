(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  registry.echoUi = Object.assign(registry.echoUi || {}, {
    name: "echo_ui",
    loaded: true
  });
})();
