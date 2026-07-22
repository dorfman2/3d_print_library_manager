# Tasks — Unified 3D Print Library

## Task 1: Shared configuration module
- [x] Create `.library/config.py` with DEFAULT_CONFIG and load/save functions
- [x] Implement `resolve_downloads_folder()` — cross-platform `~/Downloads`
- [x] Implement `resolve_library_folder()` — defaults to parent of `.library/`
- [x] Config persisted to `.library/config.json` (gitignored)
- [x] Add `config.json`, `categories.json` to `.gitignore`
- [x] Verify: config round-trips (save then load returns same values)

## Task 2: Categories module — name cleanup
- [x] Create `.library/categories.py`
- [x] Implement `clean_name()` with all 8 cleanup steps from design.md
- [x] Define NOISE_TOKENS and SMALL_WORDS constants
- [x] Preserve internal-uppercase and all-caps words
- [x] Verify: table-driven test cases from Sorter spec all pass (Ender 3 Fan Duct,
      Case for Rak Wisblock, 3DBenchy, NERF Blaster, etc.)

## Task 3: Categories module — keyword categorization + config
- [x] `.library/categories.default.json` already created (merged 19-category starter)
- [x] Implement `categorize(name, categories)` — score by NUMBER of matched keywords
      (not mere presence), tie-break by lowest category number
- [x] Implement `load_categories()` — read categories.json (do NOT auto-seed; the
      setup wizard writes it)
- [x] Implement `save_categories()` — write categories.json
- [x] No-match → `Uncategorized`
- [x] Verify: known names map to expected categories; distinctive work keywords
      (preforming jig, jam nut) beat generic single-word matches (EC-33)

## Task 4: Sorter module — phases 1 & 2
- [x] Create `.library/sorter.py` with SyncPlanItem and SyncResult dataclasses
- [x] Implement `preprocess_source_zips()` — extract in place, delete redundant ZIPs
- [x] Implement `build_library_index()` — collect cleaned names of existing projects
- [x] Use cross-platform Path operations (no Windows-only calls)
- [x] Verify: ZIP preprocessing on tmp_path (redundant deleted, new extracted)

## Task 5: Sorter module — phases 3, 4, 5
- [x] Implement `collect_candidates()` — folders and loose files, clean + categorize + dedup
- [x] Implement loose-file wrapping (wrap in subfolder named after stem)
- [x] Implement `execute_moves()` — move with unique-path collision handling (_2, _3)
- [x] Implement `clean_library_zips()` — recursive ZIP extraction + deletion in library
- [x] Implement `run_sync()` orchestrating all 5 phases, dry_run aware
- [x] Verify: full sync dry-run and execute on tmp_path fixtures

## Task 6: Server — config and category endpoints
- [x] Add `GET /api/config` and `PATCH /api/config`
- [x] Add `GET /api/categories/config` and `PUT /api/categories/config`
- [x] Category rename moves the on-disk folder
- [x] Category delete moves children to Uncategorized
- [x] Verify: config and category edits persist and reflect on disk

## Task 7: Server — sync endpoints and scheduler
- [x] Implement `SyncScheduler` class (daemon thread, interval-based)
- [x] Add `POST /api/sync/preview` — dry-run, return SyncResult JSON
- [x] Add `POST /api/sync/run` — execute in background thread
- [x] Add `GET /api/sync/status` — state, last_run, next_run, interval, enabled
- [x] Add `POST /api/sync/schedule` — enable/disable, set interval
- [x] Auto-trigger `scanner.run_full_scan()` after successful execute sync
- [x] Verify: preview returns plan, run moves files + reindexes, scheduler fires on interval

## Task 7b: First-run setup wizard
- [x] Detect first run (no config.json AND no categories.json)
- [x] Add `GET /setup` route + `static/setup.html` wizard page
- [x] Wizard step 1: pick library folder (default ~/3D Prints) and source folder
      (default ~/Downloads)
