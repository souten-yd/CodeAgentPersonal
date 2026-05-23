<template>
  <StatusCard title="Approval & Dry-run Readiness Preview (VUE18 read-only)">
    <p><b>Approval-required count:</b> {{ approvalRequiredCount }}</p>
    <p><b>Dry-run ready:</b> {{ dryRunReadyLabel }}</p>
    <p v-if="dryRunBlockedReason"><b>Dry-run blocked reason:</b> {{ dryRunBlockedReason }}</p>
    <p v-if="missingGates.length"><b>Missing readiness gates:</b> {{ missingGates.join(' | ') }}</p>
    <p v-if="readinessWarnings.length"><b>Readiness warnings:</b> {{ readinessWarnings.join(' | ') }}</p>
    <p v-if="approvalItems.length"><b>Approval-required items:</b></p>
    <ul v-if="approvalItems.length" class="compact-list">
      <li v-for="(item, i) in approvalItems" :key="i">{{ item }}</li>
    </ul>
    <p><b>Backend-owned metadata note:</b> Approval and dry-run readiness are backend-owned metadata only.</p>
    <p><b>Actions unavailable in Vue18:</b> Vue18 does not allow approval decisions, dry-run start, execute, apply, verify, rollback/restore, retry, or continue.</p>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatusCard from './StatusCard.vue'

const props = defineProps<{ result: Record<string, unknown> }>()

function pick(obj: unknown, keys: string[]): unknown {
  if (!obj || typeof obj !== 'object') return undefined
  const item = obj as Record<string, unknown>
  for (const key of keys) if (key in item) return item[key]
  return undefined
}

const planPool = computed(() => pick(props.result, ['plan_pool']) as Record<string, unknown> | undefined)
const plan = computed(() => pick(props.result, ['plan']) as Record<string, unknown> | undefined)
const rootMetadata = computed(() => pick(props.result, ['metadata']) as Record<string, unknown> | undefined)
const reviewResult = computed(() => pick(props.result, ['review_result']) as Record<string, unknown> | undefined)

const merged = computed<Record<string, unknown>>(() => ({ ...(rootMetadata.value ?? {}), ...(reviewResult.value ?? {}), ...(planPool.value ?? {}), ...(plan.value ?? {}) }))

const approvalRequiredCount = computed(() => {
  const raw = pick(merged.value, ['approval_required_count', 'approval_required'])
  if (typeof raw === 'number') return raw
  if (Array.isArray(raw)) return raw.length
  return 0
})
const dryRunReadyLabel = computed(() => {
  const raw = pick(merged.value, ['dry_run_ready'])
  if (raw === true) return 'true'
  if (raw === false) return 'false'
  return 'unknown'
})
const dryRunBlockedReason = computed(() => String(pick(merged.value, ['dry_run_blocked_reason']) ?? ''))
const missingGates = computed(() => {
  const raw = pick(merged.value, ['missing_readiness_gates', 'readiness_missing_gates'])
  return Array.isArray(raw) ? raw.map((v) => String(v)) : []
})
const readinessWarnings = computed(() => {
  const raw = pick(merged.value, ['readiness_warnings', 'warnings'])
  return Array.isArray(raw) ? raw.map((v) => String(v)) : []
})
const approvalItems = computed(() => {
  const raw = pick(merged.value, ['approval_required_items', 'approval_items'])
  if (!Array.isArray(raw)) return []
  return raw.slice(0, 10).map((r, i) => {
    const item = r && typeof r === 'object' ? r as Record<string, unknown> : {}
    return `${String(item.item_id ?? item.id ?? `item-${i + 1}`)}: ${String(item.title ?? item.label ?? 'untitled')} [status=${String(item.status ?? 'unknown')}]`
  })
})
</script>

<style scoped>
.compact-list { margin: 4px 0 8px 16px; }
</style>
