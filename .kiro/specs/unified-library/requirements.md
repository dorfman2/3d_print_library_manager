# Requirements — Unified 3D Print Library

## Purpose

Combine two existing projects into one cross-platform application:

- **Viewer** (`3d_print_library_manager`) — browser-based visual library with
  thumbnails, tags, search, and file open/reveal. Flask + SQLite + Three.js.
- **Sorter** (`3d-print-library`) — auto-ingests new files from a watched Source
  folder into the organized library: name cleanup, keyword categorization,
  ZIP handling, duplicate detection.

The combined program covers the full lifecycle: **download → auto-sort → browse**.

## Vision

A single Flask application that:
1. **Ingests** — sorts new files from a Source folder into the library (Sorter logic)
2. **Browses** — visual thumbnail library with tags and search (Viewer logic)
3. **Runs as one service** — the sorter runs on a schedule in a background thread,
   controlled from the web UI (replacing the Windows-only tray app)
4. **Is cross-platform** — macOS and Windows, no OS-specific tray/registry code
   in the core

## Functional Requirements

### FR-1: Preserve existing Viewer functionality
- MUST retain all current viewer features: folder grid, file grid, tags, search,
  category sidebar, Three.js thumbnails, 3MF preview extraction, open/reveal,
  batch generation, scan
- MUST NOT regress any existing endpoint or UI behavior

### FR-2: Port Sorter logic to a cross-platform module
- MUST port `sort_downloads.py` five-phase sync into a new `sorter.py` module
- MUST work on macOS and Windows (no Windows-only calls in the core logic)
- MUST preserve all five phases:
  1. Pre-process Source ZIPs (extract in place, delete redundant ZIPs)
  2. Build library index (collect existing cleaned project names)
  3. Collect and categorize candidates (name cleanup + keyword scoring + dedup)
  4. Move to library
  5. Clean library ZIPs
- MUST preserve the name-cleanup rules exactly (version tags, file-type tags,
  author suffixes, separator replacement, title-casing, acronym preservation)
- MUST preserve keyword-based category scoring
- MUST support dry-run mode (preview without moving)

### FR-3: Web-based sync controls (replace tray app)
- MUST add a "Sync" panel to the web UI
- MUST let the user configure the Source folder (default: OS Downloads folder)
- MUST let the user configure the Library folder (default: current working library)
- MUST provide a "Run Now" button (dry-run and execute)
- MUST provide a scheduler: enable/disable, interval in minutes (1–1440)
- MUST show sync status (idle/running/scheduled), last run, next run
- MUST show a preview (dry-run output) before executing
- MUST display a log of moves, skips, and ZIP operations

### FR-4: Configurable categories
- MUST store categories and their keywords in a config file or DB table
- MUST ship a merged starter category list (`categories.default.json`) combining
  work-focused and hobby-focused categories (19 categories + Uncategorized)
- MUST let the user add/rename/delete categories and edit keyword lists via the UI
- MUST NOT force default categories onto an existing library with custom categories
- MUST reconcile: the Viewer derives categories from folder names on disk; the
  Sorter maps keywords to category folder names. Both read the same list.

### FR-4b: First-run setup wizard
- MUST detect first run (no `categories.json`, no `config.json`)
- MUST present a setup choice:
  1. **Starter library** — seed all merged categories and create the folders on disk
  2. **Use existing library** — scan an existing folder, derive categories from its
     actual on-disk folder names (no folders created or renamed)
  3. **Custom / blank** — start with only `Uncategorized`; user adds categories
- MUST let the user pick the library location during setup (default: `~/3D Prints`)
- MUST let the user pick the source/watch folder during setup (default: `~/Downloads`)
- MUST allow skipping the wizard and configuring later from the Sync panel
- MUST write `config.json` and `categories.json` at the end of setup

### FR-5: Auto re-index after sync
- MUST trigger the Viewer's scanner automatically after a successful sync
- MUST update the folder/file/thumbnail index so newly-sorted files appear
  in the browser without a manual rescan

### FR-6: Shared configuration
- MUST use a single config file for both Viewer and Sorter settings
- MUST store: source folder, library folder, sync interval, autostart preference,
  server port

## Non-Functional Requirements

### NFR-1: Cross-platform
- Core sync + view logic MUST run identically on macOS and Windows
- OS-specific features (tray icon, registry autostart, installer) MUST be
  optional add-ons that degrade gracefully when unavailable

### NFR-2: Dependencies
- MUST keep the runtime dependency footprint minimal
- Core: Flask, stdlib (sqlite3, zipfile, shutil, pathlib)
- Optional (Windows tray): pystray, Pillow, ttkbootstrap — only if tray mode used
- Three.js from CDN (browser)

### NFR-3: Testing
- MUST use real-filesystem integration tests (no mocks), per python-prefs.md
- MUST test the sorter phases on tmp_path fixtures
- MUST verify name-cleanup and categorization with table-driven cases

### NFR-4: Safety
- MUST default to dry-run for sync operations
- MUST never delete a source file without confirming the move succeeded
- MUST never overwrite an existing library file (append `_2`, `_3`, …)
- MUST log every destructive operation

## Print File Extensions

`.stl` `.3mf` `.obj` `.step` `.stp` `.f3d` `.f3z` `.amf` `.gcode` `.bgcode` `.gco`

## Out of Scope (v1 of unified app)

- Windows tray app and Inno Setup installer (keep as optional, separate deliverable)
- Re-categorizing existing library items (moving between categories)
- Password-protected ZIPs
- Scanning nested subdirectories of the Source folder (root level only)

## Reference Documents
- #[[file:.library/SPEC.md]]
- #[[file:.library/EDGE_CASES.md]]
