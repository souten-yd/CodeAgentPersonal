export type AtlasReadOnlyAvailableAction = {
  id: string
  label: string
  kind?: string
  readOnly: true
  enabled: false
  reason: string
}

export type AtlasReadOnlySafetyState = {
  runtimeLevel: 'level_0_manual_only' | string
  autonomousExecutionEnabled: false
  vueExecutionEnabled: false
  backendWorkflowStateAuthoritative: true
  dryRunFirstPreserved: true
  executeOneActionPreserved: true
}

export type AtlasWorkflowArtifactState = {
  snapshot?: boolean
  transaction?: boolean
  risk?: boolean
  allowlist?: boolean
  dryRun?: boolean
  rollback?: boolean
  artifactCapture?: boolean
  stop?: boolean
  loopBound?: boolean
  remoteGit?: boolean
  selfImprovement?: boolean
  rollup?: boolean
}

export type AtlasWorkflowDiagnosticsState = {
  source: 'placeholder' | 'safe_get_adapter'
  routeMounted: boolean
  routePath: '/atlas-next'
  routeDefault: false
  routeGuarded: true
  distBacked: true
  failClosed: true
  staticMountDeferred: boolean
  diagnosticsEndpoint: '/api/atlas/vue-next-preview/diagnostics'
  previewHealth: 'observable_fail_closed' | 'placeholder'
  backendContractReady: boolean
  warnings: string[]
}

export type AtlasPatchTransactionMetadata = {
  available: boolean
  transactionId?: string
  candidateCount: number
  source: string
  previewStatus: string
  riskClass: string
  rollbackReady: boolean
  warnings: string[]
  generationEnabled: false
  applyEnabled: false
  safeApplyEnabled: false
  verificationEnabled: false
  rollbackEnabled: false
  advisoryOnly: true
}

export type AtlasPracticalLoopMetadata = {
  schemaVersion: 'atlas.practical_autonomous_dev_loop.v1'
  status: string
  boundedLoop: boolean
  maxIterations: number
  currentIteration: number
  allowedActionsEnforced: true
  stopCondition: string
  changedFilesCount: number
  verificationState: string
  recoveryState: string
  draftPrState: string
  latestLoopRunId?: string
  latestRecoveryRunId?: string
  latestDraftPrArtifactId?: string
  latestLoopPoolId?: string
  latestLoopMode?: string
  latestLoopResultPath?: string
  latestLoopSourceDetail?: string
  latestLoopActionExecuted: boolean
  recoveryArtifactAvailable: boolean
  recoveryArtifactSummary: string
  draftPrArtifactAvailable: boolean
  draftPrArtifactSummary: string
  executionEnabled: false
  directMergeEnabled: false
  remoteGitPushEnabled: false
  selfApplyEnabled: false
  stableRuntimeMutationEnabled: false
  vueAuthoritative: false
  advisoryOnly: true
}

export type AtlasWorkflowSnapshot = {
  goal?: string
  projectPath?: string
  phase?: string
  status?: string
  primaryCtaLabel?: string
  primaryCtaState?: 'read_only' | 'disabled' | 'unknown'
  readinessLevel?: string
  backendAuthorityNote: string
  safety: AtlasReadOnlySafetyState
  availableActions: AtlasReadOnlyAvailableAction[]
  artifacts: AtlasWorkflowArtifactState
  diagnostics: AtlasWorkflowDiagnosticsState
  workflowMetadata: AtlasWorkflowRealDataMetadata
  guardedExecutionReview: AtlasGuardedExecutionReviewState
  patchTransaction: AtlasPatchTransactionMetadata
  practicalLoop: AtlasPracticalLoopMetadata
}

