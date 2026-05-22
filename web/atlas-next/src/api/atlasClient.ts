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
}

// Safe GET-only backend workflow_state contract endpoint binding.
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
  available_actions: [{ id: 'inspect_workflow_state', label: 'Inspect workflow state payload', kind: 'read_only' }],
  diagnostics: {
    source: 'placeholder',
    backend_contract_ready: false,
    warnings: ['Using placeholder read-only snapshot when safe GET adapter endpoint is unavailable or invalid.']
  }
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

function normalizeWorkflowState(payload: AtlasBackendWorkflowStateContract): AtlasWorkflowSnapshot {
  const accepted = isValidWorkflowStateContract(payload)
  const runtimeLevel = typeof payload.runtime_level === 'string' ? payload.runtime_level : 'level_0_manual_only'
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
    primaryCtaLabel: payload.primary_cta_label,
    primaryCtaState: payload.primary_cta_state === 'read_only' || payload.primary_cta_state === 'disabled' ? payload.primary_cta_state : 'unknown',
    readinessLevel: payload.readiness_level,
    backendAuthorityNote: 'Backend workflow state remains authoritative. Vue Next does not compute execution eligibility.',
    safety: getReadOnlySafetyState(runtimeLevel),
    availableActions: toReadOnlyAvailableActions(payload.available_actions),
    artifacts: payload.artifacts ?? {},
    diagnostics,
    workflowMetadata: normalizeWorkflowMetadata(payload.workflow_state_metadata)
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


export type CreatePlanPoolRequest = {
  input: string
  project_path?: string
  project_name?: string
  planning_depth?: string
  workspace_id?: string
  automation_level?: string
  execution_strategy?: string
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
  const payload: CreatePlanPoolRequest = {
    input: request.input,
    project_path: request.project_path ?? '',
    project_name: request.project_name ?? 'CodeAgentPersonal',
    planning_depth: request.planning_depth ?? 'standard',
    workspace_id: request.workspace_id ?? 'default',
    automation_level: request.automation_level ?? 'plan_then_ask',
    execution_strategy: request.execution_strategy ?? 'sequential'
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
