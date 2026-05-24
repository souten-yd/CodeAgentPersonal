<template>
  <StatusCard title="Level-1 Readiness Diagnostics (read-only)">
    <p><b>enabled:</b> {{ diagnostics?.enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>runtime_level:</b> {{ diagnostics?.runtime_level || 'unknown' }}</p>
    <p><b>level1_execution_enabled:</b> {{ diagnostics?.level1_execution_enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>callable_execution_endpoint_enabled:</b> {{ diagnostics?.callable_execution_endpoint_enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>vue_execution_controls_enabled:</b> {{ diagnostics?.vue_execution_controls_enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>advisory_only:</b> {{ diagnostics?.advisory_only ? 'true' : 'false' }}</p>
    <p class="advisory-note"><b>Display note:</b> backend workflow_state remains authoritative. Local metadata comparison below is advisory only, not a readiness decision, and does not compute execution eligibility and does not decide readiness.</p>

    <div class="metadata-actions" role="group" aria-label="Readiness metadata comparison actions">
      <button type="button" class="filter-btn" :disabled="!hasDiagnostics" @click="saveCurrentAsBaseline">Save current snapshot</button>
      <button type="button" class="filter-btn" :disabled="!hasBaseline" @click="useSavedBaseline">Use saved baseline</button>
      <button type="button" class="filter-btn" :disabled="!hasPastedJson" @click="usePastedBaseline">Use pasted baseline</button>
      <button type="button" class="filter-btn" @click="clearComparison">Clear comparison</button>
      <button type="button" class="filter-btn" :disabled="!hasDiagnostics" @click="copyReadinessJson">Copy readiness JSON</button>
      <button type="button" class="filter-btn" :disabled="!hasDiagnostics" @click="downloadReadinessJson">Download readiness JSON</button>
      <button type="button" class="filter-btn" :disabled="!hasDiagnostics" @click="copyVisibleGateSummary">Copy visible gate summary</button>
      <span class="metadata-status">{{ comparisonStatus }}</span>
    </div>
    <div class="metadata-actions" role="group" aria-label="Readiness local history actions">
      <button type="button" class="filter-btn" :disabled="!hasDiagnostics" @click="saveCurrentToHistory">Save to local history</button>
      <button type="button" class="filter-btn" :disabled="!selectedHistoryId" @click="useHistoryBaseline">Use selected history baseline</button>
      <button type="button" class="filter-btn" :disabled="!historyEntries.length" @click="clearHistory">Clear local history</button>
      <span class="metadata-status">{{ historyStatus }}</span>
    </div>
    <div class="comparison-box">
      <p><b>local history diff view:</b> local display-only; compares browser-stored snapshots/current diagnostics only.</p>
      <div class="diff-selectors">
        <select v-model="historyDiffBaselineId" :disabled="!historyEntries.length">
          <option value="">Select diff baseline snapshot</option>
          <option v-for="entry in historyEntries" :key="`baseline-${entry.id}`" :value="entry.id">{{ entry.label }} — {{ entry.saved_at }}</option>
        </select>
        <select v-model="historyDiffTargetId" :disabled="!historyEntries.length">
          <option value="">Select diff target snapshot</option>
          <option v-for="entry in historyEntries" :key="`target-${entry.id}`" :value="entry.id">{{ entry.label }} — {{ entry.saved_at }}</option>
        </select>
      </div>
      <div class="metadata-actions" role="group" aria-label="Readiness local history diff actions">
        <button type="button" class="filter-btn" :disabled="!canCompareHistoryEntries" @click="compareSelectedHistoryEntries">Compare selected history snapshots</button>
        <button type="button" class="filter-btn" :disabled="!canCompareCurrentToHistory" @click="compareCurrentToHistoryEntry">Compare current diagnostics to selected baseline</button>
        <button type="button" class="filter-btn" @click="clearHistoryDiffSelection">Clear diff selection</button>
        <span class="metadata-status">{{ historyDiffStatus }}</span>
      </div>
    </div>
    <div class="metadata-actions" role="group" aria-label="Readiness local history import export actions">
      <button type="button" class="filter-btn" :disabled="!historyEntries.length" @click="copyHistoryJson">Copy local history JSON</button>
      <button type="button" class="filter-btn" :disabled="!historyEntries.length" @click="downloadHistoryJson">Export local history JSON</button>
      <button type="button" class="filter-btn" :disabled="!hasHistoryImportJson" @click="importHistoryMerge">Merge imported history</button>
      <button type="button" class="filter-btn" :disabled="!hasHistoryImportJson" @click="importHistoryReplace">Replace local history</button>
      <button type="button" class="filter-btn" :disabled="!historyImportJson" @click="clearHistoryImportText">Clear import text</button>
      <input type="file" accept="application/json" @change="loadHistoryImportFile" />
      <span class="metadata-status">{{ historyImportStatus }}</span>
    </div>
    <textarea v-model="historyImportJson" rows="6" class="metadata-input" placeholder="Paste local history JSON array or object with history array."></textarea>
    <div class="comparison-box">
      <p><b>local history storage:</b> browser storage only; max entries: {{ HISTORY_MAX_ENTRIES }}</p>
      <select v-model="selectedHistoryId" :disabled="!historyEntries.length">
        <option value="">Select local history snapshot</option>
        <option v-for="entry in historyEntries" :key="entry.id" :value="entry.id">{{ entry.label }} — {{ entry.saved_at }}</option>
      </select>
      <ul v-if="historyEntries.length">
        <li v-for="entry in historyEntries" :key="entry.id">
          {{ entry.label }} — {{ entry.saved_at }}
          <button type="button" class="filter-btn" @click="deleteHistoryEntry(entry.id)">Delete</button>
        </li>
      </ul>
    </div>

    <textarea v-model="pastedSnapshotJson" rows="6" class="metadata-input" placeholder="Paste prior readiness JSON for local metadata comparison."></textarea>

    <div v-if="comparisonResult" class="comparison-box">
      <p><b>local metadata comparison:</b> available={{ comparisonResult.comparison_available ? 'true' : 'false' }}</p>
      <p v-if="comparisonResult.comparison_error"><b>comparison_error:</b> {{ comparisonResult.comparison_error }}</p>
      <ul v-if="comparisonResult.summary_delta">
        <li>required_gate_count Δ: {{ comparisonResult.summary_delta.required_gate_count }}</li>
        <li>missing_evidence_count Δ: {{ comparisonResult.summary_delta.missing_evidence_count }}</li>
        <li>satisfied_gate_count Δ: {{ comparisonResult.summary_delta.satisfied_gate_count }}</li>
        <li>unsatisfied_gate_count Δ: {{ comparisonResult.summary_delta.unsatisfied_gate_count }}</li>
      </ul>
      <ul>
        <li>enabled changed: {{ comparisonResult.disabled_status_delta.enabled_changed ? 'yes' : 'no' }}</li>
        <li>level1_execution_enabled changed: {{ comparisonResult.disabled_status_delta.level1_execution_changed ? 'yes' : 'no' }}</li>
        <li>callable_execution_endpoint_enabled changed: {{ comparisonResult.disabled_status_delta.callable_execution_endpoint_changed ? 'yes' : 'no' }}</li>
        <li>vue_execution_controls_enabled changed: {{ comparisonResult.disabled_status_delta.vue_execution_controls_changed ? 'yes' : 'no' }}</li>
        <li>runtime_level changed: {{ comparisonResult.disabled_status_delta.runtime_level_changed ? 'yes' : 'no' }}</li>
      </ul>
      <ul v-if="comparisonResult.added_gates.length || comparisonResult.removed_gates.length">
        <li>added gates: {{ comparisonResult.added_gates.join(', ') || '-' }}</li>
        <li>removed gates: {{ comparisonResult.removed_gates.join(', ') || '-' }}</li>
      </ul>
      <table v-if="comparisonResult.evidence_summary_delta_by_source.length" class="gate-table">
        <thead><tr><th>source</th><th>before_missing_evidence_count</th><th>after_missing_evidence_count</th><th>delta_missing_evidence_count</th></tr></thead>
        <tbody><tr v-for="row in comparisonResult.evidence_summary_delta_by_source" :key="row.source"><td>{{ row.source }}</td><td>{{ row.before_missing_evidence_count }}</td><td>{{ row.after_missing_evidence_count }}</td><td>{{ row.delta_missing_evidence_count }}</td></tr></tbody>
      </table>
      <div class="metadata-actions" role="group" aria-label="Readiness local history diff filtering controls">
        <label>Display filter:
          <select v-model="activeDiffFilter">
            <option value="all">Show all diff gates</option>
            <option value="status">Status changes</option>
            <option value="evidence">Evidence changes</option>
            <option value="blocker">Blocker reason changes</option>
            <option value="added">Added gates</option>
            <option value="removed">Removed gates</option>
          </select>
        </label>
        <span class="metadata-status">{{ diffFilterStatusLabel }}</span>
      </div>
      <div class="metadata-actions" role="group" aria-label="Readiness local history diff export actions">
        <button type="button" class="filter-btn" :disabled="!comparisonResult" @click="copyDiffJson">Copy diff JSON</button>
        <button type="button" class="filter-btn" :disabled="!comparisonResult" @click="downloadDiffJson">Export diff JSON</button>
        <button type="button" class="filter-btn" :disabled="!comparisonResult" @click="copyFilteredDiffSummary">Copy filtered diff summary</button>
        <button type="button" class="filter-btn" :disabled="!comparisonResult" @click="downloadFilteredDiffSummary">Export filtered diff summary</button>
        <button type="button" class="filter-btn" :disabled="!comparisonResult" @click="copyLabelFilteredDiffJson">Copy label-filtered diff JSON</button>
        <button type="button" class="filter-btn" :disabled="!comparisonResult" @click="downloadLabelFilteredDiffJson">Export label-filtered diff JSON</button>
        <button type="button" class="filter-btn" :disabled="!comparisonResult" @click="copyLabelFilteredDiffSummary">Copy label-filtered summary</button>
        <button type="button" class="filter-btn" :disabled="!comparisonResult" @click="downloadLabelFilteredDiffSummary">Export label-filtered summary</button>
        <span class="metadata-status">{{ diffExportStatus }}</span>
      </div>
      <div class="comparison-box">
        <p><b>local diff bookmarks:</b> browser-local/display-only markers for diff rows; never uploaded.</p>
        <div class="metadata-actions" role="group" aria-label="Readiness local history diff bookmark actions">
          <button type="button" class="filter-btn" :disabled="!bookmarkedDiffItems.length" @click="clearDiffBookmarks">Clear local bookmarks</button>
          <span class="metadata-status">{{ diffBookmarkStatus }}</span>
        </div>
        <ul v-if="bookmarkedDiffItems.length">
          <li v-for="item in bookmarkedDiffItems" :key="`saved-${item.id}`">{{ item.label }}</li>
        </ul>
      </div>
      <div class="comparison-box">
        <p><b>local diff labels:</b> browser-local/display-only labels for diff rows; never uploaded.</p>
        <div class="metadata-actions" role="group" aria-label="Readiness local history diff label filtering controls">
          <label>Label filter:
            <select v-model="activeDiffLabelFilter">
              <option v-for="opt in labelFilterOptions" :key="`label-filter-${opt.value}`" :value="opt.value">{{ opt.label }}</option>
            </select>
          </label>
          <button type="button" class="filter-btn" :disabled="activeDiffLabelFilter === 'all'" @click="clearDiffLabelFilter">Clear label filter</button>
          <span class="metadata-status">{{ labelFilterStatusText }}</span>
        </div>
        <div class="metadata-actions" role="group" aria-label="Readiness local history diff label actions">
          <button type="button" class="filter-btn" :disabled="!labeledDiffItems.length" @click="clearDiffLabels">Clear local labels</button>
          <span class="metadata-status">{{ diffLabelStatus }}</span>
        </div>
        <div class="metadata-actions" role="group" aria-label="Readiness local history diff label import actions">
          <button type="button" class="filter-btn" :disabled="!hasLabelImportText" @click="importDiffLabelsFromText('merge')">Merge imported labels</button>
          <button type="button" class="filter-btn" :disabled="!hasLabelImportText" @click="importDiffLabelsFromText('replace')">Replace local labels</button>
          <button type="button" class="filter-btn" :disabled="!Object.keys(diffLabelMap).length" @click="clearDiffLabels">Clear all local labels</button>
          <button type="button" class="filter-btn" :disabled="!labelImportText.trim()" @click="clearDiffLabelImportText">Clear import text</button>
          <input type="file" accept="application/json" @change="onDiffLabelImportFile" />
          <span class="metadata-status">{{ labelImportStatus }}</span>
        </div>
        <div class="comparison-box" v-if="pendingLabelImport">
          <p><b>local label conflict preview:</b> {{ importedLabelConflicts.length }} conflict(s) across {{ pendingLabelImport.importedCount }} imported label(s).</p>
          <p v-if="importedLabelConflicts.length"><b>conflict summary:</b> existing local labels differ from imported local labels for the ids below.</p>
          <ul v-if="importedLabelConflicts.length">
            <li v-for="conflict in importedLabelConflicts" :key="`label-conflict-${conflict.id}`">
              {{ conflict.id }} — existing: {{ conflict.existingLabel }} | imported: {{ conflict.importedLabel }}
            </li>
          </ul>
          <div class="metadata-actions" role="group" aria-label="Readiness local history diff label conflict resolution actions">
            <button type="button" class="filter-btn" :disabled="!importedLabelConflicts.length" @click="applyImportedLabelConflicts('keep-existing')">Keep existing labels</button>
            <button type="button" class="filter-btn" :disabled="!importedLabelConflicts.length" @click="applyImportedLabelConflicts('use-imported')">Use imported labels</button>
            <button type="button" class="filter-btn" :disabled="!importedLabelConflicts.length" @click="applyImportedLabelConflicts('clear-conflicts')">Clear conflicting labels</button>
            <button type="button" class="filter-btn" @click="clearLabelConflictPreview">Clear conflict preview</button>
            <span class="metadata-status">{{ labelConflictStatus }}</span>
          </div>
        </div>
        <p><b>local label import source:</b> browser-local/display-only; imported labels are never uploaded and never mutate backend.</p>
        <p v-if="labelImportFileName"><b>import file:</b> {{ labelImportFileName }}</p>
        <textarea v-model="labelImportText" rows="5" class="metadata-input" placeholder="Paste local diff label export JSON (local_diff_labels or local_diff_label_filtered_items)."></textarea>
        <ul v-if="labeledDiffItems.length">
          <li v-for="item in labeledDiffItems" :key="`label-${item.id}`">{{ item.label }} => {{ item.local_label }}</li>
        </ul>
        <p><b>label summary:</b> {{ labeledDiffSummaryText }}</p>
        <p><b>label filter summary:</b> {{ labelFilterSummaryText }}</p>
      </div>
      <div class="comparison-box">
        <p><b>local diff annotation:</b> browser-local/display-only notes for current diff view; never uploaded.</p>
        <textarea v-model="diffAnnotationText" rows="4" class="metadata-input" placeholder="Add local review notes for this displayed diff."></textarea>
        <div class="metadata-actions" role="group" aria-label="Readiness local history diff annotation actions">
          <button type="button" class="filter-btn" :disabled="!comparisonResult" @click="saveDiffAnnotationDraft">Save local annotation</button>
          <button type="button" class="filter-btn" :disabled="!diffAnnotationText.trim()" @click="clearDiffAnnotation">Clear local annotation</button>
          <span class="metadata-status">{{ diffAnnotationStatus }}</span>
        </div>
      </div>
      <ul>
        <li>Summary by change type: {{ diffChangeTypeSummaryText }}</li>
        <li>Summary by source: {{ diffSourceSummaryText }}</li>
        <li>Summary by before_status: {{ diffBeforeStatusSummaryText }}</li>
        <li>Summary by after_status: {{ diffAfterStatusSummaryText }}</li>
      </ul>
      <ul v-if="visibleAddedGates.length || visibleRemovedGates.length">
        <li>filtered added gates: {{ visibleAddedGates.join(', ') || '-' }}</li>
        <li v-for="gateId in visibleAddedGates" :key="`added-bookmark-${gateId}`"><button type="button" class="filter-btn" @click="toggleDiffBookmark(`added:${gateId}`)">Bookmark added gate {{ gateId }}</button> <select :value="diffLabelMap[`added:${gateId}`] || ''" @change="setDiffLabel(`added:${gateId}`, ($event.target as HTMLSelectElement).value)"> <option value="">No local label</option><option v-for="opt in DIFF_LABEL_OPTIONS" :key="`added-${gateId}-${opt}`" :value="opt">{{ opt }}</option></select><button type="button" class="filter-btn" @click="clearDiffLabel(`added:${gateId}`)">Clear label</button></li>
        <li>filtered removed gates: {{ visibleRemovedGates.join(', ') || '-' }}</li>
        <li v-for="gateId in visibleRemovedGates" :key="`removed-bookmark-${gateId}`"><button type="button" class="filter-btn" @click="toggleDiffBookmark(`removed:${gateId}`)">Bookmark removed gate {{ gateId }}</button> <select :value="diffLabelMap[`removed:${gateId}`] || ''" @change="setDiffLabel(`removed:${gateId}`, ($event.target as HTMLSelectElement).value)"> <option value="">No local label</option><option v-for="opt in DIFF_LABEL_OPTIONS" :key="`removed-${gateId}-${opt}`" :value="opt">{{ opt }}</option></select><button type="button" class="filter-btn" @click="clearDiffLabel(`removed:${gateId}`)">Clear label</button></li>
      </ul>
      <table v-if="visibleChangedGates.length" class="gate-table">
        <thead><tr><th>gate_id</th><th>before_status</th><th>after_status</th><th>before_evidence_available</th><th>after_evidence_available</th><th>before_blocker_reason</th><th>after_blocker_reason</th></tr></thead>
        <tbody><tr v-for="gate in visibleChangedGates" :key="gate.gate_id"><td>{{ gate.gate_id }}<button type="button" class="filter-btn" @click="toggleDiffBookmark(`changed:${gate.gate_id}`)">Bookmark changed gate</button> <select :value="diffLabelMap[`changed:${gate.gate_id}`] || ''" @change="setDiffLabel(`changed:${gate.gate_id}`, ($event.target as HTMLSelectElement).value)"> <option value="">No local label</option><option v-for="opt in DIFF_LABEL_OPTIONS" :key="`changed-${gate.gate_id}-${opt}`" :value="opt">{{ opt }}</option></select><button type="button" class="filter-btn" @click="clearDiffLabel(`changed:${gate.gate_id}`)">Clear label</button></td><td>{{ gate.before_status }}</td><td>{{ gate.after_status }}</td><td>{{ gate.before_evidence_available }}</td><td>{{ gate.after_evidence_available }}</td><td>{{ gate.before_blocker_reason || '-' }}</td><td>{{ gate.after_blocker_reason || '-' }}</td></tr></tbody>
      </table>
    </div>
  </StatusCard>

<!-- Legacy compatibility tokens: test_requirement mutable evidence_required  evidence_required  Display filter: Show all gates Missing evidence only Backend-owned only Frontend-owned only Summary by owner Summary by source Summary by current_status mutation_performed execution_performed activeFilter summarizeBy( key: 'owner' | 'source' | 'current_status' ownerSummary sourceSummary statusSummary not execution eligibility -->

</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import StatusCard from './StatusCard.vue'
import { fetchLevel1ReadinessDiagnostics, type AtlasLevel1ReadinessDiagnostics, type AtlasLevel1ReadinessGateSource } from '../api/atlasClient'

type SnapshotComparisonResult = {
  summary_delta: { required_gate_count: number, missing_evidence_count: number, satisfied_gate_count: number, unsatisfied_gate_count: number } | null
  disabled_status_delta: { enabled_changed: boolean, level1_execution_changed: boolean, callable_execution_endpoint_changed: boolean, vue_execution_controls_changed: boolean, runtime_level_changed: boolean }
  evidence_summary_delta_by_source: Array<{ source: string, before_missing_evidence_count: number, after_missing_evidence_count: number, delta_missing_evidence_count: number }>
  changed_gates: Array<{ gate_id: string, before_status: string, after_status: string, before_evidence_available: boolean, after_evidence_available: boolean, before_blocker_reason: string, after_blocker_reason: string }>
  added_gates: string[]
  removed_gates: string[]
  comparison_available: boolean
  comparison_error: string | null
}

const diagnostics = ref<AtlasLevel1ReadinessDiagnostics | null>(null)
const baselineSnapshot = ref<AtlasLevel1ReadinessDiagnostics | null>(null)
const pastedSnapshotJson = ref('')
const comparisonResult = ref<SnapshotComparisonResult | null>(null)
const comparisonStatus = ref('Local metadata comparison idle.')
const hasDiagnostics = computed(() => diagnostics.value !== null)
const hasBaseline = computed(() => baselineSnapshot.value !== null)
const hasPastedJson = computed(() => pastedSnapshotJson.value.trim().length > 0)

type DiffFilter = 'all' | 'status' | 'evidence' | 'blocker' | 'added' | 'removed'
const activeDiffFilter = ref<DiffFilter>('all')
const visibleChangedGates = computed(() => {
  const result = comparisonResult.value
  if (!result) return []
  if (activeDiffFilter.value === 'added' || activeDiffFilter.value === 'removed') return []
  if (activeDiffFilter.value === 'all') return result.changed_gates
  if (activeDiffFilter.value === 'status') return result.changed_gates.filter((g) => g.before_status !== g.after_status)
  if (activeDiffFilter.value === 'evidence') return result.changed_gates.filter((g) => g.before_evidence_available !== g.after_evidence_available)
  return result.changed_gates.filter((g) => (g.before_blocker_reason || '') !== (g.after_blocker_reason || ''))
})
const visibleAddedGates = computed(() => { const result = comparisonResult.value; if (!result) return []; return activeDiffFilter.value === 'all' || activeDiffFilter.value === 'added' ? result.added_gates : [] })
const visibleRemovedGates = computed(() => { const result = comparisonResult.value; if (!result) return []; return activeDiffFilter.value === 'all' || activeDiffFilter.value === 'removed' ? result.removed_gates : [] })
const diffFilterStatusLabel = computed(() => `Local display-only diff filter: ${activeDiffFilter.value}`)

function summarizeBy(rows: string[]): string {
  if (!rows.length) return '-'
  const counts = new Map<string, number>()
  rows.forEach((k) => counts.set(k || 'unknown', (counts.get(k || 'unknown') || 0) + 1))
  return [...counts.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([k,v]) => `${k}:${v}`).join(', ')
}
const diffChangeTypeSummaryText = computed(() => {
  const result = comparisonResult.value
  if (!result) return '-'
  const tokens = [
    ...result.changed_gates.filter((g)=>g.before_status!==g.after_status).map(()=>'status_change'),
    ...result.changed_gates.filter((g)=>g.before_evidence_available!==g.after_evidence_available).map(()=>'evidence_change'),
    ...result.changed_gates.filter((g)=>(g.before_blocker_reason||'')!==(g.after_blocker_reason||'')).map(()=>'blocker_reason_change'),
    ...result.added_gates.map(()=>'added_gate'),
    ...result.removed_gates.map(()=>'removed_gate'),
  ]
  return summarizeBy(tokens)
})
const diffSourceSummaryText = computed(() => summarizeBy(visibleChangedGates.value.map((g) => {
  const target = diagnostics.value?.gate_source_map.find((s) => s.gate_id === g.gate_id)
  return target?.source || 'unknown'
})))
const diffBeforeStatusSummaryText = computed(() => summarizeBy(visibleChangedGates.value.map((g) => g.before_status || 'unknown')) )
const diffAfterStatusSummaryText = computed(() => summarizeBy(visibleChangedGates.value.map((g) => g.after_status || 'unknown')) )


const diffExportStatus = ref('Local diff export idle.')
const DIFF_ANNOTATION_STORAGE_KEY = 'atlas.level1.readiness.diff.annotation.draft'
const DIFF_BOOKMARK_STORAGE_KEY = 'atlas.level1.readiness.diff.bookmarks'
const DIFF_LABEL_STORAGE_KEY = 'atlas.level1.readiness.diff.labels'
const DIFF_LABEL_OPTIONS = ['Needs review', 'Evidence issue', 'Blocker changed', 'Resolved', 'Follow up', 'Ignore locally'] as const
const diffAnnotationText = ref('')
const diffAnnotationStatus = ref('Local diff annotation idle.')
const diffBookmarkIds = ref<string[]>([])
const diffBookmarkStatus = ref('Local diff bookmarks idle.')
const diffLabelMap = ref<Record<string, string>>({})
const diffLabelStatus = ref('Local diff labels idle.')
const labelImportText = ref('')
const labelImportStatus = ref('Local diff label import idle.')
const labelImportFileName = ref('')
const pendingLabelImport = ref<{ labels: Record<string, string>, importedCount: number, skipped: number } | null>(null)
const importedLabelConflicts = ref<Array<{ id: string, existingLabel: string, importedLabel: string }>>([])
const labelConflictStatus = ref('Local label conflict preview idle.')
const hasLabelImportText = computed(() => labelImportText.value.trim().length > 0)
type DiffLabelFilter = 'all' | 'unlabeled' | (typeof DIFF_LABEL_OPTIONS)[number]
const activeDiffLabelFilter = ref<DiffLabelFilter>('all')


const allDiffBookmarkItems = computed(() => {
  const result = comparisonResult.value
  if (!result) return [] as Array<{id:string,label:string,type:string}>
  const changed = result.changed_gates.map((g)=>({id:`changed:${g.gate_id}`,label:`changed gate: ${g.gate_id} (${g.before_status}→${g.after_status})`,type:'changed'}))
  const added = result.added_gates.map((gateId)=>({id:`added:${gateId}`,label:`added gate: ${gateId}`,type:'added'}))
  const removed = result.removed_gates.map((gateId)=>({id:`removed:${gateId}`,label:`removed gate: ${gateId}`,type:'removed'}))
  return [...changed,...added,...removed]
})
const bookmarkedDiffItems = computed(() => allDiffBookmarkItems.value.filter((item)=>diffBookmarkIds.value.includes(item.id)))
const bookmarkedDiffSummaryText = computed(() => bookmarkedDiffItems.value.map((item)=>item.label).join(' | ') || '-')
const labeledDiffItems = computed(() => allDiffBookmarkItems.value
  .filter((item) => typeof diffLabelMap.value[item.id] === 'string' && diffLabelMap.value[item.id].trim())
  .map((item) => ({ ...item, local_label: diffLabelMap.value[item.id] })))
const labeledDiffSummaryText = computed(() => labeledDiffItems.value.map((item) => `${item.local_label}:${item.id}`).join(' | ') || '-')
const labelFilterOptions = computed(() => [
  { value: 'all', label: 'Show all labels' },
  { value: 'unlabeled', label: 'Show unlabeled only' },
  ...DIFF_LABEL_OPTIONS.map((value) => ({ value, label: `Label: ${value}` })),
])
const visibleDiffItemsForLabelFilter = computed(() => {
  if (activeDiffLabelFilter.value === 'all') return allDiffBookmarkItems.value
  if (activeDiffLabelFilter.value === 'unlabeled') return allDiffBookmarkItems.value.filter((item) => !(diffLabelMap.value[item.id] || '').trim())
  return allDiffBookmarkItems.value.filter((item) => diffLabelMap.value[item.id] === activeDiffLabelFilter.value)
})
const labelFilterSummaryText = computed(() => `visible_items=${visibleDiffItemsForLabelFilter.value.length}/${allDiffBookmarkItems.value.length}`)
const labelFilterStatusText = computed(() => `Local label filter: ${activeDiffLabelFilter.value} (display-only)`)
function clearDiffLabelFilter(): void { activeDiffLabelFilter.value = 'all' }
function toggleDiffBookmark(id: string): void {
  diffBookmarkIds.value = diffBookmarkIds.value.includes(id) ? diffBookmarkIds.value.filter((v)=>v!==id) : [...diffBookmarkIds.value,id]
  saveDiffBookmarks()
  diffBookmarkStatus.value = diffBookmarkIds.value.includes(id) ? 'Bookmarked local diff item.' : 'Removed local diff bookmark.'
}
function clearDiffBookmarks(): void { diffBookmarkIds.value = []; if (typeof window!=='undefined') window.localStorage.removeItem(DIFF_BOOKMARK_STORAGE_KEY); diffBookmarkStatus.value='Cleared local diff bookmarks.' }

function setDiffLabel(id: string, label: string): void {
  if (!label) {
    clearDiffLabel(id)
    return
  }
  diffLabelMap.value = { ...diffLabelMap.value, [id]: label }
  saveDiffLabels()
  diffLabelStatus.value = 'Updated local diff label.'
}
function clearDiffLabel(id: string): void {
  if (!(id in diffLabelMap.value)) return
  const next = { ...diffLabelMap.value }
  delete next[id]
  diffLabelMap.value = next
  saveDiffLabels()
  diffLabelStatus.value = 'Cleared local diff label.'
}
function clearDiffLabels(): void {
  diffLabelMap.value = {}
  if (typeof window !== 'undefined') window.localStorage.removeItem(DIFF_LABEL_STORAGE_KEY)
  diffLabelStatus.value = 'Cleared local diff labels.'
}
function saveDiffLabels(): void { if (typeof window !== 'undefined') window.localStorage.setItem(DIFF_LABEL_STORAGE_KEY, JSON.stringify(diffLabelMap.value)) }
function loadDiffLabels(): void { try { if (typeof window==='undefined') return; const raw=window.localStorage.getItem(DIFF_LABEL_STORAGE_KEY); if (!raw) return; const parsed=JSON.parse(raw); if (parsed && typeof parsed==='object' && !Array.isArray(parsed)) { const labels: Record<string, string> = {}; for (const [k, v] of Object.entries(parsed)) { if (typeof k === 'string' && typeof v === 'string') labels[k] = v } diffLabelMap.value = labels } } catch {} }
function parseImportedDiffLabels(payload: unknown): { labels: Record<string, string>, skipped: number, importedCount: number } {
  const source = payload && typeof payload === 'object' && !Array.isArray(payload)
    ? ((payload as { local_diff_labels?: unknown, local_diff_label_filtered_items?: unknown }).local_diff_labels
      ?? (payload as { local_diff_label_filtered_items?: unknown }).local_diff_label_filtered_items
      ?? payload)
    : payload
  const labels: Record<string, string> = {}
  let skipped = 0
  let importedCount = 0
  const consumeRecord = (id: unknown, label: unknown) => {
    if (typeof id !== 'string' || !id.trim() || typeof label !== 'string' || !DIFF_LABEL_OPTIONS.includes(label as (typeof DIFF_LABEL_OPTIONS)[number])) {
      skipped += 1
      return
    }
    labels[id] = label
    importedCount += 1
  }
  if (Array.isArray(source)) {
    for (const item of source) {
      if (item && typeof item === 'object' && !Array.isArray(item)) consumeRecord((item as { id?: unknown }).id, (item as { local_label?: unknown, label?: unknown }).local_label ?? (item as { label?: unknown }).label)
      else skipped += 1
    }
  } else if (source && typeof source === 'object') {
    for (const [id, value] of Object.entries(source as Record<string, unknown>)) consumeRecord(id, value)
  }
  return { labels, skipped, importedCount }
}

function previewImportedDiffLabels(labels: Record<string, string>): Array<{ id: string, existingLabel: string, importedLabel: string }> {
  return Object.entries(labels)
    .filter(([id, importedLabel]) => typeof diffLabelMap.value[id] === 'string' && diffLabelMap.value[id] !== importedLabel)
    .map(([id, importedLabel]) => ({ id, existingLabel: diffLabelMap.value[id], importedLabel }))
}

function importDiffLabelsFromText(mode: 'merge' | 'replace'): void {
  const text = labelImportText.value.trim()
  if (!text) {
    labelImportStatus.value = 'No import JSON provided.'
    return
  }
  try {
    const parsed = JSON.parse(text)
    const result = parseImportedDiffLabels(parsed)
    pendingLabelImport.value = result
    importedLabelConflicts.value = previewImportedDiffLabels(result.labels)
    labelConflictStatus.value = importedLabelConflicts.value.length
      ? `Previewed ${importedLabelConflicts.value.length} local conflict(s).`
      : 'No local label conflicts detected.'
    const nextLabels = mode === 'replace' ? { ...result.labels } : { ...diffLabelMap.value, ...result.labels }
    diffLabelMap.value = nextLabels
    saveDiffLabels()
    diffLabelStatus.value = `Updated local diff labels (${mode}).`
    labelImportStatus.value = `Imported ${result.importedCount} label(s); skipped ${result.skipped} invalid item(s) (${mode}).`
  } catch {
    labelImportStatus.value = 'Import failed: invalid JSON.'
    pendingLabelImport.value = null
    importedLabelConflicts.value = []
    labelConflictStatus.value = 'Invalid JSON; conflict preview not available.'
  }
}

function applyImportedLabelConflicts(mode: 'keep-existing' | 'use-imported' | 'clear-conflicts'): void {
  const pending = pendingLabelImport.value
  if (!pending || !importedLabelConflicts.value.length) return
  const next = { ...diffLabelMap.value }
  for (const conflict of importedLabelConflicts.value) {
    if (mode === 'keep-existing') next[conflict.id] = conflict.existingLabel
    else if (mode === 'use-imported') next[conflict.id] = conflict.importedLabel
    else delete next[conflict.id]
  }
  diffLabelMap.value = next
  saveDiffLabels()
  diffLabelStatus.value = `Applied local label conflict resolution (${mode}).`
  labelConflictStatus.value = `Applied conflict resolution: ${mode}.`
}

function clearLabelConflictPreview(): void {
  pendingLabelImport.value = null
  importedLabelConflicts.value = []
  labelConflictStatus.value = 'Cleared local label conflict preview.'
}
function clearDiffLabelImportText(): void {
  labelImportText.value = ''
  labelImportFileName.value = ''
  labelImportStatus.value = 'Cleared local diff label import text.'
  clearLabelConflictPreview()
}
function onDiffLabelImportFile(event: Event): void {
  const input = event.target as HTMLInputElement | null
  const file = input?.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    labelImportText.value = typeof reader.result === 'string' ? reader.result : ''
    labelImportFileName.value = file.name
    labelImportStatus.value = `Loaded import file: ${file.name}`
  }
  reader.onerror = () => { labelImportStatus.value = `Failed to read import file: ${file.name}` }
  reader.readAsText(file)
  if (input) input.value = ''
}

function saveDiffBookmarks(): void { if (typeof window!=='undefined') window.localStorage.setItem(DIFF_BOOKMARK_STORAGE_KEY, JSON.stringify(diffBookmarkIds.value)) }
function loadDiffBookmarks(): void { try { if (typeof window==='undefined') return; const raw=window.localStorage.getItem(DIFF_BOOKMARK_STORAGE_KEY); if (!raw) return; const parsed=JSON.parse(raw); if (Array.isArray(parsed)) diffBookmarkIds.value=parsed.filter((v)=>typeof v==='string') } catch {} }

function diffExportJsonText(): string {
  if (!comparisonResult.value) return ''
  return JSON.stringify(annotatedDiffExportJsonText(), null, 2)
}
function filteredDiffSummaryText(): string {
  const result = comparisonResult.value
  if (!result) return ''
  const lines = [
    'Atlas Level-1 readiness metadata history diff summary (local-only)',
    `filter=${activeDiffFilter.value}`,
    `comparison_available=${result.comparison_available ? 'true' : 'false'}`,
    `changed_gates_visible=${visibleChangedGates.value.length}`,
    `added_gates_visible=${visibleAddedGates.value.length}`,
    `removed_gates_visible=${visibleRemovedGates.value.length}`,
    `summary_change_type=${diffChangeTypeSummaryText.value}`,
    `summary_source=${diffSourceSummaryText.value}`,
    `summary_before_status=${diffBeforeStatusSummaryText.value}`,
    `summary_after_status=${diffAfterStatusSummaryText.value}`,
  ]
  if (bookmarkedDiffItems.value.length) {
    lines.push('bookmarks_local_only=' + bookmarkedDiffSummaryText.value)
  }
  if (labeledDiffItems.value.length) {
    lines.push('labels_local_only=' + labeledDiffSummaryText.value)
  }
  lines.push('label_filter_local_only=' + activeDiffLabelFilter.value)
  lines.push('label_filter_summary=' + labelFilterSummaryText.value)
  if (diffAnnotationText.value.trim()) {
    lines.push('annotation_local_only=' + diffAnnotationText.value.trim())
  }
  return lines.join('\n')
}


function labelFilteredDiffItemsForExport(): Array<Record<string, unknown>> {
  return visibleDiffItemsForLabelFilter.value.map((item) => ({
    ...item,
    local_label: diffLabelMap.value[item.id] || null,
    local_bookmarked: diffBookmarkIds.value.includes(item.id),
  }))
}

function annotatedDiffExportJsonText(): Record<string, unknown> {
  const result = comparisonResult.value
  return {
    ...(result || {}),
    local_diff_annotation: diffAnnotationText.value.trim() || null,
    local_diff_annotation_local_only: true,
    local_diff_bookmarks: bookmarkedDiffItems.value,
    local_diff_bookmarks_local_only: true,
    local_diff_labels: labeledDiffItems.value,
    local_diff_labels_local_only: true,
    local_diff_label_filter: activeDiffLabelFilter.value,
    local_diff_label_filter_local_only: true,
    local_diff_label_filter_summary: labelFilterSummaryText.value,
    local_diff_label_filtered_items: labelFilteredDiffItemsForExport(),
    local_diff_label_filtered_items_local_only: true,
  }
}



function labelFilteredDiffSummaryText(): string {
  const lines = [
    'Atlas Level-1 readiness metadata history label-filtered diff summary (local-only)',
    `local_diff_label_filter=${activeDiffLabelFilter.value}`,
    'local_diff_label_filter_local_only=true',
    `local_diff_label_filter_summary=${labelFilterSummaryText.value}`,
    `local_diff_label_filtered_items_count=${labelFilteredDiffItemsForExport().length}`,
    'local_diff_label_filtered_items_local_only=true',
  ]
  if (labeledDiffItems.value.length) lines.push('labels_local_only=' + labeledDiffSummaryText.value)
  if (bookmarkedDiffItems.value.length) lines.push('bookmarks_local_only=' + bookmarkedDiffSummaryText.value)
  if (diffAnnotationText.value.trim()) lines.push('annotation_local_only=' + diffAnnotationText.value.trim())
  return lines.join('\n')
}

async function copyLabelFilteredDiffJson(): Promise<void> {
  const ok = await copyTextToClipboard(JSON.stringify(annotatedDiffExportJsonText(), null, 2))
  diffExportStatus.value = ok ? 'Copied local label-filtered diff JSON to clipboard.' : 'Clipboard unavailable for local label-filtered diff JSON copy.'
}

function downloadLabelFilteredDiffJson(): void {
  const ok = downloadLocalTextFile(JSON.stringify(annotatedDiffExportJsonText(), null, 2), 'atlas-level1-readiness-diff-label-filtered.json', 'application/json')
  diffExportStatus.value = ok ? 'Exported local label-filtered diff JSON file.' : 'Local label-filtered diff JSON export unavailable.'
}

async function copyLabelFilteredDiffSummary(): Promise<void> {
  const ok = await copyTextToClipboard(labelFilteredDiffSummaryText())
  diffExportStatus.value = ok ? 'Copied local label-filtered diff summary to clipboard.' : 'Clipboard unavailable for local label-filtered diff summary copy.'
}

function downloadLabelFilteredDiffSummary(): void {
  const ok = downloadLocalTextFile(labelFilteredDiffSummaryText(), 'atlas-level1-readiness-diff-label-filtered-summary.txt', 'text/plain;charset=utf-8')
  diffExportStatus.value = ok ? 'Exported local label-filtered diff summary file.' : 'Local label-filtered diff summary export unavailable.'
}

function saveDiffAnnotationDraft(): void {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(DIFF_ANNOTATION_STORAGE_KEY, diffAnnotationText.value)
  }
  diffAnnotationStatus.value = diffAnnotationText.value.trim() ? 'Saved local annotation draft.' : 'Saved empty local annotation draft.'
}

function clearDiffAnnotation(): void {
  diffAnnotationText.value = ''
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(DIFF_ANNOTATION_STORAGE_KEY)
  }
  diffAnnotationStatus.value = 'Cleared local annotation draft.'
}

function downloadLocalTextFile(payload: string, filename: string, mimeType: string): boolean {
  if (!payload || typeof window === 'undefined' || typeof document === 'undefined') return false
  const blob = new Blob([payload], { type: mimeType })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
  return true
}

async function copyDiffJson(): Promise<void> {
  const payload = diffExportJsonText()
  const ok = await copyTextToClipboard(payload)
  diffExportStatus.value = ok ? 'Copied local diff JSON to clipboard.' : 'Clipboard unavailable for local diff JSON copy.'
}

function downloadDiffJson(): void {
  const ok = downloadLocalTextFile(diffExportJsonText(), 'atlas-level1-readiness-diff.json', 'application/json')
  diffExportStatus.value = ok ? 'Exported local diff JSON file.' : 'Local diff JSON export unavailable.'
}

async function copyFilteredDiffSummary(): Promise<void> {
  const ok = await copyTextToClipboard(filteredDiffSummaryText())
  diffExportStatus.value = ok ? 'Copied filtered local diff summary to clipboard.' : 'Clipboard unavailable for filtered diff summary copy.'
}

function downloadFilteredDiffSummary(): void {
  const ok = downloadLocalTextFile(filteredDiffSummaryText(), 'atlas-level1-readiness-diff-summary.txt', 'text/plain;charset=utf-8')
  diffExportStatus.value = ok ? 'Exported filtered local diff summary file.' : 'Filtered diff summary export unavailable.'
}

function saveCurrentAsBaseline(): void {
  if (!diagnostics.value) return
  baselineSnapshot.value = JSON.parse(JSON.stringify(diagnostics.value))
  comparisonStatus.value = 'Saved current diagnostics as local baseline snapshot.'
}

function parsePastedBaseline(): AtlasLevel1ReadinessDiagnostics {
  const parsed = JSON.parse(pastedSnapshotJson.value) as AtlasLevel1ReadinessDiagnostics
  if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.gate_source_map)) throw new Error('Invalid readiness metadata JSON for local comparison.')
  return parsed
}

function compareSnapshots(before: AtlasLevel1ReadinessDiagnostics, after: AtlasLevel1ReadinessDiagnostics): SnapshotComparisonResult {
  const beforeMap = new Map<string, AtlasLevel1ReadinessGateSource>(before.gate_source_map.map((g) => [g.gate_id, g]))
  const afterGateIds = new Set(after.gate_source_map.map((g) => g.gate_id))
  const beforeGateIds = new Set(before.gate_source_map.map((g) => g.gate_id))
  const changed_gates = after.gate_source_map
    .map((gate) => {
      const prior = beforeMap.get(gate.gate_id)
      if (!prior) return null
      const changed = prior.current_status !== gate.current_status || prior.evidence_available !== gate.evidence_available || (prior.blocker_reason || '') !== (gate.blocker_reason || '')
      return changed ? { gate_id: gate.gate_id, before_status: prior.current_status, after_status: gate.current_status, before_evidence_available: prior.evidence_available, after_evidence_available: gate.evidence_available, before_blocker_reason: prior.blocker_reason || '', after_blocker_reason: gate.blocker_reason || '' } : null
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)

  const added_gates = [...afterGateIds].filter((gateId) => !beforeGateIds.has(gateId))
  const removed_gates = [...beforeGateIds].filter((gateId) => !afterGateIds.has(gateId))
  const sourceKeys = new Set<string>([...before.gate_source_map.map((g) => g.source || 'unknown'), ...after.gate_source_map.map((g) => g.source || 'unknown')])
  const missingEvidenceCountBySource = (snapshot: AtlasLevel1ReadinessDiagnostics, source: string): number => snapshot.gate_source_map.filter((g) => (g.source || 'unknown') === source && !g.evidence_available).length
  const evidence_summary_delta_by_source = [...sourceKeys].sort().map((source) => {
    const before_missing_evidence_count = missingEvidenceCountBySource(before, source)
    const after_missing_evidence_count = missingEvidenceCountBySource(after, source)
    return { source, before_missing_evidence_count, after_missing_evidence_count, delta_missing_evidence_count: after_missing_evidence_count - before_missing_evidence_count }
  })

  return {
    summary_delta: {
      required_gate_count: (after.required_gate_count ?? 0) - (before.required_gate_count ?? 0),
      missing_evidence_count: (after.missing_evidence_count ?? 0) - (before.missing_evidence_count ?? 0),
      satisfied_gate_count: (after.satisfied_gate_count ?? 0) - (before.satisfied_gate_count ?? 0),
      unsatisfied_gate_count: (after.unsatisfied_gate_count ?? 0) - (before.unsatisfied_gate_count ?? 0)
    },
    changed_gates,
    disabled_status_delta: {
      enabled_changed: before.enabled !== after.enabled,
      level1_execution_changed: before.level1_execution_enabled !== after.level1_execution_enabled,
      callable_execution_endpoint_changed: before.callable_execution_endpoint_enabled !== after.callable_execution_endpoint_enabled,
      vue_execution_controls_changed: before.vue_execution_controls_enabled !== after.vue_execution_controls_enabled,
      runtime_level_changed: before.runtime_level !== after.runtime_level
    },
    evidence_summary_delta_by_source,
    added_gates,
    removed_gates,
    comparison_available: true,
    comparison_error: null
  }
}


async function copyTextToClipboard(text: string): Promise<boolean> {
  if (!text || typeof navigator === 'undefined' || !navigator.clipboard?.writeText) return false
  try { await navigator.clipboard.writeText(text); return true } catch { return false }
}

function diagnosticsJsonText(): string { return diagnostics.value ? JSON.stringify(diagnostics.value, null, 2) : '' }
function visibleGateSummaryText(): string { return (diagnostics.value?.gate_source_map ?? []).map((g) => `${g.gate_id} | ${g.current_status}`).join('\n') }
async function copyReadinessJson(): Promise<void> { await copyTextToClipboard(diagnosticsJsonText()) }
function downloadReadinessJson(): void { const payload = diagnosticsJsonText(); if (!payload || typeof window === 'undefined' || typeof document === 'undefined') return; const blob = new Blob([payload], { type: 'application/json' }); const url = window.URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'atlas-level1-readiness.json'; document.body.appendChild(link); link.click(); document.body.removeChild(link); window.URL.revokeObjectURL(url) }
async function copyVisibleGateSummary(): Promise<void> { await copyTextToClipboard(visibleGateSummaryText()) }

function useSavedBaseline(): void {
  if (!baselineSnapshot.value || !diagnostics.value) return
  comparisonResult.value = compareSnapshots(baselineSnapshot.value, diagnostics.value)
  comparisonStatus.value = 'Compared local saved baseline against current diagnostics.'
}

function usePastedBaseline(): void {
  if (!diagnostics.value) return
  try {
    const parsed = parsePastedBaseline()
    comparisonResult.value = compareSnapshots(parsed, diagnostics.value)
    comparisonStatus.value = 'Compared local pasted baseline against current diagnostics.'
  } catch (error) {
    comparisonResult.value = {
      summary_delta: null,
      disabled_status_delta: { enabled_changed: false, level1_execution_changed: false, callable_execution_endpoint_changed: false, vue_execution_controls_changed: false, runtime_level_changed: false },
      evidence_summary_delta_by_source: [],
      changed_gates: [],
      added_gates: [],
      removed_gates: [],
      comparison_available: false,
      comparison_error: error instanceof Error ? error.message : 'Unable to parse pasted JSON.'
    }
    comparisonStatus.value = 'Local comparison failed due to pasted JSON validation error.'
  }
}

function clearComparison(): void {
  comparisonResult.value = null
  pastedSnapshotJson.value = ''
  comparisonStatus.value = 'Local metadata comparison cleared.'
}



type LocalHistoryEntry = {
  id: string
  saved_at: string
  label: string
  diagnostics: AtlasLevel1ReadinessDiagnostics
}

const HISTORY_STORAGE_KEY = 'atlas.level1.readiness.history'
const HISTORY_MAX_ENTRIES = 5
const historyEntries = ref<LocalHistoryEntry[]>([])
const selectedHistoryId = ref('')
const historyDiffBaselineId = ref('')
const historyDiffTargetId = ref('')
const historyDiffStatus = ref('Local history diff idle.')
const canCompareHistoryEntries = computed(() => !!historyDiffBaselineId.value && !!historyDiffTargetId.value && historyDiffBaselineId.value !== historyDiffTargetId.value)
const canCompareCurrentToHistory = computed(() => hasDiagnostics.value && !!historyDiffBaselineId.value)
const historyStatus = ref('Local history idle.')
const historyImportJson = ref('')
const historyImportStatus = ref('Local import/export idle.')
const hasHistoryImportJson = computed(() => historyImportJson.value.trim().length > 0)

function storageAvailable(): boolean {
  try { return typeof window !== 'undefined' && !!window.localStorage } catch { return false }
}

function loadHistory(): void {
  if (!storageAvailable()) { historyStatus.value = 'Local browser storage unavailable.'; historyEntries.value = []; return }
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY)
    if (!raw) { historyEntries.value = []; return }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) throw new Error('invalid history payload')
    historyEntries.value = parsed.filter((e) => e && typeof e.id === 'string' && typeof e.saved_at === 'string' && typeof e.label === 'string' && e.diagnostics && Array.isArray(e.diagnostics.gate_source_map)).slice(0, HISTORY_MAX_ENTRIES)
  } catch {
    historyEntries.value = []
    historyStatus.value = 'Local history parse error; history reset in memory.'
  }
}

function persistHistory(entries: LocalHistoryEntry[]): boolean {
  if (!storageAvailable()) { historyStatus.value = 'Local browser storage unavailable.'; return false }
  try {
    window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries.slice(0, HISTORY_MAX_ENTRIES)))
    return true
  } catch {
    historyStatus.value = 'Unable to save local history (storage quota or storage error).';
    return false
  }
}