export type AtlasGuardedExecutionReviewState = {
  checkpoint: 'PR-ATLAS-SCALE-126'
  displayOnly: true
  backendAuthoritative: true
  vueAuthoritative: false
  callableExecutionRouteEnabled: false
  executionEnabled: false
  approvalActionEnabled: false
  dryRunActionEnabled: false
  executeActionEnabled: false
  applyActionEnabled: false
  verifyActionEnabled: false
  rollbackActionEnabled: false
  retryContinueActionEnabled: false
  requiresDryRun: true
  requiresApproval: true
  requiresRuntimeTransition: true
  endpointContractStatus: string
  reviewItems: Array<{ label: string; ready: boolean; source: string }>
  blockedReasons: string[]
}
export type AtlasWorkflowRealDataMetadata = {
  latestPoolId?: string
  latestRunId?: string
  latestPlanId?: string
  latestRequirementId?: string
  currentPhase?: string
  latestStatus?: string
  continuationState?: string
  recoveryState?: string
  planPoolAvailable: boolean
  activePlanAvailable: boolean
  lastReportAvailable: boolean
  lastErrorSummary?: string
  lastUpdatedAt?: string
  dataFreshness: string
  sourceDetail: string
  workflowSnapshotAvailable: boolean
}

export type AtlasBackendWorkflowStateContract = {
  schema_version?: string
  contract?: string
  source?: string
  goal?: string
  project_path?: string
  phase?: string
  status?: string
  primary_cta_label?: string
  primary_cta_state?: string
  primary_cta?: { label?: unknown; state?: unknown }
  readiness_level?: string
  runtime_level?: string
  backend_workflow_state_authoritative?: boolean
  artifacts?: AtlasWorkflowArtifactState
  available_actions?: Array<Record<string, unknown>>
  diagnostics?: {
    source?: string
    backend_contract_ready?: boolean
    warnings?: unknown
  }
  workflow_state_metadata?: Record<string, unknown>
  guarded_execution_review?: Record<string, unknown>
  patch_transaction_metadata?: Record<string, unknown>
  practical_loop_metadata?: Record<string, unknown>
}

const DEFAULT_PRACTICAL_LOOP_METADATA: AtlasPracticalLoopMetadata = {
  schemaVersion: 'atlas.practical_autonomous_dev_loop.v1',
  status: 'metadata_only',
  boundedLoop: false,
  maxIterations: 0,
  currentIteration: 0,
  allowedActionsEnforced: true,
  stopCondition: 'manual_review_or_backend_gate',
  changedFilesCount: 0,
  verificationState: 'waiting_for_backend_checks',
  recoveryState: 'unknown',
  draftPrState: 'not_prepared',
  latestLoopActionExecuted: false,
  recoveryArtifactAvailable: false,
  recoveryArtifactSummary: 'not_available',
  draftPrArtifactAvailable: false,
  draftPrArtifactSummary: 'not_available',
  executionEnabled: false,
  directMergeEnabled: false,
  remoteGitPushEnabled: false,
  selfApplyEnabled: false,
  stableRuntimeMutationEnabled: false,
  vueAuthoritative: false,
  advisoryOnly: true
}

const PLACEHOLDER_SNAPSHOT: AtlasBackendWorkflowStateContract = {
  goal: 'Atlas Next read-only supervision shell',
  project_path: 'Backend-provided project path when safe workflow_state is available',
  phase: 'read_only_preview',
  status: 'Vue shell is not wired to execution endpoints',
  primary_cta_label: 'Read-only preview (not wired)',
  primary_cta_state: 'read_only',
  readiness_level: 'Level 0 metadata-only readiness complete',
  runtime_level: 'level_0_manual_only',
  artifacts: { rollup: true, dryRun: true, snapshot: true, allowlist: true, risk: true },
  patch_transaction_metadata: { available: false, candidate_count: 0, source: 'backend_contract_metadata_only', preview_status: 'missing', risk_class: 'unknown', rollback_ready: false, warnings: [], advisory_only: true },
  practical_loop_metadata: {
    schema_version: 'atlas.practical_autonomous_dev_loop.v1',
    status: 'metadata_only',
    bounded_loop: false,
    max_iterations: 0,
    current_iteration: 0,
    changed_files_count: 0,
    verification_state: 'waiting_for_backend_checks',
    recovery_state: 'unknown',
    draft_pr_state: 'not_prepared',
    latest_loop_run_id: '',
    latest_recovery_run_id: '',
    latest_draft_pr_artifact_id: '',
    latest_loop_pool_id: '',
    latest_loop_mode: '',
    latest_loop_result_path: '',
    latest_loop_source_detail: 'placeholder',
    latest_loop_action_executed: false,
    recovery_artifact_available: false,
    recovery_artifact_summary: 'not_available',
    draft_pr_artifact_available: false,
    draft_pr_artifact_summary: 'not_available',
    advisory_only: true
  },
  available_actions: [{ id: 'inspect_workflow_state', label: 'Inspect workflow state payload', kind: 'read_only' }],
  diagnostics: {
    source: 'placeholder',
    backend_contract_ready: false,
    warnings: ['Using placeholder read-only snapshot when safe GET adapter endpoint is unavailable or invalid.']
  }
}

