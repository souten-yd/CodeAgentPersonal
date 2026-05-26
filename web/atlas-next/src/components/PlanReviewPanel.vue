<template>
  <StatusCard title="Atlas Plan Review (Read-only)">
    <p><b>Status:</b> {{ result.status }} | <b>Pool ID:</b> {{ result.pool_id }} | <b>Items:</b> {{ result.item_count }}</p>
    <p><b>Planner status:</b> {{ result.planner_status || 'unknown' }}</p>
    <p v-if="warnings.length"><b>Warnings:</b> {{ warnings.join(' | ') }}</p>
    <p v-if="errors.length" class="error"><b>Errors:</b> {{ errors.join(' | ') }}</p>
    <p v-if="clarificationSessionId"><b>Clarification session:</b> {{ clarificationSessionId }} (read-only in VUE17)</p>
    <p v-if="questions.length"><b>Planner questions:</b> {{ questions.length }}</p>
    <ul v-if="questions.length" class="compact-list">
      <li v-for="(q, i) in questions" :key="i">{{ q }}</li>
    </ul>
    <p v-if="requirementSummary"><b>Requirement summary:</b> {{ requirementSummary }}</p>
    <p v-if="planSummary"><b>Plan summary:</b> {{ planSummary }}</p>
    <section v-if="planPoolItems.length" class="planpool-summary" aria-label="Read-only PlanPool item summary">
      <p><b>PlanPool item summary:</b></p>
      <div class="planpool-grid">
        <article v-for="item in planPoolItems" :key="item.id" class="planpool-item">
          <p class="item-title">{{ item.title }}</p>
          <p class="item-meta">{{ item.id }} | status={{ item.status }}</p>
          <p class="item-meta">phase={{ item.phase }} | risk={{ item.risk }} | type={{ item.type }}</p>
        </article>
      </div>
    </section>
    <p v-if="items.length"><b>PlanPool item metadata:</b></p>
    <ul v-if="items.length" class="compact-list">
      <li v-for="(item, i) in items" :key="i">{{ item }}</li>
    </ul>
    <ApprovalDryRunPreview :result="result as unknown as Record<string, unknown>" />
    <p><b>Next step:</b> Review/clarify only. Approve/approval, dry-run, execute, apply, verify, rollback/restore, retry, and continue remain unavailable in Vue.</p>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatusCard from './StatusCard.vue'
import ApprovalDryRunPreview from './ApprovalDryRunPreview.vue'
import type { CreatePlanPoolResponse } from '../api/atlasClient'

const props = defineProps<{ result: CreatePlanPoolResponse }>()
const warnings = computed(() => props.result.warnings ?? [])
const errors = computed(() => props.result.errors ?? [])

const questions = computed(() => (props.result.questions ?? []).map((q, idx) => {
  if (typeof q === 'string') return q
  if (q && typeof q === 'object' && typeof (q as Record<string, unknown>).question === 'string') return String((q as Record<string, unknown>).question)
  if (q && typeof q === 'object' && typeof (q as Record<string, unknown>).text === 'string') return String((q as Record<string, unknown>).text)
  return `Question ${idx + 1}`
}))

const clarificationSessionId = computed(() => {
  const root = props.result as unknown as Record<string, unknown>
  const direct = root.clarification_session_id
  if (typeof direct === 'string' && direct.trim()) return direct
  const clar = root.clarification
  if (clar && typeof clar === 'object') {
    const id = (clar as Record<string, unknown>).session_id
    if (typeof id === 'string' && id.trim()) return id
  }
  return ''
})

const requirementSummary = computed(() => {
  const req = props.result.requirement
  if (!req) return ''
  return String((req.summary ?? req.requirement_summary ?? req.text ?? '')).slice(0, 300)
})
const planSummary = computed(() => {
  const plan = props.result.plan
  if (!plan) return ''
  return String((plan.summary ?? plan.plan_summary ?? '')).slice(0, 300)
})

const rawPlanPoolItems = computed(() => {
  const root = props.result as unknown as Record<string, unknown>
  const fromPlanPool = root.plan_pool && typeof root.plan_pool === 'object' ? (root.plan_pool as Record<string, unknown>).items : undefined
  const fromPlan = props.result.plan && typeof props.result.plan === 'object' ? (props.result.plan as Record<string, unknown>).items : undefined
  return Array.isArray(fromPlanPool) ? fromPlanPool : (Array.isArray(fromPlan) ? fromPlan : [])
})

const planPoolItems = computed(() => rawPlanPoolItems.value.slice(0, 6).map((it, i) => {
  const item = (it && typeof it === 'object') ? it as Record<string, unknown> : {}
  return {
    id: String(item.item_id ?? item.id ?? `item-${i + 1}`),
    title: String(item.title ?? item.label ?? 'untitled'),
    status: String(item.status ?? 'unknown'),
    phase: String(item.phase ?? 'unknown'),
    risk: String(item.risk ?? 'unknown'),
    type: String(item.type ?? 'unknown')
  }
}))

const items = computed(() => planPoolItems.value.map((item) => {
  return `${item.id}: ${item.title} [status=${item.status} phase=${item.phase} risk=${item.risk} type=${item.type}]`
}))
</script>

<style scoped>
.compact-list { margin: 4px 0 8px 16px; }
.error { color: #b91c1c; }
.planpool-summary {
  margin: 10px 0;
}
.planpool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
  margin-top: 6px;
}
.planpool-item {
  border: 1px solid #d8e0ea;
  border-radius: 6px;
  padding: 10px;
  background: #ffffff;
}
.item-title {
  margin: 0;
  font-weight: 800;
}
.item-meta {
  margin: 4px 0 0;
  color: #475569;
  font-size: 13px;
}
</style>
