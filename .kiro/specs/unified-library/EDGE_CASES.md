# Edge Cases — Unified 3D Print Library

Analysis of new edge cases created by combining the Sorter (ingest) with the
Viewer (browse). The two systems share a library folder, a database, and a
category list — most new risks live at that seam.

---

## Category A: Metadata Survival (highest risk)

### EC-1: Sorter move orphans viewer tags/notes/covers
The viewer keys folders by **absolute path** (confirmed: 101 folders have tags,
2 have custom covers). When the Sorter moves a folder into the library, or the
category editor renames a category folder, the path changes. On the next scan
the old path is marked `missing` and the moved folder appears as brand-new with
**no tags, no notes, no cover**.

**Decision:**
- Before any Sorter move or category rename, look up the folder's viewer metadata
  by old path and **re-attach it to the new path** after the move.
- Add a `migrate_folder_metadata(old_path, new_path)` helper in scanner.py that
  updates `folders.path` (and cascade) instead of orphaning.
- Category rename must call this for every child folder.

### EC-2: Two folders clean to the same name
`Ender_3_Fan_Duct_v3` and `ender-3-fan-duct-FINAL` both clean to
`Ender 3 Fan Duct`. Sorter dedup would skip the second as a duplicate — but it
may be a genuinely different model.

**Decision:**
- Dedup match is on cleaned name within the SAME target category only.
- On collision at move time, append `_2`, `_3` (already in Sorter spec) rather
  than silently skipping when content differs.
- Log both so the user can review.

### EC-3: Cleaned name collides with an existing viewer-tagged folder
Sorter appends `_2`; the viewer sees a new untagged folder. User expected it to
merge with the tagged original.

**Decision:** Never auto-merge. Keep `_2`. Surface in the sync log so the user
can manually consolidate and re-tag.

---

## Category B: Folder Overlap & Paths

### EC-4: Source folder == Library folder (or nested)
If the user points Source at `~/3D Prints` (the library itself), the Sorter would
try to move files into subfolders of themselves — infinite/destructive.

**Decision:**
- Reject config where Source == Library, or Source is inside Library, or Library
  is inside Source. Validate on `PATCH /api/config` and refuse with a clear error.

### EC-5: The `.library/` folder is inside the library
The Sorter walks the library; the viewer's own `.library/`, `.kiro/`, `thumbnails/`,
`library.db` must never be treated as print projects or moved.

**Decision:** Sorter and scanner both hard-skip `.library`, `.kiro`, dotfolders,
and the config/db files. (Scanner already skips these — Sorter must too.)

### EC-6: Downloads folder doesn't exist / not resolvable
`~/Downloads` may not exist (fresh machine, non-English locale, redirected).

**Decision:** `resolve_downloads_folder()` falls back gracefully: if `~/Downloads`
missing, leave Source unset and show a prompt in the UI to pick one. Never crash.

### EC-7: Case-insensitive filesystem (macOS default)
`Fan Duct` and `fan duct` are the same folder on macOS/APFS default but different
on case-sensitive Linux. Dedup and collision checks may behave differently per OS.

**Decision:** Normalize names to casefold() for dedup comparison. Preserve original
case for the actual folder name on disk.

---

## Category C: ZIP Handling

### EC-8: Nested ZIPs (ZIP inside a ZIP)
Extracting a ZIP yields another ZIP. Sorter phase 5 is recursive over the library
but phase 1 extracts Source ZIPs once.

**Decision:** Phase 1 extracts one level; any inner ZIP is caught by phase 5's
recursive library cleanup after the move. Document this two-stage behavior.

### EC-9: ZIP with path traversal entries (`../../etc`)
Malicious or malformed ZIP with `..` members could write outside the target.

**Decision:** Validate each ZIP member path stays within the extraction dir
(reject/skip `..` and absolute paths). Use a safe-extract helper, not raw
`extractall()`.

### EC-10: Password-protected or corrupt ZIP
Out of scope per requirements, but must not crash the whole sync.

**Decision:** Wrap each ZIP op in try/except; log failure, skip, continue. One bad
ZIP never aborts the sync.

### EC-11: ZIP contains no print files
A ZIP of only images/README extracted into Downloads root creates clutter.

**Decision:** Phase 1 only extracts ZIPs that contain at least one print file
(matches Sorter spec). Non-print ZIPs are left untouched.

