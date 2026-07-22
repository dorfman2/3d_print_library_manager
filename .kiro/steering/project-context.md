---
inclusion: always
---

# Project Context - Big Picture View

## Project Purpose
A lightweight, browser-based visual library for a personal collection of ~700 3D print files (STL, 3MF, STEP, OBJ, F3D, bgcode). Runs locally as a Python Flask server with a browser UI. No cloud, no Docker, no accounts. Must work identically on macOS and Windows. Includes an auto-sort pipeline that ingests new files from a watched folder, cleans names, categorizes by keywords, and organizes them into the library.

## Current Development Status
- v2 COMPLETE — unified app: Viewer + Sorter merged into one Flask server
- Folder structure cleanup complete (10+ numbered categories, 101+ model folders)
- scanner.py: ~960 lines, full filesystem walk + 3MF preview extraction + migrate_folder_metadata
- server.py: ~1050 lines, 20+ API routes, local-only binding, sync scheduler
- sorter.py: ~640 lines, 5-phase sync pipeline, cross-platform
- config.py: ~130 lines, shared config load/save
- categories.py: ~370 lines, 8-step name cleanup + keyword categorization
- app.js: 944 lines, two-level browse + Three.js renderer + tags/notes
- sync.js: ~380 lines, sync panel + category editor UI
- Database: 101 folders, 688 files, 11 tags, 265 cached thumbnails
- Setup wizard: first-run detection, 3 category modes
- Ready for daily use: `python3 server.py` → http://localhost:5050

## Key Features Designed
- Two-level visual browse: folder grid (Level 1) → file grid (Level 2)
- Unlimited depth via container/leaf folder logic + breadcrumb navigation
- Tag-based filtering and full-text search
- Cover thumbnail selection per folder (user-selectable or auto-first-file)
- One-click Open (OS default app) and Reveal (Finder/Explorer) for every file
- Incremental rescan with missing-file detection
- 3MF embedded preview extraction
- Client-side STL/OBJ rendering via Three.js (cached to server)
- Format icons for non-renderable types
- Auto-sort from Downloads (5-phase sync: ZIP extract, index, categorize, move, clean)
- Web-based sync controls: preview, run, schedule
- Category editor: add/rename/delete categories, edit keywords
- First-run setup wizard (starter / use existing / blank)
- Shared lock between sync and scan (non-reentrant scheduler)

## Architecture Overview
```
.library/
├── scanner.py       ← Python: walks folders, indexes DB, extracts 3MF previews
├── server.py        ← Flask: REST API + static file serving on port 5050
├── sorter.py        ← Python: 5-phase sync pipeline (ingest from Downloads)
├── config.py        ← Python: shared config load/save (JSON)
├── categories.py    ← Python: category list + keyword scoring + name cleanup
├── library.db       ← SQLite: folders, files, tags, folder_tags, scan_status
├── thumbnails/      ← Cached PNG thumbnails (by content hash)
└── static/
    ├── index.html   ← SPA shell
    ├── app.js       ← Three.js rendering + UI logic
    ├── sync.html    ← Sync control panel
    ├── sync.js      ← Sync panel + category editor logic
    ├── setup.html   ← First-run setup wizard
    ├── style.css    ← Grid layout, sidebar, responsive
    └── icons/       ← Format icons (step.svg, f3d.svg, bgcode.svg, pdf.svg)
```

## Next Development Priorities
1. First real-user test of the unified app (ingest + browse)
2. Potential v3 features: interactive 3D viewer, bulk tag editor, AI auto-tagging
3. Dark mode toggle
4. Keyboard navigation
5. Optional Windows tray wrapper (calls sorter.py, no logic dup)

## Technical Challenges
- stl-thumb has no macOS binary; pyrender/trimesh require a display — solved by moving rendering to browser
- Folder depth varies 2-4 levels — solved with container/leaf logic
- Printables download structure (`files/`, `images/` subfolders) — solved with asset-folder flattening
- Loose files in category roots — solved with synthetic "(Loose Files)" folder cards
- Special characters in filenames (`=`, `+`, unicode dashes) — solved by using full paths as DB keys
