# Capsule and Portal Specification

## Names and placement

The top-level mode is **Portal**. The Atlas packaging action is **Capsule**.

Top navigation:

```text
Lumen | Atlas | Portal | Echo | Nexus
```

Atlas header:

```text
[Project]                         [Capsule] [Play] [Plan History]
```

## Capsule eligibility

Capsule creation requires:

- an active Atlas project
- at least one successful Play session
- matching current file hashes or a new successful validation
- one or more selected launch profiles
- package exclusion, manifest and checksum validation

Multiple launch profiles are allowed. A profile may start one entrypoint or a composite set such as an API and frontend with dependency order.

## Package format

The exported artifact is a ZIP named like:

```text
sample-app-1.0.0.portal.zip
```

Required layout:

```text
portal-package.json
checksums.json
application/
metadata/
licenses/
```

The manifest is versioned and stores package identity, version, launch profiles, runtime requirements, requested permissions and data policy. It must not contain a free-form shell command. Launch profiles refer to supported structured adapters.

The package is immutable after registration. Capsule copies a validated snapshot; it does not move or delete the Atlas project.

## Inclusion and exclusion

Include source code, web assets, templates, dependency manifests, lock files, launch profiles, icons, descriptions and licenses.

Exclude development history and runtime state, including `.git`, virtual environments, dependency install directories, caches, logs, generated databases, uploads, session data, local environment files and Atlas conversation or PlanPool artifacts.

The existing Atlas project download is a development archive. A Capsule is a separate distribution contract.

## Portal catalog

Each Portal card shows name, version, icon, trust state, launch profile count, last run, data size and actions.

Actions:

- Run
- choose launch profile
- Data
- Snapshots
- Export Package
- Fork to Atlas
- Uninstall Package
- Delete Data

Package removal and data removal are independent operations.

## Import and export

Import first stores the ZIP in quarantine. Before catalog registration, validate normalized paths, archive size, expanded size, compression ratio, file count, links, special files, manifest schema, checksums, supported adapters and package identity conflicts.

Trust states:

- trusted local Capsule
- verified publisher package
- untrusted imported package

Export Package downloads only the immutable package ZIP. Runtime data is never included. Data Backup is a separate operation and file type.

## Runtime staging

Packages remain compressed while stored. Run creates an isolated session root and performs:

1. package hash and manifest revalidation
2. archive preflight
3. safe extraction into a session application directory
4. read-only application staging
5. creation of a separate writable data layer
6. launch through the public Atlas Play runtime contract
7. process and port cleanup
8. data decision
9. purge of extracted application, cache and temporary files

Portal must not implement a second process runner.

## Data model

Keep four independent layers:

```text
Package ZIP   immutable application
Current Data  committed persistent state
Session Data  writes made during the current run
Cache/Temp    disposable runtime content
```

Snapshots are immutable named copies of committed or session data.

Run modes:

- continue from current data
- start empty
- start from snapshot
- ephemeral run

When stopping a changed session, show:

- Save and exit
- Save as snapshot
- Discard and exit
- Return to app

Saving uses an atomic commit so failure does not corrupt the previous current data. Starting from a snapshot never mutates that snapshot.

Applications receive managed paths such as `PORTAL_DATA_DIR`, `PORTAL_CACHE_DIR`, `PORTAL_TEMP_DIR` and `PORTAL_SESSION_ID`. Package files are not writable.

## Recovery and purge

A browser disconnect does not immediately delete changed session data. Move the session to a recoverable state and allow Resume, Save or Discard. Recovery expires under a bounded policy and is then purged.

After a terminal decision, stop the process tree, release ports, finalize minimal logs, commit or discard session data, and delete extracted application, cache and temporary directories.

## Fork to Atlas

Fork verifies and extracts a package into a new allowed Atlas project. It never edits the registered package in place. The new project becomes the editable development copy.