---

## Category D: Concurrency

### EC-12: Sync runs while a scan is running (or vice versa)
Auto-reindex after sync could collide with a manual scan; the scheduler could fire
mid-scan.

**Decision:** Single shared lock. Sync acquires it, runs, then triggers scan under
the same lock. Scheduler skips a tick if the lock is held (log "skipped, busy").

### EC-13: Scheduler fires while a previous sync is still running
Long sync (huge Downloads) overruns the interval.

**Decision:** Non-reentrant — `run_once` is a no-op if a sync is already active.
Next tick proceeds normally.

### EC-14: User edits categories mid-sync
Category list changes while `collect_candidates` is scoring against it.

**Decision:** Snapshot the category list at sync start; edits apply to the next run.

### EC-15: Browser thumbnail POST during sorter move
Viewer posts a rendered thumbnail keyed by content hash while the file is being
moved.

**Decision:** Thumbnails are keyed by content hash, not path — a move doesn't
invalidate them. Safe. The DB row's folder_id updates on rescan.

---

## Category E: File Operations

### EC-16: Source file is open/locked (in a slicer)
Moving a file open in PrusaSlicer fails on Windows (lock), succeeds on macOS.

**Decision:** Wrap move in try/except; on failure log and skip that item, continue
the rest. Never delete the source until the move is confirmed.

### EC-17: Cross-device move (Source and Library on different drives)
`shutil.move` across filesystems falls back to copy+delete, which is slow and can
partially fail.

**Decision:** Use `shutil.move` (handles cross-device). On failure mid-copy, do
not delete source; log partial state for user review.

### EC-18: Move target exists as a file, not a folder
A file named like the target folder blocks the move.

**Decision:** Collision handler checks type; if a non-folder blocks, append `_2`.

### EC-19: Very deep or long paths (Windows 260-char limit)
Cleaned name + category + library root may exceed Windows MAX_PATH.

**Decision:** Detect path length on Windows; if over limit, truncate cleaned name
with a hash suffix and log. macOS unaffected.

### EC-20: Loose file with no extension or unknown type
A print file with a weird/missing extension at Source root.

**Decision:** Only wrap+move files matching the recognized print extensions.
Everything else at Source root is ignored (left in place).

---

## Category F: Name Cleanup

### EC-21: Name cleans to empty string
`v1_FINAL_stl` → all noise tokens stripped → empty.

**Decision:** Rule 8 already handles this — return original name unchanged.

### EC-22: Name is only an acronym or number
`MMU`, `40k`, `3DBenchy` must survive cleanup (all-caps / internal-caps / leading digit).

**Decision:** Preserve all-caps and internal-uppercase words; don't title-case them.
Verify with test cases.

### EC-23: Unicode / emoji in names
`Café_Sign_🎉_v2.stl` — separators, emoji, accents.

**Decision:** Cleanup operates on Unicode-safe string ops. Preserve accented chars;
strip emoji only if they're separator-adjacent noise. Filesystem-safe on both OSes
(both support Unicode filenames).

### EC-24: Author suffix removal is too aggressive
`by` in `Fly by Wire Bracket` is a real word, not an author tag.

**Decision:** Only strip `by <author>` when `by` is followed by a single trailing
token at the END of the name. Mid-name `by` is preserved. Add test cases both ways.

---

## Category G: Categorization

### EC-25: Name matches keywords in multiple categories
`Raspberry Pi Camera Mount for Drone` matches Electronics (raspberry pi) and
RC Flight (drone).

**Decision:** Highest keyword-match score wins; tie broken by category order
(lowest number first). Log the decision so the user can re-tag if wrong.

### EC-26: Name matches no keywords
Generic name like `Thing v2`.

**Decision:** Assign to `Uncategorized` (create if missing). Never fail the move.

### EC-27: Sorter category doesn't exist as a folder yet
Keyword maps to `9 - Tabletop` but the library has no such folder.

**Decision:** Sorter creates the category folder on first use. Viewer picks it up
on the auto-rescan.

### EC-28: Category list and on-disk folders diverge
User's library has `6 - Work Fixtures and Tooling`; a default list has
`6 - Electronics`. Same number, different name → two folders numbered 6.

