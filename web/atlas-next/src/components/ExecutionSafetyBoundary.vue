<template>
  <StatusCard title="Execution Safety Boundary (Display-only)">
    <ul>
      <li><b>Runtime level:</b> {{ snapshot.safety.runtimeLevel }}</li>
      <li><b>Vue execution enabled:</b> false</li>
      <li><b>Autonomous execution enabled:</b> false</li>
      <li><b>Backend workflow_state authoritative:</b> yes</li>
      <li><b>Dry-run-first preserved:</b> yes</li>
      <li><b>EXECUTE ONE ACTION preserved:</b> yes</li>
      <li><b>Execution actions in Vue:</b> unavailable</li>
      <li v-if="blockedReasons.length"><b>Blocked execution reasons:</b> {{ blockedReasons.join(' | ') }}</li>
    </ul>
    <p><b>Readiness gate checklist (metadata-only):</b></p>
    <ul class="compact-list">
      <li>snapshot/restore readiness: {{ gateState('snapshot') }}</li>
      <li>patch transaction readiness: {{ gateState('transaction') }}</li>
      <li>risk classification: {{ gateState('risk') }}</li>
      <li>allowlisted verification: {{ gateState('allowlist') }}</li>
      <li>dry-run/approval: {{ gateState('dryRun') }}</li>
      <li>rollback readiness: {{ gateState('rollback') }}</li>
      <li>artifact capture: {{ gateState('artifactCapture') }}</li>
      <li>stop/kill switch: {{ gateState('stop') }}</li>
      <li>loop bounds: {{ gateState('loopBound') }}</li>
      <li>remote git restrictions: {{ gateState('remoteGit') }}</li>
      <li>self-improvement gates: {{ gateState('selfImprovement') }}</li>
    </ul>
    <p><b>Vue cannot execute:</b> approval, dry-run start, execute, apply, verify, rollback/restore, retry, and continue remain unavailable in Vue.</p>
    <p><b>No execution endpoint is called from Vue.</b></p>
    <p><b>VUE21 note:</b> default-enable checkpoint only; not execution-enable.</p>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatusCard from './StatusCard.vue'
type ArtifactState = Record<string, boolean | undefined>
type LocalSnapshot = {
  safety: { runtimeLevel: string }
  artifacts: ArtifactState
  availableActions: Array<{ reason: string }>
}

const props = defineProps<{ snapshot: LocalSnapshot }>()

const blockedReasons = computed(() => props.snapshot.availableActions.map((a) => a.reason).filter((v, i, arr) => v && arr.indexOf(v) === i).slice(0, 3))

function gateState(key: string): string {
  const value = props.snapshot.artifacts[key]
  return value ? 'ready' : 'missing'
}
</script>

<style scoped>
.compact-list { margin: 4px 0 8px 16px; }
</style>
