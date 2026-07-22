# Edge Cases & Update Behavior

Analysis based on actual folder structure and file contents.

---

## Thumbnail & Rendering Edge Cases (Spec v2)

### 13. Large STL Files Served to Browser (up to 13 MB)

**Stats:** 691 renderable files, 24 > 5MB, 5 > 10MB, largest 13.6 MB, avg ~1 MB.

**Decision:**
- Serve via Flask `send_file` with caching headers
- Render ONE file at a time (no parallel flooding)
- Files > 10 MB get a loading indicator
- If Three.js fails to parse → set `thumbnail = '__failed__'` in DB (don't retry)

---

### 14. Concurrent Thumbnail Rendering (Folders with 22+ STLs)

`Prusa Core One Side Storage` has 22 STL files visible at once in Level 2.

**Decision:**
- Render queue: max 3 concurrent
- IntersectionObserver: only render visible cards
- Prioritize cover file first, then top-left to bottom-right

---

### 15. 3MF Without Embedded Previews (26% — 92 of 359)

**Decision:**
- Scanner marks these `thumbnail = NULL`
- Browser uses Three.js 3MFLoader (handles ZIP internally via JSZip)
- If 3MFLoader fails → format icon + `thumbnail = '__failed__'`

---

### 16. Thumbnail Cache Invalidation After File Change

User re-exports a .stl from CAD. Scanner detects hash change.

**Decision:**
- Scanner deletes `thumbnails/<old_hash>.png`
- Sets `thumbnail = NULL` → browser re-renders on next view

---

### 17. Race Condition: Two Tabs Render Same File

Both see `thumbnail = NULL`, both render + POST.

**Decision:**
- `POST /api/thumbnails` writes `<content_hash>.png` — idempotent
- No locking needed; last write wins; content is identical

---

### 18. Browser Without WebGL

**Decision:**
- Check on load: `!!document.createElement('canvas').getContext('webgl')`
- If false: show format icons everywhere; banner: "3D thumbnails require WebGL"
- Tags, search, open, reveal all still work

---

### 19. Filenames with Special Characters

Real examples: `Bed = 100.stl`, `159939-006_01 (BOARD, RX S1-S2).3mf`, `SMC 25 (1).jpeg`

**Decision:**
- All API calls use integer `file_id` — filenames never appear in URLs
- `/api/files/<id>/raw` looks up path by ID, serves via `send_file`
- No URL encoding issues possible

---

### 20. Container with Only PDF + Subfolders (No Printable Files Directly)

`Prusa Tool Box/` has only a PDF at its level + 4 subfolders with real models.

**Decision:**
- PDF is non-printable → doesn't trigger leaf classification
- Folder is a **container** (drills into subfolder grid)
- Only STL/3MF/OBJ/STEP/F3D count for leaf determination

---

### 21. Orphan Thumbnail Accumulation

Old `<hash>.png` files pile up as files change over time.

**Decision:**
- Post-scan cleanup: collect all known hashes from DB, delete any PNG not in the set
- Also clear `__failed__` entries if file hash changed (allow retry)

---

## Folder Structure Edge Cases (Preserved from v1)

### 1. Folder Depth (up to 4 levels)

**Decision:** Container/leaf logic. Containers show subfolder grid. Leaves show file grid.
Breadcrumb handles unlimited depth.

Mixed folders (subfolders + loose files) → treated as leaf with a "Subfolders" section.

---

### 2. Loose Files in Category Root

**Decision:** Auto-create synthetic "(Loose Files)" folder card. `is_synthetic = 1`.

---

### 3. `files/` and `images/` Asset Subfolders (Printables Downloads)

**Decision:**
- Flatten `files/` contents into parent folder's file list
- `images/` contents become cover photo candidates
- `LICENSE.txt`, `README.txt` ignored

---

### 4. `_model_files` Suffix Still Present

**Decision:** Strip from display name. Cleaning rules:
1. Strip `_model_files`
2. Strip trailing UUID
3. Strip leading part-number prefix
4. Replace `-`/`_` with spaces
5. Title-case

---

### 5. STL + 3MF Variants of Same Model

**Decision:** Show all files individually. No deduplication.

---

### 6. Non-Printable-Only Folders (`0 - CONFIG Files`)

**Decision:** Skipped entirely. Not in DB.

---

### 7. Images Alongside Model Files

**Decision:** Cover candidates, not file cards. Not shown in Level 2.

---

### 8. STP-Named Folders (No Extension)

**Decision:** Treat as leaf folder. Generic STEP icon.

---

### 9. Version Subfolders (V4/V5/V6)

**Decision:** Each is its own card inside container. Automatic.

---

### 10. Duplicate Filenames Across Subfolders

**Decision:** Full path as DB key. Content hash shares thumbnail if identical.

---

### 11. .ini / .txt / .md Files

**Decision:** Ignored. Excluded extensions:
`.ini .txt .md .xml .json .cfg .log .zip .7z .rar`

---

### 12. Large File-Count Folders (14+ files)

**Decision:** Responsive grid. IntersectionObserver + render queue prevents flooding.

---

## Update Behavior

### Triggers
Manual only: ↺ button in UI or `python scanner.py`. No file watcher in v1.

### Rescan Rules

| Condition | Action |
|-----------|--------|
| New file on disk | INSERT; extract 3MF preview if applicable |
| File hash unchanged | Skip |
| File hash changed | UPDATE; re-extract preview; delete old thumbnail |
| File missing from disk | Set `status = 'missing'` |
| New folder on disk | INSERT; auto-tag with category |
| Folder missing from disk | Set `status = 'missing'` |

### Never Auto-Deleted
- User tags, notes, cover selections
- Missing file/folder rows (user manually removes)

---

## Summary

| # | Edge Case | Decision |
|---|-----------|----------|
| 1 | Folder depth > 2 | Container/leaf + breadcrumb |
| 2 | Loose files in category | Synthetic folder card |
| 3 | files/ + images/ subfolders | Flatten into parent |
| 4 | _model_files suffix | Strip from display name |
| 5 | STL + 3MF duplicates | Show all, no dedup |
| 6 | Non-printable folders | Skip |
| 7 | Images alongside models | Cover candidates only |
| 8 | STP-named folders | Leaf + STEP icon |
| 9 | Version subfolders | Own card inside container |
| 10 | Duplicate filenames | Full path key, shared hash |
| 11 | .ini/.txt files | Ignored |
| 12 | Large file-count folders | IntersectionObserver |
| 13 | Large STL files (13 MB) | Loading indicator, one-at-a-time |
| 14 | 22+ concurrent renders | Max 3 parallel, viewport-only |
| 15 | 3MF without preview (26%) | Three.js 3MFLoader fallback |
| 16 | Thumbnail invalidation | Delete old PNG, set NULL |
| 17 | Two-tab race condition | Idempotent write, no lock |
| 18 | No WebGL | Format icons + banner |
| 19 | Special chars in filenames | Integer IDs in all API |
| 20 | Container with only PDF | PDF doesn't count as printable |
| 21 | Orphan thumbnails | Post-scan cleanup pass |