const DEFAULT_PATCH_TRANSACTION_METADATA: AtlasPatchTransactionMetadata = {
  available: false,
  candidateCount: 0,
  source: 'backend_contract_metadata_only',
  previewStatus: 'missing',
  riskClass: 'unknown',
  rollbackReady: false,
  warnings: [],
  generationEnabled: false,
  applyEnabled: false,
  safeApplyEnabled: false,
  verificationEnabled: false,
  rollbackEnabled: false,
  advisoryOnly: true
}

const DEFAULT_GUARDED_EXECUTION_REVIEW: AtlasGuardedExecutionReviewState = {
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
  endpointContractStatus: 'metadata_unavailable',
  reviewItems: [
    { label: 'Dry-run artifact', ready: false, source: 'backend metadata' },
    { label: 'Approval token', ready: false, source: 'backend metadata' },
    { label: 'Allowlisted single action', ready: false, source: 'backend metadata' },
    { label: 'Stop gate', ready: false, source: 'backend metadata' },
    { label: 'Rollback readiness', ready: false, source: 'backend metadata' }
  ],
  blockedReasons: ['Runtime transition PR-ATLAS-SCALE-127 is required before execution can be callable.']
}

function getReadOnlySafetyState(runtimeLevel?: string): AtlasReadOnlySafetyState {
  return {
    runtimeLevel: runtimeLevel || 'level_0_manual_only',
    autonomousExecutionEnabled: false,
    vueExecutionEnabled: false,
    backendWorkflowStateAuthoritative: true,
    dryRunFirstPreserved: true,
    executeOneActionPreserved: true
  }
}

function toReadOnlyAvailableActions(value: unknown): AtlasReadOnlyAvailableAction[] {
  if (!Array.isArray(value)) return []
  return value.map((raw, index) => {
    const item = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {}
    const id = String(item.id ?? item.action_id ?? `action_${index + 1}`)
    const label = String(item.label ?? item.title ?? id)
    const kind = item.kind ? String(item.kind) : undefined
    return { id, label, kind, readOnly: true, enabled: false, reason: 'Read-only metadata only. Execution remains disabled in Vue Next.' }
  })
}

function fallbackWorkflowStateContract(): AtlasBackendWorkflowStateContract {
  return PLACEHOLDER_SNAPSHOT
}

function isValidWorkflowStateContract(payload: AtlasBackendWorkflowStateContract): boolean {
  return payload.schema_version === 'atlas.workflow_state.v1' && payload.contract === 'read_only_workflow_state'
}

async function fetchReadOnlyWorkflowState(): Promise<AtlasBackendWorkflowStateContract> {
  try {
    const response = await fetch('/api/atlas/workflow-state/read-only', { method: 'GET' })
    if (!response.ok) return fallbackWorkflowStateContract()
    const payload = (await response.json()) as AtlasBackendWorkflowStateContract
    if (!isValidWorkflowStateContract(payload)) return fallbackWorkflowStateContract()
    return payload
  } catch {
    return fallbackWorkflowStateContract()
  }
}

function optionalText(raw: unknown, fallback: string): string {
  return typeof raw === 'string' && raw.trim() ? raw : fallback
}

function optionalTextValue(raw: unknown): string | undefined {
  return typeof raw === 'string' && raw.trim() ? raw : undefined
}

function nonNegativeNumber(raw: unknown): number {
  return typeof raw === 'number' && Number.isFinite(raw) ? Math.max(0, Math.floor(raw)) : 0
}

