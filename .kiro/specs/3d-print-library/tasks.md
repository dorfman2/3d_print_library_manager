# Tasks — 3D Print Library

## Task 1: Project scaffold and requirements.txt
- [x] Create `.library/requirements.txt` with `flask>=3.0`
- [x] Create `.library/thumbnails/` directory (empty, with .gitkeep)
- [x] Create `.library/static/` directory structure
- [x] Create `.library/static/icons/` directory

## Task 2: Scanner — database setup and schema
- [x] Create `.library/scanner.py`
- [x] Implement SQLite database initialization (create all tables and indexes from design.md schema)
- [x] Implement `get_db()` connection helper with row_factory
- [x] Verify: running `python scanner.py` creates `library.db` with correct schema

## Task 3: Scanner — folder walking and classification
- [x] Implement category detection (top-level folders matching `^\d+ - .+`)
- [x] Implement recursive folder walk skipping `.library/`, `.kiro/`, and ignored extensions
- [x] Implement leaf vs container classification logic
- [x] Implement asset-folder flattening (`files/`, `images/`, `assets/`, `renders/`, `photos/`)
- [x] Implement synthetic "(Loose Files)" folder creation for loose files in category roots
- [x] Implement display name cleaning function (strip _model_files, UUIDs, part numbers)
- [x] Implement folder DB insertion with parent_id tracking
- [x] Verify: scan populates `folders` table correctly for the full library

## Task 4: Scanner — file indexing and 3MF preview extraction
- [x] Implement file discovery within leaf folders (respect asset-folder flattening)
- [x] Implement SHA-256 content hashing for each file
- [x] Implement file DB insertion (path, filename, format, size_bytes, modified_at, content_hash)
- [x] Implement 3MF preview extraction (zipfile, check Metadata/thumbnail.png and Metadata/plate_1.png)
- [x] Save extracted previews to `thumbnails/<hash>.png` and set `files.thumbnail`
- [x] Implement incremental rescan logic (skip unchanged, update changed, mark missing)
- [x] Implement orphaned thumbnail cleanup after scan
- [x] Implement scan_status table updates (progress tracking)
- [x] Implement auto-tagging with category name on first scan
- [x] Verify: full scan completes in <60s, `files` table has ~700 rows, thumbnails extracted for 3MF files

## Task 5: Flask server — core API
- [x] Create `.library/server.py`
- [x] Initialize Flask app, configure static folder and thumbnail serving
- [x] Implement `GET /api/categories` — returns list with folder counts
- [x] Implement `GET /api/folders` — with query params: category, tag, q, parent_id, format
- [x] Implement `GET /api/folders/<id>` — single folder with files and tags
- [x] Implement `GET /api/folders/<id>/files` — files in a folder
- [x] Implement `GET /api/tags` — all tags with usage counts
- [x] Implement `POST /api/folders/<id>/tags` — add tag
- [x] Implement `DELETE /api/folders/<id>/tags/<name>` — remove tag
- [x] Implement `PATCH /api/folders/<id>/cover` — set cover_file_id or cover_image
- [x] Implement `PATCH /api/folders/<id>/notes` — update notes
- [x] Verify: server starts, API returns correct JSON for folders/files/tags/categories

## Task 6: Flask server — file serving, open/reveal, scan, thumbnails
- [x] Implement `GET /api/files/<id>/raw` — serve raw model file via send_file
- [x] Implement `POST /api/open/<file_id>` — validate file exists, execute OS open command
- [x] Implement `POST /api/reveal/<file_id>` — validate file exists, execute OS reveal command
- [x] Implement `POST /api/thumbnails` — accept base64 PNG, save to thumbnails/<hash>.png, update DB
- [x] Implement `POST /api/scan` — trigger scanner in background thread
- [x] Implement `GET /api/scan/status` — return current scan progress
- [x] Bind server to 127.0.0.1:5050
- [x] Verify: can open/reveal a file, can POST a thumbnail, scan triggers correctly

