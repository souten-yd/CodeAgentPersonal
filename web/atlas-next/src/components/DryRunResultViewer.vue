<template>
  <StatusCard title="Dry-run Result Viewer (SCALE-120 display-only)">
    <p><b>Dry-run artifact:</b> {{ dryRunArtifactLabel }}</p>
    <p><b>Latest run:</b> {{ latestRunLabel }}</p>
    <p><b>Workflow snapshot:</b> {{ snapshotLabel }}</p>
    <p><b>Source:</b> {{ sourceLabel }}</p>
    <p v-if="warnings.length"><b>Warnings:</b> {{ warnings.join(' | ') }}</p>
    <p><b>Backend-owned result note:</b> dry-run result metadata is displayed only when provided by backend workflow_state.</p>
    <p><b>Actions unavailable in SCALE-120:</b> Vue does not start dry-runs, capture artifacts, approve, execute, apply, verify, rollback or restore, retry, continue, or mutate files.</p>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatusCard from './StatusCard.vue'

type DryRunResultViewerSnapshot = {
  artifacts?: { dryRun?: boolean }
  diagnostics: { source: string, warnings?: string[] }
  workflowMetadata: {
    latestRunId?: string
    sourceDetail: string
    workflowSnapshotAvailable: boolean
  }
}

const props = defineProps<{ snapshot: DryRunResultViewerSnapshot }>()

const dryRunArtifactLabel = computed(() => {
  if (props.snapshot.artifacts?.dryRun === true) return 'available'
  if (props.snapshot.artifacts?.dryRun === false) return 'missing'
  return 'unknown'
})

const latestRunLabel = computed(() => props.snapshot.workflowMetadata.latestRunId ?? 'unknown')
const snapshotLabel = computed(() => props.snapshot.workflowMetadata.workflowSnapshotAvailable ? 'available' : 'unavailable')
const sourceLabel = computed(() => props.snapshot.workflowMetadata.sourceDetail || props.snapshot.diagnostics.source)
const warnings = computed(() => props.snapshot.diagnostics.warnings ?? [])
</script>