function saveCurrentToHistory(): void {
  if (!diagnostics.value) return
  const now = new Date().toISOString()
  const entry: LocalHistoryEntry = { id: `${Date.now()}`, saved_at: now, label: `Snapshot ${new Date().toLocaleString()}`, diagnostics: JSON.parse(JSON.stringify(diagnostics.value)) }
  const updated = [entry, ...historyEntries.value].slice(0, HISTORY_MAX_ENTRIES)
  if (persistHistory(updated)) { historyEntries.value = updated; historyStatus.value = 'Saved current diagnostics to local history.'; selectedHistoryId.value = entry.id }
}

function useHistoryBaseline(): void {
  if (!diagnostics.value || !selectedHistoryId.value) return
  const found = historyEntries.value.find((e) => e.id === selectedHistoryId.value)
  if (!found) { historyStatus.value = 'Selected local history snapshot not found.'; return }
  comparisonResult.value = compareSnapshots(found.diagnostics, diagnostics.value)
  comparisonStatus.value = 'Compared selected local history baseline against current diagnostics.'
}


function compareSelectedHistoryEntries(): void {
  const baseline = historyEntries.value.find((e) => e.id === historyDiffBaselineId.value)
  const target = historyEntries.value.find((e) => e.id === historyDiffTargetId.value)
  if (!baseline || !target) { historyDiffStatus.value = 'Select valid local baseline and target snapshots.'; return }
  comparisonResult.value = compareSnapshots(baseline.diagnostics, target.diagnostics)
  comparisonStatus.value = 'Compared selected local history snapshots.'
  historyDiffStatus.value = 'History snapshot diff displayed (local-only).'
}

