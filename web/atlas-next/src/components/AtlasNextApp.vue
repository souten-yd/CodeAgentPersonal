<template>
  <main>
    <h1>Atlas Next (Parallel Read-only Shell)</h1>
    <p>Runtime remains Level 0 manual-only. Existing ui.html remains default. Backend workflow state remains authoritative.</p>
    <WorkflowShell :snapshot="snapshot" />
    <SafetySummary :snapshot="snapshot" />
    <ArtifactSummary :snapshot="snapshot" />
    <DiagnosticsNotice :snapshot="snapshot" />
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchAtlasWorkflowSnapshot, type AtlasWorkflowSnapshot } from '../api/atlasClient'
import WorkflowShell from './WorkflowShell.vue'
import SafetySummary from './SafetySummary.vue'
import ArtifactSummary from './ArtifactSummary.vue'
import DiagnosticsNotice from './DiagnosticsNotice.vue'

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
    routeMounted: false,
    staticMountDeferred: true,
    backendContractReady: false,
    warnings: []
  },
  backendAuthorityNote: 'Backend workflow state remains authoritative. Vue Next does not compute execution eligibility.'
})

onMounted(async () => {
  snapshot.value = await fetchAtlasWorkflowSnapshot()
})
</script>
