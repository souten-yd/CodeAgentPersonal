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
    diagnostics
  }
}

export async function fetchAtlasWorkflowSnapshot(): Promise<AtlasWorkflowSnapshot> {
  const payload = await fetchReadOnlyWorkflowState()
  return normalizeWorkflowState(payload)
}
