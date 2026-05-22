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

export type AtlasWorkflowSnapshot = {
  goal?: string
  projectPath?: string
  phase?: string
  status?: string
  primaryCtaLabel?: string
  primaryCtaState?: 'read_only' | 'disabled' | 'unknown'
  readinessLevel?: string
  safety: AtlasReadOnlySafetyState
  availableActions: AtlasReadOnlyAvailableAction[]
  artifacts?: Record<string, boolean | undefined>
}

type AtlasWorkflowStateResponse = {
  goal?: string
  project_path?: string
  phase?: string
  status?: string
  primary_cta_label?: string
  primary_cta_state?: string
  readiness_level?: string
  runtime_level?: string
  artifacts?: Record<string, boolean | undefined>
  available_actions?: Array<Record<string, unknown>>
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
    const item = typeof raw === 'object' && raw !== null ? raw as Record<string, unknown> : {}
    const id = String(item.id ?? item.action_id ?? `action_${index + 1}`)
    const label = String(item.label ?? item.title ?? id)
    const kind = item.kind ? String(item.kind) : undefined
    return { id, label, kind, readOnly: true, enabled: false, reason: 'Read-only metadata only. Execution remains disabled in Vue Next.' }
  })
}

function normalizeWorkflowState(payload: AtlasWorkflowStateResponse): AtlasWorkflowSnapshot {
  const runtimeLevel = typeof payload.runtime_level === 'string' ? payload.runtime_level : 'level_0_manual_only'
  const availableActions = toReadOnlyAvailableActions(payload.available_actions)
  return {
    goal: payload.goal,
    projectPath: payload.project_path,
    phase: payload.phase,
    status: payload.status,
    primaryCtaLabel: payload.primary_cta_label,
    primaryCtaState: payload.primary_cta_state === 'read_only' || payload.primary_cta_state === 'disabled' ? payload.primary_cta_state : 'unknown',
    readinessLevel: payload.readiness_level,
    safety: getReadOnlySafetyState(runtimeLevel),
    availableActions,
    artifacts: payload.artifacts
  }
}

export async function fetchAtlasWorkflowSnapshot(): Promise<AtlasWorkflowSnapshot> {
  // TODO(PR-ATLAS-VUE-03): Bind to a dedicated backend workflow_state contract endpoint when available.
  return normalizeWorkflowState({
    goal: 'Atlas Next read-only supervision shell',
    project_path: 'Backend-provided project path when safe workflow_state is available',
    phase: 'read_only_preview',
    status: 'Vue shell is not wired to execution endpoints',
    primary_cta_label: 'Read-only preview (not wired)',
    primary_cta_state: 'read_only',
    readiness_level: 'Level 0 metadata-only readiness complete',
    runtime_level: 'level_0_manual_only',
    artifacts: { rollup: true, dryRun: true, snapshot: true },
    available_actions: []
  })
}