**Decision:** The first-run setup wizard eliminates the auto-seed guess. The user
explicitly picks: (1) starter merged library, (2) derive from existing on-disk
folders, or (3) blank. For an existing library the user chooses "Use existing" and
categories are read from actual folder names — no divergence. The merged default is
only applied when the user explicitly picks "Starter library."

### EC-32: Merged category number collision on "Starter" over existing library
User picks "Starter library" but already has folders like `6 - Work Fixtures`.
Seeding `6 - Electronics` creates a conflicting number.

**Decision:** If the chosen library folder is non-empty, the wizard disables/warns
on the "Starter library" option and steers to "Use existing." Starter only creates
folders in an empty (or new) library location.

### EC-33: Work-category keyword loses tie to hobby category
`Cable Preforming Jig` — `jig` matches Tools (4) and Work Fixtures (16). Tie breaks
to lower number → wrongly lands in Tools.

**Decision:** Score by number of matched keywords, not just presence. Distinctive
multi-word work keywords (`preforming jig`, `work holding`) score higher than the
generic single `jig`. Where still ambiguous, user re-tags in the viewer or adds a
keyword. Documented tuning tradeoff.

---

## Category H: Viewer Integration

### EC-29: Synthetic "(Loose Files)" vs Sorter loose-file wrapping
The viewer auto-creates synthetic "(Loose Files)" cards for loose files in category
roots. The Sorter wraps loose Source files into named subfolders. After sync there
should be no loose files in category roots — but manually-added ones still get the
synthetic treatment.

**Decision:** No conflict — Sorter wraps at ingest, viewer handles any that appear
by other means. Document that Sorter output never produces synthetic folders.

### EC-30: Auto-rescan after sync is slow on large library
Full rescan of 700+ files after every sync adds latency.

**Decision:** Incremental scan (already implemented — skips unchanged by hash).
Only newly-moved files are processed. Fast.

### EC-31: Sync moves a folder that's currently open in the viewer (Level 2)
User is viewing a folder's files when a scheduled sync moves/renames it.

**Decision:** Viewer fetches by folder_id; if the row is gone/missing after rescan,
show a "this folder moved" message and route back to Level 1.

---

## Summary Table

| # | Edge Case | Decision |
|---|-----------|----------|
| 1 | Move orphans tags/notes/covers | migrate_folder_metadata(old,new) |
| 2 | Two names clean identically | dedup per-category, else _2 |
| 3 | Cleaned name hits tagged folder | never auto-merge, log |
| 4 | Source == Library / nested | reject in config validation |
| 5 | .library inside library | hard-skip in sorter + scanner |
| 6 | Downloads missing | graceful fallback, prompt |
| 7 | Case-insensitive FS | casefold() for dedup |
| 8 | Nested ZIPs | phase1 one level, phase5 recursive |
| 9 | ZIP path traversal | safe-extract, reject `..` |
| 10 | Bad/locked ZIP | try/except, skip, continue |
| 11 | ZIP w/o print files | don't extract |
| 12 | Sync vs scan collision | shared lock |
| 13 | Scheduler overrun | non-reentrant |
| 14 | Categories edited mid-sync | snapshot at start |
| 15 | Thumbnail POST during move | hash-keyed, safe |
| 16 | Source file locked | skip, don't delete source |
| 17 | Cross-device move | shutil.move, no delete on fail |
| 18 | Target is a file | collision handler _2 |
| 19 | Windows MAX_PATH | truncate + hash suffix |
| 20 | Unknown extension | ignore non-print files |
| 21 | Name cleans to empty | return original |
| 22 | Acronym-only name | preserve caps |
| 23 | Unicode/emoji | Unicode-safe ops |
| 24 | Aggressive `by` strip | only trailing author token |
| 25 | Multi-category match | highest score, tie=lowest number |
| 26 | No keyword match | Uncategorized |
| 27 | Category folder missing | create on first use |
| 28 | Category list vs disk diverge | seed from disk if library exists |
| 29 | Synthetic vs wrapped loose files | no conflict, documented |
| 30 | Slow auto-rescan | incremental (hash skip) |
| 31 | Open folder moved mid-view | route to Level 1 with notice |
| 32 | Starter over existing library | warn/disable, steer to "Use existing" |
| 33 | Work keyword loses tie | score by match count, distinctive keywords |
