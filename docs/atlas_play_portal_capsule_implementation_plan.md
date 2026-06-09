# Atlas Play / Capsule / Portal Implementation Plan

> Canonical ordered plan. Implement one PR work package at a time.
> Baseline: `8d6897fe366a3877808f040a8828729350b89b7e`.

## Architecture rule

Boundary interfaces and schemas are implemented before runtime features. UI and Portal may depend only on public contracts, never on another layer's private storage or process objects.

Suggested module ownership:

```text
app/atlas/play/       shared Play domain and runtime
app/atlas/capsule/    packaging domain
app/portal/           Portal catalog, package and data domain
app/api/              thin HTTP/WebSocket adapters
web/js/               thin UI projections
web/css/              responsive presentation
tests/                contract, security, integration and E2E tests
```

Exact file names may be adjusted to existing conventions, but the public boundaries and PR ordering below are fixed.

## PR-PPC-0 — Baseline, contracts and threat model

### Purpose

Create versioned schemas, filesystem layout helpers, state machines and failing/contract fixtures before any process execution.

### Add

- Play request, target, launch profile, environment, session view and lifecycle-event models.
- Capsule manifest, package record and build request models.
- Portal installation, run, data policy, commit and snapshot models.
- Canonical state transition reducers with no filesystem or process side effects.
- Central path layout for Atlas project work, Portal packages, quarantine, sessions, recovery and data.
- Threat model and resource-limit defaults.
- Router registration placeholders that expose no execution capability.

### Contracts

- Schema version required on persisted and imported objects.
- Unknown launch kinds fail closed.
- Persistence entities and API views are separate.
- State transitions reject invalid backwards or terminal transitions.
- No free-form shell command field in package manifest.

### Tests

- model round trips and migration/default behavior
- state transition matrix
- path layout containment
- unknown schema/launch kind rejection
- router import and no-side-effect startup

### Likely files

- `app/atlas/play/contracts.py`
- `app/atlas/play/state.py`
- `app/atlas/play/paths.py`
- `app/atlas/capsule/contracts.py`
- `app/portal/contracts.py`
- `app/portal/paths.py`
- `app/api/atlas_play.py`
- `app/api/portal.py`
- `app/server.py`
- focused tests

## PR-PPC-1 — Shared workspace access policy and safe file service

### Purpose

Create one canonical read/write/execute/serve decision boundary usable by Play, Capsule and Portal staging.

### Implement

- structural containment after path normalization
- link/junction escape checks
- independent read, write, execute and serve decisions
- protected dependency/runtime directories
- bounded file list/read/write APIs for Play
- optimistic hash or revision precondition on writes
- file-size, binary-file and encoding handling

### Reuse

Extract low-level safe path logic shared with `AtlasFileSafeApplyExecutor` without weakening Safe Apply semantics. Do not make Play writes bypass Atlas project roots.

### Tests

Traversal, encoded traversal, absolute paths, Windows drives, UNC paths, case handling, symlink escape, duplicate normalized paths, stale-write conflict and protected directories on supported platforms.

## PR-PPC-2 — Play target and dependency discovery

### Purpose

Resolve `/play`, the Play button and candidate selection into a deterministic `PlayTarget`.

### Implement

- Atlas-only `/play` intent classification
- same service invocation from button and command
- current editor/selected file/last target/candidate precedence
- launch candidate detection from HTML, Python and `package.json`
- static dependency discovery for HTML, JS modules, CSS and Python imports
- dependency graph persistence and missing-resource diagnostics
- multiple candidate mobile selection payload

### Tests

- Lumen does not classify or route `/play`
- button and command request equivalence
- nested and sibling dependency resolution
- unsupported or ambiguous target responses
- candidates cannot escape project root

## PR-PPC-3 — Environment resolver and structured launch adapters

### Purpose

Resolve safe runtimes without starting long-lived processes yet.

### Implement

- Python environment precedence and dependency manifest inspection
- Node/package-manager inspection
- structured adapters for static web, Python script, ASGI, WSGI, Streamlit, Django, Node script, npm, Vite and Next
- composite service DAG validation
- loopback-only port allocation contract
- bounded arguments and environment allowlist
- missing dependency outcome; no automatic host mutation

### Tests

Adapter command construction, interpreter selection, malformed package metadata, dependency cycles, disallowed arguments, inherited-environment filtering and platform-specific path behavior.

## PR-PPC-4 — Process supervisor, sessions, events and cleanup

### Purpose

Add the first real Play execution boundary.

### Implement

- Play session repository and manager
- process-group/job-object abstraction for Linux and Windows
- child-process tracking
- stdout/stderr streaming and bounded log retention
- start, restart, stop, timeout, expiry and purge
- port ownership and release
- startup orphan reconciliation
- static web and Python script execution first; enable server adapters after supervisor tests pass

### Safety

No arbitrary command endpoint. Only validated launch-adapter output reaches the supervisor. Working directory, environment, limits and session ownership are mandatory.

### Tests

Short-lived success/failure, long-lived stop, child cleanup, restart, timeout, output truncation, concurrent session limit, orphan reconciliation and port release.

## PR-PPC-5 — Preview gateway and browser/runtime evidence

### Purpose

Expose static and server applications through KasaneCore without exposing temporary ports.

### Implement

- session-bound static serving
- reverse proxy to loopback-owned session ports
- WebSocket and SSE forwarding
- path/base/location/cookie rewriting where required
- origin and host validation
- browser console and failed-request ingestion
- runtime-observed dependency evidence
- no open-proxy behavior

