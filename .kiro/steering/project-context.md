---
inclusion: always
---

# Project Context - Big Picture View

## Project Purpose
A lightweight, browser-based visual library for a personal collection of ~700 3D print files (STL, 3MF, STEP, OBJ, F3D, bgcode). Runs locally as a Python Flask server with a browser UI. No cloud, no Docker, no accounts. Must work identically on macOS and Windows.

## Current Development Status
- v1 COMPLETE — all 13 spec tasks executed and verified
- Folder structure cleanup complete (10 numbered categories, 101 model folders)
- scanner.py: 917 lines, full filesystem walk + 3MF preview extraction
- server.py: 741 lines, 17 API routes, local-only binding
- app.js: 944 lines, two-level browse + Three.js renderer + tags/notes
- Database: 101 folders, 688 files, 11 tags, 265 cached thumbnails
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

## Architecture Overview
```
.library/
├── scanner.py       ← Python: walks folders, indexes DB, extracts 3MF previews
├── server.py        ← Flask: REST API + static file serving on port 5050
├── library.db       ← SQLite: folders, files, tags, folder_tags, scan_status
├── thumbnails/      ← Cached PNG thumbnails (by content hash)
└── static/
    ├── index.html   ← SPA shell
    ├── app.js       ← Three.js rendering + UI logic
    ├── style.css    ← Grid layout, sidebar, responsive
    └── icons/       ← Format icons (step.svg, f3d.svg, bgcode.svg, pdf.svg)
```

## Next Development Priorities
1. Rebuild SPEC.md with Three.js approach
2. Build scanner.py (folder walk, DB, 3MF preview extraction)
3. Build server.py (Flask API, open/reveal, scan trigger, thumbnail cache endpoint)
4. Build frontend (folder grid → file grid, Three.js rendering, tags, search)

## Technical Challenges
- stl-thumb has no macOS binary; pyrender/trimesh require a display — solved by moving rendering to browser
- Folder depth varies 2-4 levels — solved with container/leaf logic
- Printables download structure (`files/`, `images/` subfolders) — solved with asset-folder flattening
- Loose files in category roots — solved with synthetic "(Loose Files)" folder cards
- Special characters in filenames (`=`, `+`, unicode dashes) — solved by using full paths as DB keys
