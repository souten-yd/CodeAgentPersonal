(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  registry.echoApi = Object.assign(registry.echoApi || {}, {
    name: "echo_api",
    loaded: true
  });
})();