- [x] Wizard step 2: choose category mode — Starter / Use existing / Blank
- [x] "Starter library": seed merged categories, create category folders (only if
      library empty; warn + disable if non-empty per EC-32)
- [x] "Use existing": derive categories from on-disk folder names, no folders created
- [x] "Blank": seed only Uncategorized
- [x] Write config.json + categories.json at completion; redirect to library
- [x] Wizard is skippable (configure later in Sync panel)
- [x] Root route `/` redirects to `/setup` on first run
- [x] Verify: each of the three modes produces correct categories.json and folder state

## Task 8: Frontend — sync panel page
- [x] Create `.library/static/sync.html` — source/library inputs, schedule, buttons, log
- [x] Add `GET /sync` route serving sync.html
- [x] Add "Sync" link in main header (next to Generate)
- [x] Create `.library/static/sync.js` — fetch config, run preview/sync, poll status
- [x] Render preview/log output (moves, skips, ZIP ops) with color coding
- [x] Extend `style.css` with sync panel styles
- [x] Verify: panel loads, preview shows dry-run plan, run executes and updates library

## Task 9: Frontend — category editor
- [x] Add category list + keyword editor to sync.html
- [x] Add/rename/delete category via UI (calls PUT /api/categories/config)
- [x] Edit keyword lists per category
- [x] Verify: category edits persist, rename moves folder, new files sort correctly

## Task 9b: Edge-case hardening (see EDGE_CASES.md)
- [x] Implement `migrate_folder_metadata(old_path, new_path)` in scanner.py — moves
      tags/notes/cover to new path so Sorter moves and category renames don't orphan
      metadata (EC-1)
- [x] Config validation: reject Source == Library, nested either way (EC-4)
- [x] Sorter hard-skips `.library`, `.kiro`, dotfolders, config/db files (EC-5)
- [x] `resolve_downloads_folder()` graceful fallback when missing (EC-6)
- [x] Use casefold() for dedup comparison, preserve on-disk case (EC-7)
- [x] Safe ZIP extraction: reject `..` and absolute member paths (EC-9)
- [x] Wrap every ZIP and move op in try/except; one failure never aborts sync
      (EC-10, EC-16, EC-17)
- [x] Shared lock across sync + scan; scheduler non-reentrant, skips if busy
      (EC-12, EC-13)
- [x] Snapshot category list at sync start (EC-14)
- [x] Trailing-author-only `by` stripping; preserve mid-name `by` (EC-24)
- [x] Multi-category tie-break by lowest category number; log decision (EC-25)
- [x] No-match → Uncategorized (create if missing) (EC-26)
- [x] Sorter creates category folder on first use (EC-27)
- [x] Seed categories.json from on-disk folders if library non-empty, defaults only
      if empty (EC-28)
- [x] Windows MAX_PATH detection + truncate with hash suffix (EC-19)
- [x] Verify: dedicated tests for EC-1, EC-4, EC-9, EC-24, EC-25, EC-28

## Task 10: Integration and verification
- [x] Wire config source/library folders into scanner and sorter
- [x] End-to-end: drop test files in Source, run sync, verify sorted + browsable
- [x] Verify existing viewer features still work (no regressions)
- [x] Verify auto-reindex: synced files appear in browser without manual rescan
- [x] Update `.library/requirements.txt` if any new deps
- [x] Update README with combined-app usage and the ingest → browse workflow
- [x] Run full test suite (pytest), ensure all pass with real-filesystem fixtures
- [x] Run linting (ruff/flake8, mypy) — remediate all issues

## Task 11: Documentation and steering updates
- [x] Update `.kiro/steering/project-context.md` — combined app scope
- [x] Update `.kiro/steering/tech-context.md` — sorter deps and modules
- [x] Update `.library/SPEC.md` — reference the unified architecture
- [x] Document optional Windows tray wrapper (calls sorter.py, no logic dup)
