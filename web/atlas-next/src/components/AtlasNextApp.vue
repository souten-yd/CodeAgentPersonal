<template>
  <main class="atlas-next-root">
    <h1>Atlas Next (Parallel Read-only Shell)</h1>
    <p class="headline">Read-only supervision UI. Existing ui.html remains default. Guarded /atlas-next preview route mounted (non-default).</p>
    <p class="headline">Level 0 manual-only runtime. Backend workflow state remains authoritative.</p>
    <RequirementInput />
    <WorkflowShell :snapshot="snapshot" />
    <SafetySummary :snapshot="snapshot" />
    <ExecutionSafetyBoundary :snapshot="snapshot" />
    <GuardedExecutionReviewPanel :review="snapshot.guardedExecutionReview" />
    <DefaultReadinessPreflight />
    <Level1ReadinessPanel />
    <DryRunResultViewer :snapshot="snapshot" />
    <ArtifactSummary :snapshot="snapshot" />
    <DiagnosticsNotice :snapshot="snapshot" />
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchAtlasWorkflowSnapshot, type AtlasWorkflowSnapshot } from '../api/atlasClient'
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
.atlas-next-root { max-width: 960px; margin: 0 auto; padding: 8px 12px 24px; }
.headline { margin: 4px 0; color: #334155; }
</style>
