<template><main>
<h1>Atlas Next (Parallel Read-only Shell)</h1>
<p>Runtime remains Level 0 manual-only. Existing ui.html remains default. Backend workflow state remains authoritative.</p>
<WorkflowShell :snapshot="snapshot" />
<SafetySummary />
<ArtifactSummary :snapshot="snapshot" />
<DiagnosticsNotice />
</main></template>
<script setup lang="ts">import { onMounted, ref } from 'vue';import { fetchAtlasWorkflowSnapshot, type AtlasWorkflowSnapshot } from '../api/atlasClient';
import WorkflowShell from './WorkflowShell.vue';import SafetySummary from './SafetySummary.vue';import ArtifactSummary from './ArtifactSummary.vue';import DiagnosticsNotice from './DiagnosticsNotice.vue';
const snapshot=ref<AtlasWorkflowSnapshot>({autonomousExecutionEnabled:false,runtimeLevel:'level_0_manual_only'});onMounted(async()=>{snapshot.value=await fetchAtlasWorkflowSnapshot()})</script>
