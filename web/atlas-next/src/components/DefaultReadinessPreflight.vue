<template>
  <section class="default-readiness" aria-label="default-readiness-preflight">
    <h2>Default Readiness Preflight (Display-only)</h2>
    <p>Current default route remains existing <code>ui.html</code>.</p>
    <p><code>/atlas-next</code> is available only as a guarded preview route and remains non-default.</p>
    <p><code>/atlas-next</code> remains mounted, guarded, dist-backed, fail-closed, and non-default.</p>
    <p>VUE21 is the earliest default-enable checkpoint (not an execution-enable checkpoint).</p>
    <h3>Default readiness status</h3>
    <ul>
      <li>ui default preserved</li>
      <li>Vue route guarded</li>
      <li>diagnostics available</li>
      <li>dist validation required</li>
      <li>backend authoritative</li>
      <li>runtime level_0_manual_only</li>
      <li>no execution capability</li>
      <li>no autonomous execution</li>
      <li>no root redirect</li>
      <li>no ui.html redirect</li>
    </ul>
    <h3>Route selection guard summary</h3>
    <ul>
      <li>Root route remains unchanged and does not redirect to <code>/atlas-next</code>.</li>
      <li><code>/ui.html</code> remains unchanged and does not redirect to <code>/atlas-next</code>.</li>
      <li>Route selection guard scope: read_only_default_readiness_metadata.</li>
    </ul>
    <p><strong>VUE20 does not change default routes.</strong></p>
  </section>
</template>

<style scoped>
.default-readiness { margin-top: 10px; padding: 10px; border: 1px solid #cbd5e1; border-radius: 8px; }
h2, h3 { margin: 0 0 8px; }
ul { margin: 6px 0 10px 18px; }
</style>
