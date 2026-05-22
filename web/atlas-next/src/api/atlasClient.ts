export type AtlasWorkflowSnapshot = {
  goal?: string
  projectPath?: string
  phase?: string
  status?: string
  primaryCtaLabel?: string
  primaryCtaState?: 'read_only' | 'disabled' | 'unknown'
  readinessLevel?: string
  autonomousExecutionEnabled: false
  runtimeLevel: 'level_0_manual_only' | string
  artifacts?: Record<string, boolean | undefined>
}

// TODO(PR-ATLAS-VUE-02): optionally consume backend safe GET workflow_state/available_actions endpoints.
export async function fetchAtlasWorkflowSnapshot(): Promise<AtlasWorkflowSnapshot> {
  return {
    goal: 'Atlas Next read-only supervision shell',
    projectPath: 'Backend-provided project path when safe workflow_state is available',
    phase: 'read_only_preview',
    status: 'Vue shell is not wired to execution endpoints',
    primaryCtaLabel: 'Read-only preview (not wired)',
    primaryCtaState: 'read_only',
    readinessLevel: 'Level 0 metadata-only readiness complete',
    autonomousExecutionEnabled: false,
    runtimeLevel: 'level_0_manual_only',
    artifacts: { rollup: true, dryRun: true, snapshot: true }
  }
}