function normalizeWorkflowState(payload: AtlasBackendWorkflowStateContract): AtlasWorkflowSnapshot {
  const accepted = isValidWorkflowStateContract(payload)
  const runtimeLevel = typeof payload.runtime_level === 'string' ? payload.runtime_level : 'level_0_manual_only'
  const primaryCtaLabel = typeof payload.primary_cta?.label === 'string' && payload.primary_cta.label.trim()
    ? payload.primary_cta.label
    : payload.primary_cta_label
  const primaryCtaState = typeof payload.primary_cta?.state === 'string' ? payload.primary_cta.state : payload.primary_cta_state
  const diagnostics: AtlasWorkflowDiagnosticsState = {
    source: accepted ? 'safe_get_adapter' : 'placeholder',
    routeMounted: true,
    routePath: '/atlas-next',
    routeDefault: false,
    routeGuarded: true,
    distBacked: true,
    failClosed: true,
    staticMountDeferred: false,
    diagnosticsEndpoint: '/api/atlas/vue-next-preview/diagnostics',
    previewHealth: accepted ? 'observable_fail_closed' : 'placeholder',
    backendContractReady: accepted,
    warnings: Array.isArray(payload.diagnostics?.warnings)
      ? payload.diagnostics?.warnings.filter((item): item is string => typeof item === 'string')
      : []
  }

  return {
    goal: payload.goal,
    projectPath: payload.project_path,
    phase: payload.phase,
    status: payload.status,
    primaryCtaLabel,
    primaryCtaState: primaryCtaState === 'read_only' || primaryCtaState === 'disabled' ? primaryCtaState : 'unknown',
    readinessLevel: payload.readiness_level,
    backendAuthorityNote: 'Backend workflow state remains authoritative. Vue Next does not compute execution eligibility.',
    safety: getReadOnlySafetyState(runtimeLevel),
    availableActions: toReadOnlyAvailableActions(payload.available_actions),
    artifacts: payload.artifacts ?? {},
    diagnostics,
    workflowMetadata: normalizeWorkflowMetadata(payload.workflow_state_metadata),
    guardedExecutionReview: normalizeGuardedExecutionReview(payload.guarded_execution_review),
    patchTransaction: normalizePatchTransactionMetadata(payload.patch_transaction_metadata),
    practicalLoop: normalizePracticalLoopMetadata(payload.practical_loop_metadata)
  }
}

function normalizePracticalLoopMetadata(value: unknown): AtlasPracticalLoopMetadata {
  const item = typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}
  const latestLoopRunId = optionalTextValue(item.latest_loop_run_id)
  const latestRecoveryRunId = optionalTextValue(item.latest_recovery_run_id)
  const latestDraftPrArtifactId = optionalTextValue(item.latest_draft_pr_artifact_id)
  const latestLoopPoolId = optionalTextValue(item.latest_loop_pool_id)
  const latestLoopMode = optionalTextValue(item.latest_loop_mode)
  const latestLoopResultPath = optionalTextValue(item.latest_loop_result_path)
  const latestLoopSourceDetail = optionalTextValue(item.latest_loop_source_detail)
  return {
    ...DEFAULT_PRACTICAL_LOOP_METADATA,
    schemaVersion: item.schema_version === 'atlas.practical_autonomous_dev_loop.v1'
      ? 'atlas.practical_autonomous_dev_loop.v1'
      : DEFAULT_PRACTICAL_LOOP_METADATA.schemaVersion,
    status: optionalText(item.status, DEFAULT_PRACTICAL_LOOP_METADATA.status),
    boundedLoop: item.bounded_loop === true,
    maxIterations: nonNegativeNumber(item.max_iterations),
    currentIteration: nonNegativeNumber(item.current_iteration),
    allowedActionsEnforced: true,
    stopCondition: optionalText(item.stop_condition, DEFAULT_PRACTICAL_LOOP_METADATA.stopCondition),
    changedFilesCount: nonNegativeNumber(item.changed_files_count),
    verificationState: optionalText(item.verification_state, DEFAULT_PRACTICAL_LOOP_METADATA.verificationState),
    recoveryState: optionalText(item.recovery_state, DEFAULT_PRACTICAL_LOOP_METADATA.recoveryState),
    draftPrState: optionalText(item.draft_pr_state, DEFAULT_PRACTICAL_LOOP_METADATA.draftPrState),
    latestLoopRunId,
    latestRecoveryRunId,
    latestDraftPrArtifactId,
    latestLoopPoolId,
    latestLoopMode,
    latestLoopResultPath,
    latestLoopSourceDetail,
    latestLoopActionExecuted: item.latest_loop_action_executed === true,
    recoveryArtifactAvailable: item.recovery_artifact_available === true,
    recoveryArtifactSummary: optionalText(item.recovery_artifact_summary, DEFAULT_PRACTICAL_LOOP_METADATA.recoveryArtifactSummary),
    draftPrArtifactAvailable: item.draft_pr_artifact_available === true,
    draftPrArtifactSummary: optionalText(item.draft_pr_artifact_summary, DEFAULT_PRACTICAL_LOOP_METADATA.draftPrArtifactSummary),
    executionEnabled: false,
    directMergeEnabled: false,
    remoteGitPushEnabled: false,
    selfApplyEnabled: false,
    stableRuntimeMutationEnabled: false,
    vueAuthoritative: false,
    advisoryOnly: true
  }
}