### Tests

Static nested assets, SPA route fallback, ASGI HTTP, WebSocket, SSE, redirect rewriting, invalid session, cross-session port access, traversal and proxy-target injection.

## PR-PPC-6 — Atlas Play mobile workspace and header controls

### Purpose

Deliver the user-visible Atlas-only Play experience.

### Implement

- header order: Capsule, Play, Plan History on the right
- responsive button labels and accessible names
- Play target chooser
- full-screen/sheet workspace with Preview, Files, Logs and Terminal tabs
- file view/edit/save through PR-PPC-1 service
- run/restart/stop/reload/external/fullscreen/close actions
- event-stream reconnect and session restoration
- Terminal initially limited to the session PTY contract; no general host shell
- Atlas repair-handoff button

### Existing integration points

- `ui.html`
- `web/js/app.js` where Plan History and project picker are injected
- `web/js/atlas_claude_panel.js` Atlas intent dispatch
- `web/css/app.css`
- UI contract and Playwright smoke tests

## PR-PPC-7 — Capsule candidate analysis and deterministic builder

### Purpose

Package a verified Play state into a distribution artifact.

### Implement

- Play-success and current-hash eligibility check
- launch-profile candidate selection, multiple profiles and default profile
- composite profile editor/validation
- include/exclude policy
- data-policy declaration
- deterministic archive ordering and normalized metadata
- checksums and content hash
- environment/private-data pattern scan with reviewable findings
- immutable package record

### Tests

Stale successful session rejection, profile validation, deterministic repeated builds, exclusions, checksum correctness, no Atlas workspace artifacts and no runtime data.

## PR-PPC-8 — Portal package repository, catalog, import and export

### Purpose

Add the Portal top-level mode and secure package lifecycle.

### Implement

- Portal navigation button and mobile projection
- catalog APIs and cards
- automatic registration after Capsule build
- quarantine import
- archive preflight and extraction simulation
- manifest/checksum validation
- package identity/version/content-hash conflict handling
- trust classification
- package-only export
- package uninstall independent from data deletion
- Fork to Atlas into a new project

### Tests

ZIP traversal, absolute/drive/UNC entries, links, duplicate normalized entries, excessive count/size/ratio, invalid manifest, checksum mismatch, version conflict, export data exclusion and fork immutability.

## PR-PPC-9 — Portal staging and shared Play runtime launch

### Purpose

Run Portal packages using the already-tested Play runtime boundary.

### Implement

- hash revalidation on every run
- safe extraction into session application root
- application read-only policy
- launch-profile selector
- Portal run request mapped to public Play request
- package trust and permission policy projection
- Portal Preview/Logs/Stop UI
- purge of extracted application and disposable content after terminal decision

### Tests

Portal never invokes process supervisor directly, tampered stored package fails, read-only package behavior, profile selection, composite service startup, stop/purge and concurrent isolation.

## PR-PPC-10 — Portal persistent data, discard and snapshots

### Purpose

Implement the requested generated-data lifecycle.

### Implement

- installation-scoped current data
- per-run writable session data
- continue, empty, snapshot and ephemeral start modes
- Save and exit using atomic replacement
- Save as snapshot without mutating source snapshot
- Discard and exit
- cache/temp purge
- data size and last-modified metadata
- Package uninstall versus data deletion controls
- separate Data Backup/Restore contract, never Package Export

### Tests

Save persistence, discard rollback, atomic failure preservation, snapshot immutability, ephemeral default discard, package export exclusion, update compatibility checkpoint and data deletion confirmation.

## PR-PPC-11 — Disconnect recovery, expiry and lifecycle hardening

### Purpose

Make mobile/network interruption safe and ensure no resources leak.

### Implement

- heartbeat and reconnect token/session ownership
- recoverable state after disconnect or server interruption
- Resume, Save and Discard recovery actions
- bounded recovery retention and expiry purge
- startup reconciliation for processes, ports, staging roots and incomplete commits
- idempotent stop/commit/discard/purge
- audit lifecycle events and minimal diagnostics

### Tests

Browser disconnect, duplicate requests, server restart, crash between data staging and commit, expired recovery, interrupted extraction, stale process metadata and repeated cleanup.

## PR-PPC-12 — Acceptance, security, mobile E2E and documentation reconciliation

### Purpose

Prove the complete product rather than only unit components.

### Required scenarios

1. Atlas `/play` static HTML with nested JS/CSS/assets.
2. Atlas Play Python script output and failure handoff.
3. ASGI preview through proxy including WebSocket or SSE.
4. Mobile file edit, save and restart within allowed root.
5. Unsafe path and link rejection.
6. Successful Play to multi-profile Capsule.
7. Capsule automatic Portal registration and package export.
8. External package import quarantine acceptance/rejection matrix.
9. Portal run, generated-data Save, next-run continuity.
10. Snapshot start and Discard.
11. Ephemeral run and disconnect recovery expiry.
12. Fork to Atlas and package immutability.
13. Stop/failure/restart leave no child process, port or staging directory.

### Final verification

- focused suites for every package
- all affected Atlas project/UI/API tests
- security archive/path suite
- process cleanup integration suite on supported CI platforms
- iPhone-size Playwright flow
- Python compile checks and JavaScript syntax checks
- update current status with exact command evidence

## Per-package completion rule

A package is complete only when implementation, focused tests, syntax checks, affected tests, status update and remaining-gap note are committed. Do not combine later packages merely to reduce PR count. Do not mark unavailable platform tests as passed; record the limitation and provide the strongest available contract test.
