# Requirements — 3D Print Library

## Purpose
A browser-based visual library for a local collection of ~700 3D print files.
Runs as a Python Flask server on localhost:5050. Cross-platform (macOS + Windows).

## Functional Requirements

### FR-1: Scanner
- MUST walk the `3D Prints/` folder tree, skipping `.library/` and `.kiro/`
- MUST identify top-level numbered folders as categories
- MUST classify non-category folders as leaf (has printable files) or container (has subfolders only)
- MUST flatten `files/` and `images/` asset subfolders into their parent folder
- MUST create synthetic "(Loose Files)" folder cards for printable files directly in category roots
- MUST skip folders that contain zero printable files after filtering
- MUST index each printable file: path, filename, format, size, modified date, SHA-256 content hash
- MUST extract embedded preview PNGs from .3mf files (ZIP `Metadata/thumbnail.png` or `Metadata/plate_1.png`)
- MUST store extracted previews in `.library/thumbnails/<hash>.png`
- MUST apply display-name cleaning rules (strip `_model_files`, UUIDs, part-number prefixes)
- MUST auto-create tags from category names on first scan
- MUST support incremental rescan: skip unchanged files (by hash), detect missing files
- MUST never auto-delete user tags, notes, or cover selections
- MUST track scan progress in the database

### FR-2: Flask Server
- MUST serve on `http://127.0.0.1:5050`
- MUST serve static files from `.library/static/`
- MUST serve cached thumbnails from `.library/thumbnails/`
- MUST serve raw model files for Three.js rendering via `/api/files/<id>/raw`
- MUST provide REST API for: folders, files, tags, categories, scan, open, reveal, thumbnail upload
- MUST open files via OS command (`open` on macOS, `start` on Windows)
- MUST reveal files in Finder/Explorer via OS command
- MUST validate file_id exists in DB before executing OS commands
- MUST bind to 127.0.0.1 only (not 0.0.0.0)

### FR-3: Browser UI
- MUST display a two-level visual browse: folder grid (Level 1) → file grid (Level 2)
- MUST support unlimited depth via container/leaf logic and breadcrumb navigation
- MUST show a category sidebar with folder counts
- MUST show a tag sidebar with usage counts and add-tag capability
- MUST provide a search bar that filters folder names and tags (client-side)
- MUST support combinable filters: category + tag + search (AND logic)
- MUST display folder cards with: cover thumbnail, name, file count, format badges, tag chips
- MUST display file cards with: thumbnail or format icon, filename, format badge, file size
- MUST provide Open button per file (calls server open endpoint)
- MUST provide Reveal button per file (calls server reveal endpoint)
- MUST provide Cover button per file (sets folder cover_file_id)
- MUST provide inline tag editing on folders (add/remove)
- MUST provide inline notes editing on folders (textarea, save on blur)
- MUST render STL/OBJ/3MF thumbnails client-side via Three.js when no cached thumbnail exists
- MUST POST rendered thumbnails to server for caching
- MUST show format icons for non-renderable files (STEP, F3D, bgcode, PDF)
- MUST show scan progress indicator when scan is running
- MUST handle WebGL unavailability gracefully (format icons + banner)

## Non-Functional Requirements

### NFR-1: Performance
- Initial scan < 60 seconds for ~700 files
- Incremental rescan (no changes) < 3 seconds
- Page load (Level 1) < 1 second
- Individual thumbnail render < 500ms
- Tag/search filtering < 100ms

### NFR-2: Dependencies
- Python: only `flask` (no rendering libraries)
- Browser: Three.js from CDN (no build step)
- No Docker, no cloud, no accounts

### NFR-3: File Formats
- Renderable: .stl, .3mf, .obj
- Icon-only: .step, .stp, .f3d, .bgcode, .pdf
- Ignored: .ini, .txt, .md, .xml, .json, .cfg, .log, .zip, .7z, .rar

## Reference Documents
- #[[file:.library/SPEC.md]]
- #[[file:.library/EDGE_CASES.md]]
