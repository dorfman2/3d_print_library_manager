# Tasks — Unified 3D Print Library

## Task 1: Shared configuration module
- [ ] Create `.library/config.py` with DEFAULT_CONFIG and load/save functions
- [ ] Implement `resolve_downloads_folder()` — cross-platform `~/Downloads`
- [ ] Implement `resolve_library_folder()` — defaults to parent of `.library/`
- [ ] Config persisted to `.library/config.json` (gitignored)
- [ ] Add `config.json`, `categories.json` to `.gitignore`
- [ ] Verify: config round-trips (save then load returns same values)

## Task 2: Categories module — name cleanup
- [ ] Create `.library/categories.py`
- [ ] Implement `clean_name()` with all 8 cleanup steps from design.md
- [ ] Define NOISE_TOKENS and SMALL_WORDS constants
- [ ] Preserve internal-uppercase and all-caps words
- [ ] Verify: table-driven test cases from Sorter spec all pass (Ender 3 Fan Duct,
      Case for Rak Wisblock, 3DBenchy, NERF Blaster, etc.)

## Task 3: Categories module — keyword categorization + config
- [ ] `.library/categories.default.json` already created (merged 19-category starter)
- [ ] Implement `categorize(name, categories)` — score by NUMBER of matched keywords
      (not mere presence), tie-break by lowest category number
- [ ] Implement `load_categories()` — read categories.json (do NOT auto-seed; the
      setup wizard writes it)
- [ ] Implement `save_categories()` — write categories.json
- [ ] No-match → `Uncategorized`
- [ ] Verify: known names map to expected categories; distinctive work keywords
      (preforming jig, jam nut) beat generic single-word matches (EC-33)

## Task 4: Sorter module — phases 1 & 2
- [ ] Create `.library/sorter.py` with SyncPlanItem and SyncResult dataclasses
- [ ] Implement `preprocess_source_zips()` — extract in place, delete redundant ZIPs
- [ ] Implement `build_library_index()` — collect cleaned names of existing projects
- [ ] Use cross-platform Path operations (no Windows-only calls)
- [ ] Verify: ZIP preprocessing on tmp_path (redundant deleted, new extracted)

## Task 5: Sorter module — phases 3, 4, 5
- [ ] Implement `collect_candidates()` — folders and loose files, clean + categorize + dedup
- [ ] Implement loose-file wrapping (wrap in subfolder named after stem)
- [ ] Implement `execute_moves()` — move with unique-path collision handling (_2, _3)
- [ ] Implement `clean_library_zips()` — recursive ZIP extraction + deletion in library
- [ ] Implement `run_sync()` orchestrating all 5 phases, dry_run aware
- [ ] Verify: full sync dry-run and execute on tmp_path fixtures

## Task 6: Server — config and category endpoints
- [ ] Add `GET /api/config` and `PATCH /api/config`
- [ ] Add `GET /api/categories/config` and `PUT /api/categories/config`
- [ ] Category rename moves the on-disk folder
- [ ] Category delete moves children to Uncategorized
- [ ] Verify: config and category edits persist and reflect on disk

## Task 7: Server — sync endpoints and scheduler
- [ ] Implement `SyncScheduler` class (daemon thread, interval-based)
- [ ] Add `POST /api/sync/preview` — dry-run, return SyncResult JSON
- [ ] Add `POST /api/sync/run` — execute in background thread
- [ ] Add `GET /api/sync/status` — state, last_run, next_run, interval, enabled
- [ ] Add `POST /api/sync/schedule` — enable/disable, set interval
- [ ] Auto-trigger `scanner.run_full_scan()` after successful execute sync
- [ ] Verify: preview returns plan, run moves files + reindexes, scheduler fires on interval

## Task 7b: First-run setup wizard
- [ ] Detect first run (no config.json AND no categories.json)
- [ ] Add `GET /setup` route + `static/setup.html` wizard page
- [ ] Wizard step 1: pick library folder (default ~/3D Prints) and source folder
      (default ~/Downloads)
