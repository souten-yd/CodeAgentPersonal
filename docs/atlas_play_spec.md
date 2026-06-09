# Atlas Play Specification

## Scope

`/play` is an Atlas-only command. Lumen must not parse or route it. The Play button and `/play` command call the same service.

Atlas header order:

```text
[Project]                         [Capsule] [Play] [Plan History]
```

## Target resolution

A selected file is the entrypoint, while the selected Atlas project's `work` directory is the execution root. Resolution order for button or bare `/play`:

1. file open in Atlas editor
2. selected file
3. last Play target
4. detected candidates
5. mobile selection sheet

Related files inside the allowed project root must work: HTML scripts and styles, JavaScript imports, CSS imports and URLs, assets, Python imports, templates and configuration files in sibling or parent directories.

## Supported launch adapters

Initial adapters:

- static web
- Python script
- Python ASGI and WSGI servers
- Streamlit and Django development server
- Node script and npm script
- Vite or Next development server
- composite profile for multiple dependent services

Do not expose a general unbounded shell-command API. Convert each launch kind into a structured adapter.

## Workspace

The mobile Play workspace contains Preview, Files, Logs and Terminal tabs, plus Run, Restart, Stop, Reload, external-tab, fullscreen, send-to-Atlas and Close actions.

Preview is served through a KasaneCore gateway, not `file://` and not a directly exposed temporary port. Files are editable only when the shared workspace access policy grants write permission. Logs combine process output, traceback, browser console, request failures and lifecycle events.

## Session lifecycle

States:

```text
created -> resolving_target -> resolving_environment -> preparing
-> starting -> running -> stopping -> stopped
```

Failure and recovery states are `failed`, `recoverable`, `expired` and `purged`. Every process, child process, port, runtime directory and event stream belongs to one session ID and is reclaimed after stop, failure, expiry or server restart recovery.

## Access checks

Read, write, execute and serve are independent permissions. Resolve paths structurally and reject traversal, encoded traversal, drive or UNC escape, case tricks and links resolving outside the project root. Environment and dependency directories may be used for execution but are not normal editable project content.

## Repair handoff

A failed session can create a typed Atlas repair handoff containing target, dependency graph, runtime environment, launch adapter, logs, browser failures, observed files, hashes and reproduction session ID. Play itself does not silently modify source files.
