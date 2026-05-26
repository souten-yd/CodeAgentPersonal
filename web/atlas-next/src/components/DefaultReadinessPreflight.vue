<template>
  <section class="default-readiness" aria-label="default-readiness-preflight">
    <h2>Default Readiness Preflight (Display-only)</h2>
    <p>Current root default is guarded Atlas Next when the prebuilt dist is valid.</p>
    <p><code>/ui/</code> remains available as the legacy fallback route.</p>
    <p><code>/atlas-next</code> remains mounted, guarded, dist-backed, and fail-closed.</p>
    <p>Default promotion does not grant Vue workflow authority or execution capability.</p>
    <h3>Default readiness status</h3>
    <ul>
      <li>guarded root default applied</li>
      <li>legacy UI fallback preserved</li>
      <li>diagnostics available</li>
      <li>dist validation required</li>
      <li>backend authoritative</li>
      <li>runtime level_0_manual_only for Vue execution surfaces</li>
      <li>no execution capability</li>
      <li>no autonomous execution</li>
      <li>no root redirect</li>
      <li>no ui.html redirect</li>
    </ul>
    <h3>Route selection guard summary</h3>
    <ul>
      <li>Root route serves Atlas Next only after valid dist verification.</li>
      <li>Root route fails closed to legacy UI when the dist is missing or invalid.</li>
      <li><code>/ui.html</code> remains unchanged and does not redirect to <code>/atlas-next</code>.</li>
      <li>Route selection guard scope: guarded_default_apply_metadata.</li>
    </ul>
    <p><strong>Default apply does not enable execution controls.</strong></p>
  </section>
</template>

<style scoped>
.default-readiness { margin-top: 10px; padding: 10px; border: 1px solid #cbd5e1; border-radius: 8px; }
h2, h3 { margin: 0 0 8px; }
ul { margin: 6px 0 10px 18px; }
</style>
