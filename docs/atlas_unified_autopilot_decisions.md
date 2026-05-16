# Atlas Unified Autopilot Architecture Decision Records

## ADR-001: Task独立機能を廃止し、PlanItemとして扱う。

### Status

Accepted.

### Context

Atlas needs small executable work units, but exposing Task as an independent user-facing feature would duplicate planning, execution, approval, and storage concepts.

### Decision

Task will be deprecated as an independent feature direction and treated as PlanItem inside an Atlas Plan / Plan Pool.

### Consequences

- Future work should add `AtlasPlanItem` instead of a standalone Task product surface.
- Task / Agent API expansion is avoided.
- Planner and Autopilot can share a single Plan Pool vocabulary.

## ADR-002: Agent独立機能を廃止し、Autopilotとして扱う。

### Status

Accepted.

### Context

Atlas needs autonomous execution behavior, but a separate Agent feature would introduce another runner concept and confuse ownership with Autopilot.

### Decision

Agent will be deprecated as an independent feature direction and treated as Atlas Autopilot itself.

### Consequences

- No new Agent Runner should be created.
- Autonomous execution belongs to the Autopilot Pipeline Runner.
- User-facing controls should remain under Atlas.

## ADR-003: PlannerはPlan Pool生成、AutopilotはPipeline実行に分離する。

### Status

Accepted.

### Context

Planning and execution have different responsibilities, safety requirements, and approval points. Existing planning capabilities already produce reviewed plans, while execution capabilities already support dry_run and safe_apply MVP behavior.

### Decision

Planner creates and reviews PlanItems for the Plan Pool. Autopilot consumes PlanItems from the Plan Pool and executes them through the Pipeline.

### Consequences

- Planner can focus on requirement analysis, clarification, Nexus context, planning, and review.
- Autopilot can focus on policy, approval, implementation, verification, tests, debug loops, and outcomes.
- Plan Pool becomes the boundary between planning and execution.

## ADR-004: NexusをAtlasのResearch Request基盤として使う。

### Status

Accepted.

### Context

Nexus is useful beyond Memory lookup. Atlas planning and execution need context from UI design research, technical research, intent understanding, scoring support, and log investigation.

### Decision

Nexus will be used as the Atlas Research Request and Context Pack collection foundation.

### Consequences

- Nexus should support research requests that return reusable context packs.
- Planner can consume Nexus context before creating PlanItems.
- Autopilot can consume Nexus context during implementation, verification, and debug loops.
- Empty Nexus results should be warnings, not hard failures.

## ADR-005: 新規ユーザー向け機能ではなくAtlas内部専用部品として追加する。

### Status

Accepted.

### Context

The goal is to strengthen Atlas, not to add more top-level user-facing features that fragment the product.

### Decision

Required additions will be implemented as Atlas内部専用部品.

### Consequences

- New user-facing Task or Agent features are out of scope.
- Internal services may be added when needed to support Planner, Plan Pool, Autopilot, and Nexus Research Pipeline.
- UI and API additions should appear as Atlas integration points.

## ADR-006: Task / Agent APIを増やさずAtlas APIへ統合する。

### Status

Accepted.

### Context

Separate Task / Agent APIs would create parallel concepts and increase migration cost.

### Decision

Do not add standalone Task / Agent APIs. Future endpoints should be Atlas API integrations.

### Consequences

- Atlas API is the integration surface.
- Existing clients do not need to understand standalone Task or Agent resources.
- Runtime behavior remains stable until explicit Atlas API integration PRs.

## ADR-007: 初期実行はdry_run中心とし、safe_applyはlow-riskから段階導入する。

### Status

Accepted.

### Context

Autopilot execution can modify code and run verification. The initial pipeline must preserve safety while the policy, approval, and verification gates mature.

### Decision

Initial execution is dry_run-centered. safe_apply will be introduced later only for low-risk cases and only through explicit PRs.

### Consequences

- Preview and dry_run outputs can be validated before applying changes.
- Low-risk automation has a staged path.
- Approval gates remain central to the execution model.

## ADR-008: delete / run_command は初期段階では自動実行禁止にする。

### Status

Accepted.

### Context

Deletion and arbitrary command execution are high-risk operations in an Autopilot pipeline.

### Decision

Automatic `delete` and arbitrary `run_command` behavior are forbidden during the initial phase. TestCommandRunner may later introduce allowlisted commands.

### Consequences

- Early Autopilot work avoids destructive or unbounded execution.
- TestCommandRunner must use an allowlist.
- DebugLoopRunner must include max retry limits and must not bypass command restrictions.