- [ ] Wizard step 2: choose category mode — Starter / Use existing / Blank
- [ ] "Starter library": seed merged categories, create category folders (only if
      library empty; warn + disable if non-empty per EC-32)
- [ ] "Use existing": derive categories from on-disk folder names, no folders created
- [ ] "Blank": seed only Uncategorized
- [ ] Write config.json + categories.json at completion; redirect to library
- [ ] Wizard is skippable (configure later in Sync panel)
- [ ] Root route `/` redirects to `/setup` on first run
- [ ] Verify: each of the three modes produces correct categories.json and folder state

## Task 8: Frontend — sync panel page
- [ ] Create `.library/static/sync.html` — source/library inputs, schedule, buttons, log
- [ ] Add `GET /sync` route serving sync.html
- [ ] Add "Sync" link in main header (next to Generate)
- [ ] Create `.library/static/sync.js` — fetch config, run preview/sync, poll status
- [ ] Render preview/log output (moves, skips, ZIP ops) with color coding
- [ ] Extend `style.css` with sync panel styles
- [ ] Verify: panel loads, preview shows dry-run plan, run executes and updates library

## Task 9: Frontend — category editor
- [ ] Add category list + keyword editor to sync.html
- [ ] Add/rename/delete category via UI (calls PUT /api/categories/config)
- [ ] Edit keyword lists per category
- [ ] Verify: category edits persist, rename moves folder, new files sort correctly

## Task 9b: Edge-case hardening (see EDGE_CASES.md)
- [ ] Implement `migrate_folder_metadata(old_path, new_path)` in scanner.py — moves
      tags/notes/cover to new path so Sorter moves and category renames don't orphan
      metadata (EC-1)
- [ ] Config validation: reject Source == Library, nested either way (EC-4)
- [ ] Sorter hard-skips `.library`, `.kiro`, dotfolders, config/db files (EC-5)
- [ ] `resolve_downloads_folder()` graceful fallback when missing (EC-6)
- [ ] Use casefold() for dedup comparison, preserve on-disk case (EC-7)
- [ ] Safe ZIP extraction: reject `..` and absolute member paths (EC-9)
- [ ] Wrap every ZIP and move op in try/except; one failure never aborts sync
      (EC-10, EC-16, EC-17)
- [ ] Shared lock across sync + scan; scheduler non-reentrant, skips if busy
      (EC-12, EC-13)
- [ ] Snapshot category list at sync start (EC-14)
- [ ] Trailing-author-only `by` stripping; preserve mid-name `by` (EC-24)
- [ ] Multi-category tie-break by lowest category number; log decision (EC-25)
- [ ] No-match → Uncategorized (create if missing) (EC-26)
- [ ] Sorter creates category folder on first use (EC-27)
- [ ] Seed categories.json from on-disk folders if library non-empty, defaults only
      if empty (EC-28)
- [ ] Windows MAX_PATH detection + truncate with hash suffix (EC-19)
- [ ] Verify: dedicated tests for EC-1, EC-4, EC-9, EC-24, EC-25, EC-28

## Task 10: Integration and verification
- [ ] Wire config source/library folders into scanner and sorter
- [ ] End-to-end: drop test files in Source, run sync, verify sorted + browsable
- [ ] Verify existing viewer features still work (no regressions)
- [ ] Verify auto-reindex: synced files appear in browser without manual rescan
- [ ] Update `.library/requirements.txt` if any new deps
- [ ] Update README with combined-app usage and the ingest → browse workflow
- [ ] Run full test suite (pytest), ensure all pass with real-filesystem fixtures
- [ ] Run linting (ruff/flake8, mypy) — remediate all issues

## Task 11: Documentation and steering updates
- [ ] Update `.kiro/steering/project-context.md` — combined app scope
- [ ] Update `.kiro/steering/tech-context.md` — sorter deps and modules
- [ ] Update `.library/SPEC.md` — reference the unified architecture
- [ ] Document optional Windows tray wrapper (calls sorter.py, no logic dup)