function normalizePatchTransactionMetadata(value: unknown): AtlasPatchTransactionMetadata {
  const item = typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}
  const candidateCount = typeof item.candidate_count === 'number' && Number.isFinite(item.candidate_count)
    ? Math.max(0, Math.floor(item.candidate_count))
    : DEFAULT_PATCH_TRANSACTION_METADATA.candidateCount
  const transactionId = typeof item.transaction_id === 'string' && item.transaction_id.trim() ? item.transaction_id : undefined
  const source = typeof item.source === 'string' && item.source.trim() ? item.source : DEFAULT_PATCH_TRANSACTION_METADATA.source
  const previewStatus = typeof item.preview_status === 'string' && item.preview_status.trim() ? item.preview_status : DEFAULT_PATCH_TRANSACTION_METADATA.previewStatus
  const riskClass = typeof item.risk_class === 'string' && item.risk_class.trim() ? item.risk_class : DEFAULT_PATCH_TRANSACTION_METADATA.riskClass
  const warnings = Array.isArray(item.warnings)
    ? item.warnings.filter((raw): raw is string => typeof raw === 'string' && Boolean(raw.trim())).slice(0, 8)
    : []

  return {
    available: item.available === true,
    transactionId,
    candidateCount,
    source,
    previewStatus,
    riskClass,
    rollbackReady: item.rollback_ready === true,
    warnings,
    generationEnabled: false,
    applyEnabled: false,
    safeApplyEnabled: false,
    verificationEnabled: false,
    rollbackEnabled: false,
    advisoryOnly: true
  }
}

function normalizeGuardedExecutionReview(value: unknown): AtlasGuardedExecutionReviewState {
  const item = typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}
  const reviewItems = Array.isArray(item.review_items)
    ? item.review_items.map((raw, index) => {
      const row = typeof raw === 'object' && raw !== null ? raw as Record<string, unknown> : {}
      return {
        label: typeof row.label === 'string' && row.label.trim() ? row.label : `Review item ${index + 1}`,
        ready: row.ready === true,
        source: typeof row.source === 'string' && row.source.trim() ? row.source : 'backend metadata'
      }
    }).slice(0, 8)
    : DEFAULT_GUARDED_EXECUTION_REVIEW.reviewItems
  const blockedReasons = Array.isArray(item.blocked_reasons)
    ? item.blocked_reasons.filter((raw): raw is string => typeof raw === 'string' && Boolean(raw.trim())).slice(0, 6)
    : DEFAULT_GUARDED_EXECUTION_REVIEW.blockedReasons

  return {
    ...DEFAULT_GUARDED_EXECUTION_REVIEW,
    callableExecutionRouteEnabled: false,
    executionEnabled: false,
    approvalActionEnabled: false,
    dryRunActionEnabled: false,
    executeActionEnabled: false,
    applyActionEnabled: false,
    verifyActionEnabled: false,
    rollbackActionEnabled: false,
    retryContinueActionEnabled: false,
    endpointContractStatus: typeof item.endpoint_contract_status === 'string' && item.endpoint_contract_status.trim()
      ? item.endpoint_contract_status
      : DEFAULT_GUARDED_EXECUTION_REVIEW.endpointContractStatus,
    reviewItems,
    blockedReasons,
    displayOnly: true,
    backendAuthoritative: true,
    vueAuthoritative: false,
    requiresDryRun: true,
    requiresApproval: true,
    requiresRuntimeTransition: true
  }
}