function compareCurrentToHistoryEntry(): void {
  if (!diagnostics.value) { historyDiffStatus.value = 'Current diagnostics unavailable for local comparison.'; return }
  const baseline = historyEntries.value.find((e) => e.id === historyDiffBaselineId.value)
  if (!baseline) { historyDiffStatus.value = 'Select a valid local baseline snapshot.'; return }
  comparisonResult.value = compareSnapshots(baseline.diagnostics, diagnostics.value)
  comparisonStatus.value = 'Compared selected local baseline against current diagnostics.'
  historyDiffStatus.value = 'Current vs local baseline diff displayed (local-only).'
}

function clearHistoryDiffSelection(): void {
  historyDiffBaselineId.value = ''
  historyDiffTargetId.value = ''
  historyDiffStatus.value = 'Cleared local history diff selection.'
}

function deleteHistoryEntry(id: string): void {
  const updated = historyEntries.value.filter((e) => e.id !== id)
  if (persistHistory(updated)) { historyEntries.value = updated; if (selectedHistoryId.value === id) selectedHistoryId.value=''; if (historyDiffBaselineId.value===id) historyDiffBaselineId.value=''; if (historyDiffTargetId.value===id) historyDiffTargetId.value=''; historyStatus.value = 'Deleted one local history snapshot.' }
}



