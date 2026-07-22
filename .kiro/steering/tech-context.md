---
inclusion: always
---

# Tech Context - Target Environment and Stack

## Core Requirements
- Cross-platform: macOS and Windows (identical browser experience)
- No Docker dependency
- No cloud / no accounts
- Single command to start (`python server.py`)
- Port 5050 for local server

## Core Dependencies
- Python 3.9+ (system Python on macOS; any 3.x on Windows)
- Flask 3.x (HTTP server + REST API)
- SQLite 3 (via Python stdlib `sqlite3` — no external DB)
- Three.js (client-side 3D rendering for STL/OBJ/3MF thumbnails)

## Technologies, Libraries, and Protocols
- **Backend**: Python 3.9, Flask, SQLite3 (stdlib), hashlib (stdlib), zipfile (stdlib for 3MF preview extraction)
- **Frontend**: Vanilla HTML/CSS/JS, Three.js (CDN), STLLoader, 3MFLoader, OBJLoader
- **Thumbnail strategy**: Hybrid — scanner extracts 3MF embedded previews server-side (74% coverage); browser renders STL/OBJ/remaining 3MF via Three.js → canvas → POST to server cache
- **3MF handling**: Valid ZIP archives; 74% contain `Metadata/thumbnail.png` or `Metadata/plate_1.png`; remaining 26% rendered by Three.js 3MFLoader (which handles ZIP internally via JSZip)
- **File operations**: `subprocess.run(["open", path])` (macOS), `subprocess.run(["cmd", "/c", "start", "", path])` (Windows)
- **Database**: Single SQLite file at `.library/library.db`
- **Hashing**: SHA-256 of file content for thumbnail cache keys and change detection

## Component Relationships and Dependencies
- `scanner.py` → reads filesystem, writes to `library.db`, extracts 3MF previews to `thumbnails/`
- `server.py` → reads `library.db`, serves `static/`, serves `thumbnails/`, handles API requests
- `sorter.py` → 5-phase sync: ZIP preprocessing, index build, categorize, move, clean
- `config.py` → shared config for viewer + sorter (source folder, library folder, scheduler)
- `categories.py` → 8-step name cleanup + keyword-based categorization + load/save categories
- `static/app.js` → fetches from Flask API, renders Three.js thumbnails, POSTs rendered PNGs back to server
- `static/sync.js` → sync panel UI: config, preview, run, schedule, category editor
- `library.db` → single source of truth for folders, files, tags, scan state
- `thumbnails/` → cache dir; keyed by SHA-256 of file content; cleaned on each scan

## Key Technical Decisions
- **No server-side STL/OBJ rendering** — stl-thumb lacks macOS binary; pyrender/trimesh require display. Browser has GPU via WebGL.
- **Server-side 3MF preview extraction** — stdlib `zipfile` extracts embedded PNGs from 74% of .3mf files at scan time. Fast, no dependencies.
- **Three.js client-side rendering for the rest** — STL, OBJ, and 3MF-without-preview rendered on first view, cached to server. Subsequent loads use cached PNG.
- **`__failed__` sentinel** — if Three.js can't parse a file, store `thumbnail = '__failed__'` to prevent infinite retry loops.
- **Render queue (max 3 concurrent)** — prevents browser memory/GPU exhaustion on folders with 20+ files.
- **IntersectionObserver** — only render thumbnails for cards currently in viewport.
- **SQLite over JSON** — enables filtering, tag queries, and incremental updates without loading entire dataset into memory.
- **Flask over FastAPI** — simpler stdlib-compatible setup; no async needed for a local tool.
- **Vanilla JS over React/Vue** — minimal dependencies; no build step; loads instantly.
- **Content hash as cache key** — same physical file across folders shares one thumbnail render.
- **Tags on folders not files** — folders are the unit of organization; individual files are variants.
- **Scanner has minimal rendering responsibility** — only 3MF preview extraction (stdlib zipfile). All GPU rendering is in the browser.
