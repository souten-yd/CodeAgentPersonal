# Atlas Development Constitution

目的:
Atlas開発で絶対に守るべき上位ルール。
個別PR指示と矛盾した場合、このConstitutionを優先する。

## 1. Authority

- This constitution applies to all Atlas development PRs.
- It applies to human developers, Codex tasks, ChatGPT-assisted development, and future Atlas self-development.
- If a PR instruction conflicts with this constitution, the PR must stop and report the conflict.

## 2. Non-negotiable Safety Rules

Never:
- shell=True
- remote git
- git push
- git pull
- git clone
- execute all
- auto continue
- automatic safe_apply
- automatic verification
- automatic retry
- automatic patch generation
- automatic test execution
- unapproved rollback/restore
- Path("ca_data") direct writes
- storing confirmation tokens in artifacts/localStorage
- type="module" for existing classic Atlas UI scripts
- import/export in classic Atlas UI scripts

Always:
- inspect actual main branch files
- verify latest merged PR on GitHub
- do not trust PR body alone
- verify runtime wiring
- verify helper existence
- verify UI bindings
- verify API registration
- verify tests are meaningful, not placeholder-only
- use resolve_atlas_ca_data_root(request) for API data root
- inject data_root into services
- keep missing Repo Index non-blocking
- update checkpoint docs after every PR
- preserve human approval for execution

## 3. Root/Data Rules

- All Atlas persistence must use resolved data_root.
- API code must use resolve_atlas_ca_data_root(request).
- Services must receive data_root via constructor.
- Path("ca_data") is allowed only in the centralized root helper fallback, not in feature services.

## 4. UI/JS Rules

- Existing Atlas UI scripts are classic scripts.
- Do not use type="module".
- Do not add top-level import/export.
- If JS/UI changes, update cache bust.
- If a UI button is added, verify:
  - DOM ID exists
  - API helper exists
  - dashboard binding exists
  - endpoint exists
  - tests read actual main files


## Contract Test Quality Rule

- Tests must not only assert that strings exist.
- For every new feature, tests must prove the runtime chain that must work.
- A PR is incomplete if a broken implementation could still pass all tests.
- Every new UI/API feature must define the broken cases its tests catch.
- Every future Atlas PR must include an adversarial self-review.

For UI changes, tests must verify the full chain:

DOM ID
→ AtlasPipelineAPI helper
→ dashboard function
→ event binding inside bind/init
→ endpoint string
→ response unwrap
→ render target update
→ cache bust

For classic Atlas UI scripts:
- New bindings must be inside the existing IIFE / initialized path.
- New bindings must not be appended after the final `})();`.
- No top-level code after the IIFE may reference IIFE-local variables such as `$`, `state`, `arr`, or helper functions.
- `type="module"` remains forbidden for existing Atlas UI scripts.
- top-level `import` / `export` remains forbidden.

For API/backend changes, tests must verify:
- router registered
- endpoint reachable
- request-aware `resolve_atlas_ca_data_root(request)` used
- service receives `data_root`
- missing resources are non-blocking when required
- response shape is tested
- safety metadata flags are asserted when relevant
- no forbidden execution path is introduced

### Definition of Done

A reviewer should be able to intentionally break one obvious part of the new feature and see at least one test fail.
If no test would fail for a broken binding, missing endpoint, wrong response shape, wrong data_root, or misplaced UI code, the PR is incomplete.

## 5. Execution Rules

- Recommendations are not executions.
- Suggested commands must never be run automatically.
- Verification hints are advisory only unless a future explicitly approved PR changes policy.
- Guarded Operator Loop remains one confirmed action at a time.
- Follow-up action after refresh must never be executed automatically.

## 6. Documentation Rules

Every PR must update:
- Current PR
- Next PR
- Completed PRs where applicable
- Known Current Code Facts
- Safety notes

## 7. Stop Conditions

PR must stop and report if:
- helper expected by UI does not exist
- API endpoint is not registered
- runtime function is undefined
- tests assert behavior not present in main files
- PR requires forbidden execution behavior
- data_root cannot be resolved safely
- rollback/snapshot safety is missing for autonomous execution work
