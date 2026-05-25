<template>
  <main class="atlas-next-root">
    <header class="workbench-header">
      <p class="eyebrow">Atlas Workbench</p>
      <h1>Start Atlas, then review the plan.</h1>
      <p class="headline">Use the Start Atlas flow to define requirements, create planning metadata, and review backend-owned progress before any guarded execution step.</p>
      <p class="runtime-note">Runtime: {{ snapshot.safety.runtimeLevel }} / Vue execution controls: disabled</p>
    </header>
    <div class="workbench-layout">
      <section class="conversation-column">
        <RequirementInput />
        <ConversationWorkbench />
        <WorkflowShell :snapshot="snapshot" />
        <SafetySummary :snapshot="snapshot" />
        <ExecutionSafetyBoundary :snapshot="snapshot" />
        <GuardedExecutionReviewPanel :review="snapshot.guardedExecutionReview" />
        <DefaultReadinessPreflight />
        <Level1ReadinessPanel />
        <DryRunResultViewer :snapshot="snapshot" />
        <ArtifactSummary :snapshot="snapshot" />
        <DiagnosticsNotice :snapshot="snapshot" />
      </section>
      <ProgressRail :snapshot="snapshot" />
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchAtlasWorkflowSnapshot, type AtlasWorkflowSnapshot } from '../api/atlasClient'
import ConversationWorkbench from './ConversationWorkbench.vue'
import RequirementInput from './RequirementInput.vue'
import WorkflowShell from './WorkflowShell.vue'
import SafetySummary from './SafetySummary.vue'
import ExecutionSafetyBoundary from './ExecutionSafetyBoundary.vue'
import GuardedExecutionReviewPanel from './GuardedExecutionReviewPanel.vue'
import ArtifactSummary from './ArtifactSummary.vue'
import DiagnosticsNotice from './DiagnosticsNotice.vue'
import DefaultReadinessPreflight from './DefaultReadinessPreflight.vue'
import Level1ReadinessPanel from './Level1ReadinessPanel.vue'
import DryRunResultViewer from './DryRunResultViewer.vue'
import ProgressRail from './ProgressRail.vue'

const snapshot = ref<AtlasWorkflowSnapshot>({
  safety: {
    runtimeLevel: 'level_0_manual_only',
    autonomousExecutionEnabled: false,
    vueExecutionEnabled: false,
    backendWorkflowStateAuthoritative: true,
    dryRunFirstPreserved: true,
    executeOneActionPreserved: true
  },
  availableActions: [],
  artifacts: {},
  diagnostics: {
    source: 'placeholder',
    routeMounted: true,
    routePath: '/atlas-next',
    routeDefault: false,
    routeGuarded: true,
    distBacked: true,
    failClosed: true,
    staticMountDeferred: false,
    diagnosticsEndpoint: '/api/atlas/vue-next-preview/diagnostics',
    previewHealth: 'placeholder',
    backendContractReady: false,
    warnings: []
  },
  workflowMetadata: {
    planPoolAvailable: false,
    activePlanAvailable: false,
    lastReportAvailable: false,
    dataFreshness: 'unknown',
    sourceDetail: 'placeholder',
    workflowSnapshotAvailable: false
  },
  guardedExecutionReview: {
    checkpoint: 'PR-ATLAS-SCALE-126',
    displayOnly: true,
    backendAuthoritative: true,
    vueAuthoritative: false,
    callableExecutionRouteEnabled: false,
    executionEnabled: false,
    approvalActionEnabled: false,
    dryRunActionEnabled: false,
    executeActionEnabled: false,
    applyActionEnabled: false,
    verifyActionEnabled: false,
    rollbackActionEnabled: false,
    retryContinueActionEnabled: false,
    requiresDryRun: true,
    requiresApproval: true,
    requiresRuntimeTransition: true,
    endpointContractStatus: 'placeholder',
    reviewItems: [],
    blockedReasons: ['Runtime transition PR-ATLAS-SCALE-127 is required before execution can be callable.']
  },
  backendAuthorityNote: 'Backend workflow state remains authoritative. Vue Next does not compute execution eligibility.'
})

onMounted(async () => {
  snapshot.value = await fetchAtlasWorkflowSnapshot()
})
</script>

<style scoped>
:global(body) {
  margin: 0;
  background: #e8edf4;
  color: #0f172a;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.atlas-next-root {
  max-width: 1040px;
  margin: 0 auto;
  padding: 16px 16px 32px;
}
.workbench-header {
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  padding: 18px;
  background: #f8fbff;
}
.eyebrow {
  margin: 0 0 6px;
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}
h1 {
  margin: 0;
  font-size: 32px;
  line-height: 1.15;
}
.headline,
.runtime-note {
  margin: 8px 0 0;
  color: #334155;
}
.runtime-note {
  font-size: 13px;
}
.workbench-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 320px);
  gap: 14px;
  align-items: start;
}
.conversation-column {
  min-width: 0;
}
@media (max-width: 860px) {
  .workbench-layout {
    grid-template-columns: 1fr;
  }
}
</style>