## Task 7: Frontend — HTML shell and CSS layout
- [x] Create `.library/static/index.html` — SPA shell with Three.js CDN imports (STLLoader, 3MFLoader, OBJLoader)
- [x] Create `.library/static/style.css` — sidebar (220px fixed), main grid area, responsive cards
- [x] Implement header bar with title, search input, scan button
- [x] Implement sidebar structure: categories section + tags section
- [x] Implement main content area: filter chips + responsive card grid
- [x] Verify: page loads at localhost:5050, layout renders correctly (no JS logic yet)

## Task 8: Frontend — Level 1 folder grid and sidebar logic
- [x] Create `.library/static/app.js`
- [x] Implement state management (current view, filters, folder cache)
- [x] Implement URL hash routing (`#/` for Level 1, `#/folder/<id>` for Level 2)
- [x] Implement category sidebar: fetch categories, render with counts, click to filter
- [x] Implement tag sidebar: fetch tags, render with counts, click to add filter
- [x] Implement folder grid: fetch folders, render cards (thumbnail, name, file count, format badges, tags)
- [x] Implement search bar: client-side filter on folder names and tags
- [x] Implement active filter chips (removable)
- [x] Verify: Level 1 shows all folders, category/tag filtering works, search works

## Task 9: Frontend — Level 2 file grid with Open/Reveal/Cover
- [x] Implement Level 2 view: breadcrumb, back button, file grid
- [x] Implement file cards: thumbnail/icon, filename, format badge, file size
- [x] Implement Open button per file (POST to /api/open/<id>)
- [x] Implement Reveal button per file (POST to /api/reveal/<id>)
- [x] Implement Cover button per file (PATCH folder cover_file_id)
- [x] Implement tag editing on folder (add/remove inline)
- [x] Implement notes editing on folder (textarea, auto-save on blur)
- [x] Implement container folder drill-in (show subfolder cards, not files)
- [x] Implement format filter sidebar for Level 2 (filter files within folder)
- [x] Verify: clicking a folder navigates to Level 2, Open/Reveal work, tags/notes save

## Task 10: Frontend — Three.js thumbnail renderer
- [x] Implement WebGL availability check (show banner if unavailable)
- [x] Implement offscreen WebGLRenderer (256×256, antialias, gray background)
- [x] Implement model loading: STLLoader for .stl, 3MFLoader for .3mf, OBJLoader for .obj
- [x] Implement auto-camera framing (bounding box center + appropriate distance)
- [x] Implement lighting (ambient 0.6 + 2 directional)
- [x] Implement render queue (max 3 concurrent, IntersectionObserver for viewport-only)
- [x] Implement render → canvas.toDataURL → POST to /api/thumbnails
- [x] Implement `__failed__` handling (show format icon, don't retry)
- [x] Verify: browsing a folder with STL files renders thumbnails, cached on refresh

## Task 11: SVG format icons
- [x] Create `.library/static/icons/step.svg` — simple CAD icon
- [x] Create `.library/static/icons/f3d.svg` — Fusion 360 style icon
- [x] Create `.library/static/icons/bgcode.svg` — sliced/gcode file icon
- [x] Create `.library/static/icons/pdf.svg` — document icon
- [x] Create `.library/static/icons/folder.svg` — generic folder icon
- [x] Verify: icons display correctly in file cards for non-renderable formats

## Task 12: Scan progress UI
- [x] Implement scan button (↺) triggers POST /api/scan
- [x] Implement progress polling (GET /api/scan/status every 2s while running)
- [x] Implement progress bar or spinner in header
- [x] Disable scan button while scan is running
- [x] Refresh folder/file data after scan completes
- [x] Verify: clicking scan shows progress, completes, and UI updates with new data

## Task 13: End-to-end verification
- [x] Run full scan from terminal: `python .library/scanner.py`
- [x] Verify library.db has correct folder and file counts
- [x] Start server: `python .library/server.py`
- [x] Verify Level 1 loads with folder cards and 3MF thumbnails
- [x] Verify clicking a folder shows Level 2 with file cards
- [x] Verify STL thumbnails render via Three.js on first view
- [x] Verify Open button launches file in default app
- [x] Verify Reveal button highlights file in Finder
- [x] Verify tag add/remove persists across page reload
- [x] Verify notes save persists across page reload
- [x] Verify cover selection changes the folder card thumbnail
- [x] Verify rescan from UI detects a new file added to disk
