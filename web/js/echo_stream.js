(function () {
  "use strict";
  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  registry.echoStream = Object.assign(registry.echoStream || {}, {
    name: "echo_stream",
    loaded: true
  });
})();