function normalizeWorkflowMetadata(value: unknown): AtlasWorkflowRealDataMetadata {
  const item = typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}
  const toOptionalString = (raw: unknown): string | undefined => typeof raw === 'string' && raw.trim() ? raw : undefined
  return {
    latestPoolId: toOptionalString(item.latest_pool_id),
    latestRunId: toOptionalString(item.latest_run_id),
    latestPlanId: toOptionalString(item.latest_plan_id),
    latestRequirementId: toOptionalString(item.latest_requirement_id),
    currentPhase: toOptionalString(item.current_phase),
    latestStatus: toOptionalString(item.latest_status),
    continuationState: toOptionalString(item.continuation_state),
    recoveryState: toOptionalString(item.recovery_state),
    planPoolAvailable: item.plan_pool_available === true,
    activePlanAvailable: item.active_plan_available === true,
    lastReportAvailable: item.last_report_available === true,
    lastErrorSummary: toOptionalString(item.last_error_summary),
    lastUpdatedAt: toOptionalString(item.last_updated_at),
    dataFreshness: toOptionalString(item.data_freshness) ?? 'unknown',
    sourceDetail: toOptionalString(item.source_detail) ?? 'backend_contract_metadata_only',
    workflowSnapshotAvailable: item.workflow_snapshot_available === true
  }
}

export async function fetchAtlasWorkflowSnapshot(): Promise<AtlasWorkflowSnapshot> {
  const payload = await fetchReadOnlyWorkflowState()
  return normalizeWorkflowState(payload)
}

export type AtlasLevel1ReadinessGateSource = {
  gate_id: string
  label: string
  owner: string
  source: string
  evidence_required: string
  evidence_available: boolean
  current_status: string
  blocker_reason: string
  test_requirement: string
  mutable: boolean
  advisory_only: boolean
}

export type AtlasLevel1ReadinessDiagnostics = {
  enabled: false
  runtime_level: string
  level1_execution_enabled: false
  callable_execution_endpoint_enabled: false
  vue_execution_controls_enabled: false
  advisory_only: boolean
  mutation_performed: false
  execution_performed: false
  required_gate_count: number
  missing_evidence_count: number
  satisfied_gate_count: number
  unsatisfied_gate_count: number
  gate_source_map: AtlasLevel1ReadinessGateSource[]
}

export async function fetchLevel1ReadinessDiagnostics(): Promise<AtlasLevel1ReadinessDiagnostics | null> {
  try {
    const response = await fetch('/api/atlas/level1/readiness', { method: 'GET' })
    if (!response.ok) return null
    return await response.json() as AtlasLevel1ReadinessDiagnostics
  } catch {
    return null
  }
}

export type CreatePlanPoolRequest = {
  input: string
  project_path?: string
  project_name?: string
  planning_depth?: string
  workspace_id?: string
}

export type CreatePlanPoolResponse = {
  pool_id: string
  status: string
  item_count: number
  planner_status?: string
  warnings?: string[]
  errors?: string[]
  questions?: Array<Record<string, unknown>>
  requirement?: Record<string, unknown>
  plan?: Record<string, unknown>
}

export async function createPlanPool(request: CreatePlanPoolRequest): Promise<CreatePlanPoolResponse> {
  const payload = {
    input: request.input,
    project_path: request.project_path ?? '',
    project_name: request.project_name ?? 'CodeAgentPersonal',
    planning_depth: request.planning_depth ?? 'standard',
    workspace_id: request.workspace_id ?? 'default',
    automation_level: 'plan_then_ask',
    execution_strategy: 'sequential'
  }

  const response = await fetch('/api/atlas/plan-pools', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })

  if (!response.ok) {
    let detail = 'Failed to start Atlas planning.'
    try {
      const errorPayload = await response.json() as { detail?: unknown }
      if (typeof errorPayload.detail === 'string' && errorPayload.detail.trim()) {
        detail = errorPayload.detail
      }
    } catch {
      // keep safe default error message
    }
    throw new Error(detail)
  }

  return await response.json() as CreatePlanPoolResponse
}