function historyJsonText(): string { return JSON.stringify(historyEntries.value, null, 2) }
async function copyHistoryJson(): Promise<void> {
  const ok = await copyTextToClipboard(historyJsonText())
  historyImportStatus.value = ok ? 'Copied local history JSON to clipboard.' : 'Clipboard unavailable for local history copy.'
}
function downloadHistoryJson(): void {
  const payload = historyJsonText()
  if (!payload || typeof window === 'undefined' || typeof document === 'undefined') return
  const blob = new Blob([payload], { type: 'application/json' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'atlas-level1-readiness-history.json'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
  historyImportStatus.value = 'Exported local history JSON file.'
}
function clearHistoryImportText(): void { historyImportJson.value = ''; historyImportStatus.value = 'Cleared local history import text.' }

function isValidHistoryEntry(value: unknown): value is LocalHistoryEntry {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  const diagnostics = item.diagnostics as Record<string, unknown> | undefined
  return typeof item.id === 'string' && typeof item.saved_at === 'string' && typeof item.label === 'string' && !!diagnostics && typeof diagnostics === 'object' && Array.isArray(diagnostics.gate_source_map)
}

function parseHistoryImportPayload(raw: string): LocalHistoryEntry[] {
  const parsed = JSON.parse(raw) as unknown
  const entries: unknown[] | null = Array.isArray(parsed) ? parsed : (parsed && typeof parsed === 'object' && Array.isArray((parsed as Record<string, unknown>).history) ? ((parsed as Record<string, unknown>).history as unknown[]) : null)
  if (!entries) throw new Error('Import JSON must be an array or an object with a history array.')
  return entries.filter(isValidHistoryEntry).map((entry) => JSON.parse(JSON.stringify(entry)) as LocalHistoryEntry).slice(0, HISTORY_MAX_ENTRIES)
}

function mergeHistoryEntries(imported: LocalHistoryEntry[]): LocalHistoryEntry[] {
  const byId = new Map<string, LocalHistoryEntry>()
  ;[...imported, ...historyEntries.value].forEach((entry) => { if (!byId.has(entry.id)) byId.set(entry.id, entry) })
  return [...byId.values()].sort((a, b) => b.saved_at.localeCompare(a.saved_at)).slice(0, HISTORY_MAX_ENTRIES)
}

function importHistoryMerge(): void {
  try {
    const imported = parseHistoryImportPayload(historyImportJson.value)
    const merged = mergeHistoryEntries(imported)
    if (persistHistory(merged)) { historyEntries.value = merged; historyImportStatus.value = `Merged ${imported.length} valid local history entries.` }
  } catch (error) { historyImportStatus.value = error instanceof Error ? error.message : 'Failed to merge local history import.' }
}

function importHistoryReplace(): void {
  try {
    const imported = parseHistoryImportPayload(historyImportJson.value)
    if (persistHistory(imported)) { historyEntries.value = imported; selectedHistoryId.value = ''; historyImportStatus.value = `Replaced local history with ${imported.length} valid entries.` }
  } catch (error) { historyImportStatus.value = error instanceof Error ? error.message : 'Failed to replace local history import.' }
}

function loadHistoryImportFile(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    historyImportJson.value = typeof reader.result === 'string' ? reader.result : ''
    historyImportStatus.value = 'Loaded local history JSON file into import text area.'
  }
  reader.onerror = () => { historyImportStatus.value = 'Unable to read local history file.' }
  reader.readAsText(file)
}

function clearHistory(): void {
  if (!storageAvailable()) { historyStatus.value = 'Local browser storage unavailable.'; return }
  try { window.localStorage.removeItem(HISTORY_STORAGE_KEY); historyEntries.value=[]; selectedHistoryId.value=''; historyDiffBaselineId.value=''; historyDiffTargetId.value=''; historyStatus.value='Cleared local history.' }
  catch { historyStatus.value='Unable to clear local history due to storage error.' }
}

onMounted(async () => { loadHistory(); loadDiffBookmarks(); diagnostics.value = await fetchLevel1ReadinessDiagnostics() })
</script>

<style scoped>
.gate-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.gate-table th, .gate-table td { border: 1px solid #e2e8f0; padding: 4px; text-align: left; vertical-align: top; }
.filter-btn { border: 1px solid #cbd5e1; background: #f8fafc; border-radius: 6px; padding: 4px 8px; font-size: 12px; cursor: pointer; }
.advisory-note { font-size: 12px; color: #334155; }
.metadata-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0; }
.metadata-status { font-size: 12px; color: #334155; }
.metadata-input { width: 100%; margin-bottom: 8px; }
.comparison-box { margin-top: 8px; border: 1px solid #e2e8f0; padding: 8px; }
</style>
