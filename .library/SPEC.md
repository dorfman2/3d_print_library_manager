# 3D Print Library — Spec v2

## Overview

A lightweight, browser-based visual library for a local 3D print file collection.
No cloud, no account, no Docker required. Runs as a small local Python/Flask server
and opens in any browser on Mac or Windows.

Thumbnails are rendered **client-side via Three.js** (WebGL) on first view, then
cached to the server as PNGs. No server-side rendering dependencies.

---

## Goals

- Two-level visual browse: folder grid → individual file grid (unlimited depth)
- Tag-based filtering and search across both levels
- One-click local file links (open in OS default app / reveal in Finder or Explorer)
- Fast: scan indexes files + extracts 3MF previews; STL renders happen in browser on demand
- Cross-platform: identical experience on macOS and Windows via browser
- Simple to run: `python server.py` → open browser

---

## Non-Goals

- Cloud sync or remote access
- Slicer integration (out of scope for v1)
- User accounts or multi-user support
- Editing, moving, or deleting files on disk

---

## File Support

| Format            | Thumbnail Source      | Notes                                 |
|-------------------|-----------------------|---------------------------------------|
| `.stl`            | Three.js (browser)    | STLLoader renders on first view       |
| `.3mf` (w/ embed) | Server-side extract  | Preview PNG extracted from ZIP at scan |
| `.3mf` (no embed) | Three.js (browser)   | 3MFLoader fallback render             |
| `.obj`            | Three.js (browser)    | OBJLoader renders on first view       |
| `.step` / `.stp`  | Static icon           | Generic CAD icon                      |
| `.f3d`            | Static icon           | Generic Fusion 360 icon               |
| `.bgcode`         | Static icon           | Generic sliced-file icon              |
| `.pdf`            | Static icon           | PDF icon, link only                   |

---

## Architecture

```
3D Prints/
├── .library/
│   ├── SPEC.md              ← this file
│   ├── EDGE_CASES.md        ← edge case documentation
│   ├── library.db           ← SQLite database
│   ├── thumbnails/          ← cached PNG thumbnails (by content hash)
│   ├── scanner.py           ← folder walk, DB population, 3MF preview extraction
│   ├── server.py            ← Flask server + REST API
│   ├── requirements.txt     ← Python deps (flask)
│   └── static/
│       ├── index.html       ← SPA shell
│       ├── app.js           ← UI logic + Three.js rendering
│       ├── style.css        ← Layout and theme
│       └── icons/           ← SVG format icons
│           ├── step.svg
│           ├── f3d.svg
│           ├── bgcode.svg
│           ├── pdf.svg
│           └── folder.svg
```

---

## Database Schema (SQLite)

```sql
CREATE TABLE folders (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  path            TEXT UNIQUE NOT NULL,    -- absolute path on disk
  name            TEXT NOT NULL,           -- cleaned display name
  raw_name        TEXT NOT NULL,           -- actual folder name on disk
  category        TEXT NOT NULL,           -- top-level parent folder name
  parent_id       INTEGER,                 -- FK → folders.id for nested containers
  is_leaf         INTEGER NOT NULL DEFAULT 1,  -- 1=leaf (has files), 0=container (has subfolders)
  is_synthetic    INTEGER NOT NULL DEFAULT 0,  -- 1=auto-created "(Loose Files)"
  cover_file_id   INTEGER,                 -- FK → files.id; null = auto (first 3MF then STL)
  cover_image     TEXT,                    -- path to user-selected image (alternative to render)
  status          TEXT NOT NULL DEFAULT 'ok',  -- 'ok' | 'missing'
  notes           TEXT DEFAULT '',
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE TABLE files (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  folder_id    INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
  path         TEXT UNIQUE NOT NULL,       -- absolute path on disk
  filename     TEXT NOT NULL,
  format       TEXT NOT NULL,              -- stl / 3mf / obj / step / f3d / bgcode / pdf
  size_bytes   INTEGER NOT NULL,
  modified_at  TEXT NOT NULL,
  content_hash TEXT,                       -- SHA-256; thumbnail cache key + change detection
  thumbnail    TEXT,                       -- relative path under thumbnails/ or null
  status       TEXT NOT NULL DEFAULT 'ok'  -- 'ok' | 'missing'
);

CREATE TABLE tags (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  name  TEXT UNIQUE NOT NULL
);

CREATE TABLE folder_tags (
  folder_id  INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
  tag_id     INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (folder_id, tag_id)
);

CREATE TABLE scan_status (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  total       INTEGER DEFAULT 0,
  processed   INTEGER DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'running'  -- 'running' | 'complete' | 'error'
);

-- Indexes for performance
CREATE INDEX idx_files_folder ON files(folder_id);
CREATE INDEX idx_files_hash ON files(content_hash);
CREATE INDEX idx_folders_category ON folders(category);
CREATE INDEX idx_folders_parent ON folders(parent_id);
CREATE INDEX idx_folder_tags_folder ON folder_tags(folder_id);
CREATE INDEX idx_folder_tags_tag ON folder_tags(tag_id);
```

---

## API Endpoints (Flask @ localhost:5050)

### Folders
```
GET  /api/folders                     List folders (filterable)
     ?category=<name>                 Filter by category
     ?tag=<name>                      Filter by tag
     ?q=<search>                      Search folder names
     ?parent_id=<id>                  Children of a container folder (null=top-level)
     ?format=<ext>                    Folders containing this format

GET  /api/folders/<id>                Single folder with files, tags, cover info
PATCH /api/folders/<id>/cover         Set cover  { "file_id": 42 } or { "image_path": "..." }
PATCH /api/folders/<id>/notes         Update notes  { "notes": "..." }
```

### Files
```
GET  /api/folders/<id>/files          Files inside a folder
GET  /api/files/<id>/raw              Serve the raw 3D file (for Three.js to load)
```

### Tags
```
GET  /api/tags                        All tags with usage counts
POST /api/folders/<id>/tags           Add tag  { "name": "gridfinity" }
DELETE /api/folders/<id>/tags/<name>   Remove tag from folder
```

### Categories
```
GET  /api/categories                  List of categories with folder counts
```

### Thumbnails
```
GET  /thumbnails/<hash>.png           Serve cached thumbnail
POST /api/thumbnails                  Client uploads rendered thumbnail
     { "file_id": <int>, "image": "<base64 PNG>" }
```

### File Actions
```
POST /api/open/<file_id>              OS-open the file (Mac: open, Win: start)
POST /api/reveal/<file_id>            Reveal in Finder / Explorer
```

### Scan
```
POST /api/scan                        Trigger incremental rescan
GET  /api/scan/status                 { "running": bool, "processed": int, "total": int }
```

---

## Thumbnail Strategy (Three.js Client-Side)

### Flow

```
Browser requests file card
  → Check: does /thumbnails/<hash>.png exist? (API field `thumbnail` is non-null)
  → YES: show cached PNG (3MF embedded previews are pre-cached at scan time)
  → NO and format is STL/3MF/OBJ:
      1. Fetch raw file via /api/files/<id>/raw
      2. Load into Three.js scene (STLLoader / 3MFLoader / OBJLoader)
      3. Render to offscreen canvas (256×256)
      4. Convert to PNG via canvas.toDataURL()
      5. POST base64 PNG to /api/thumbnails { file_id, image }
      6. Server saves to thumbnails/<hash>.png, updates DB
      7. Display immediately in the card
  → NO and format is STEP/F3D/bgcode/PDF:
      → Show static format icon (no rendering attempt)
```

### Rendering setup (Three.js)

```javascript
// Offscreen renderer (reused across all thumbnail renders)
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setSize(256, 256);
renderer.setClearColor(0xf0f0f0, 1);

// Camera positioned to frame the model's bounding box
function frameModel(mesh) {
  const box = new THREE.Box3().setFromObject(mesh);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, maxDim * 10);
  camera.position.set(center.x + maxDim, center.y + maxDim * 0.5, center.z + maxDim);
  camera.lookAt(center);
  return camera;
}

// Lighting: ambient + two directional for depth
const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.3);
```

### 3MF File Handling

3MF files are ZIP archives. In this library:
- **100% (359/359)** are valid ZIP files
- **74% (267/359)** contain embedded preview PNGs (`Metadata/thumbnail.png` or `Metadata/plate_1.png`)

The scanner extracts these embedded previews at scan time — no rendering needed for the
majority of 3MF files. The remaining 26% without previews get rendered client-side via
Three.js `3MFLoader` on first browse.

```python
import zipfile
from pathlib import Path

PREVIEW_MEMBERS = [
    "Metadata/thumbnail.png",
    "Metadata/plate_1.png",
]

def extract_3mf_preview(path_3mf: str, output_path: str) -> bool:
    """Extract embedded preview from 3MF ZIP. Returns True if found."""
    try:
        with zipfile.ZipFile(path_3mf, 'r') as z:
            for candidate in PREVIEW_MEMBERS:
                if candidate in z.namelist():
                    data = z.read(candidate)
                    Path(output_path).write_bytes(data)
                    return True
    except zipfile.BadZipFile:
        pass
    return False
```

### Cover thumbnail priority
1. `cover_file_id` set by user → that file's cached thumbnail
2. `cover_image` set by user → image file from `images/` subfolder
3. First `.3mf` file with an extracted preview
4. First file that has a cached thumbnail (3MF > STL > OBJ, alphabetical within)
5. No renderable files → static folder icon

---

## UI — Two-Level Browse

### Level 1 — Folder Grid (default view)

```
┌──────────────────────────────────────────────────────────────┐
│  🗂 3D Print Library          [🔍 search...]      [↺ Scan]   │
├───────────────┬──────────────────────────────────────────────┤
│               │  [active filters: × tools × gridfinity]      │
│  CATEGORIES   │                                              │
│  ● All  (87)  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐       │
│  0-Calib  (1) │  │  🖼   │ │  🖼   │ │  🖼   │ │  🖼   │       │
│  1-Machines(9)│  └──────┘ └──────┘ └──────┘ └──────┘       │
│  2-Office (5) │  Fan Lock  Linear   Prusa    Build           │
│  3-Tools (18) │  3 files   3 files  Tool Box Plate           │
│  4-Elec   (4) │  STL·3MF   3MF·STP  42 files STL            │
│  ...          │                                              │
│               │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐       │
│  TAGS         │  │  🖼   │ │  🖼   │ │  🖼   │ │  🖼   │       │
│  gridfinity(6)│  └──────┘ └──────┘ └──────┘ └──────┘       │
│  fixture  (12)│                                              │
│  esd       (3)│                                              │
│  [+ new tag]  │                                              │
└───────────────┴──────────────────────────────────────────────┘
```

**Folder card:**
- Cover thumbnail (lazy-rendered or 3MF preview)
- Folder display name
- File count badge
- Format badges (unique formats present)
- Tag chips (max 3, then "+N")
- Container folders show a subfolder icon instead of file count

### Level 2 — File Grid (click a folder card)

For **leaf** folders: shows file cards.
For **container** folders: shows subfolder cards (same layout as Level 1).

Breadcrumb: `All › 1 - Machines › Prusa Tool Box › V2 Prusa Tools Box`

```
┌──────────────────────────────────────────────────────────────┐
│  ← Back    1 - Machines › Fan Lock Assembly    [↺ Scan]      │
├───────────────┬──────────────────────────────────────────────┤
│               │  Tags: [machine] [+add]                      │
│  FORMATS      │  Notes: ________________________  [Save]     │
│  All (4)      │                                              │
│  3MF (2)      │  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  BGCODE (2)   │  │    🖼     │  │    🖼     │  │   📄     │   │
│               │  └──────────┘  └──────────┘  └──────────┘   │
│               │  Assembly.3mf   Assembly_1    ...bgcode      │
│               │  3MF · 2.1 MB   3MF · 2.3 MB  BGCODE        │
│               │  [Open][Reveal] [Open][Reveal] [Open][Reveal]│
│               │  [★ Cover]                                   │
└───────────────┴──────────────────────────────────────────────┘
```

**File card:**
- Thumbnail (Three.js rendered or format icon)
- Filename (truncated with tooltip)
- Format badge + file size
- **Open** — POST `/api/open/<file_id>`
- **Reveal** — POST `/api/reveal/<file_id>`
- **★ Cover** — PATCH `/api/folders/<id>/cover { file_id }`

---

## Search & Filter

- **Search bar** (Level 1): filters folder display names + tag names (client-side)
- **Category sidebar**: click to filter; active category highlighted
- **Tag sidebar**: click to add tag filter; multiple tags = AND logic
- **Active filters**: shown as removable chips above the grid
- **Level 2 sidebar**: format filter (STL / 3MF / STEP / etc.) within the folder

---

## File Open / Reveal — Cross-Platform

```python
import sys
import subprocess
import logging

logger = logging.getLogger(__name__)

def open_file(path: str) -> bool:
    """Open file in OS default application."""
    logger.info("Opening file: %s", path)
    if sys.platform == "darwin":
        return subprocess.run(["open", path]).returncode == 0
    elif sys.platform == "win32":
        return subprocess.run(["cmd", "/c", "start", "", path]).returncode == 0
    return False

def reveal_file(path: str) -> bool:
    """Reveal file in Finder (macOS) or Explorer (Windows)."""
    logger.info("Revealing file: %s", path)
    if sys.platform == "darwin":
        return subprocess.run(["open", "-R", path]).returncode == 0
    elif sys.platform == "win32":
        return subprocess.run(["explorer", f"/select,{path}"]).returncode == 0
    return False
```

---

## Scanner Behavior

### What it does
1. Walks the `3D Prints/` folder tree (skips `.library/`, `.kiro/`)
2. Identifies top-level categories (numbered folders)
3. For each non-category folder:
   - Determines leaf vs. container
   - Flattens `files/` and `images/` asset subfolders into parent
   - Skips folders with zero printable files
   - Applies display name cleaning rules
   - Creates synthetic "(Loose Files)" folder for orphaned files in category roots
4. For each printable file:
   - Records path, filename, format, size, modified date
   - Computes SHA-256 content hash
   - For `.3mf`: attempts to extract embedded preview PNG → saves to `thumbnails/<hash>.png`
5. Creates initial tags from category names
6. Writes progress to `scan_status` table

### Incremental rescan rules

| Condition | Action |
|-----------|--------|
| New file on disk | INSERT file row; extract 3MF preview if applicable |
| File hash unchanged | Skip |
| File hash changed | UPDATE row; re-extract preview; delete old cached thumbnail |
| File missing from disk | Set `status = 'missing'` |
| New folder on disk | INSERT folder row; auto-tag with category |
| Folder missing from disk | Set `status = 'missing'` |

### Never auto-deleted
- User tags, notes, cover selections
- Missing file/folder rows (user manually cleans up)

### Orphaned thumbnail cleanup
After scan completes, delete any `.png` in `thumbnails/` whose filename (hash) doesn't
match any file's `content_hash` or `thumbnail` field.

---

## Running

### First-time setup (both platforms)

```bash
pip install flask

cd "3D Prints/.library"
python scanner.py        # Index files + extract 3MF previews (~30-60 sec)
python server.py         # Start server → http://localhost:5050
```

### Daily use

```bash
cd "3D Prints/.library"
python server.py
```

Rescan from UI (↺ button) or terminal (`python scanner.py`).
STL/OBJ thumbnails render in the browser the first time you browse a folder.
3MF thumbnails are mostly pre-cached from embedded previews after the scan.

### Dependencies

**requirements.txt:**
```
flask>=3.0
```

That's it. Three.js is loaded from CDN in the browser.
3MF preview extraction uses Python stdlib `zipfile` — no extra package.

---

## Performance Targets

| Operation                          | Target                    |
|------------------------------------|---------------------------|
| Initial scan (index + 3MF preview extract) | < 60 sec for ~700 files  |
| Incremental rescan (no changes)    | < 3 seconds               |
| Page load (Level 1, all folders)   | < 1 second                |
| First thumbnail render (browser)   | < 500ms per model         |
| Subsequent thumbnail (cached)      | < 50ms (static PNG)       |
| Tag filter / search                | < 100ms (client-side)     |

---

## v1 Implementation Tasks

- [ ] `scanner.py` — folder walk, DB creation, file indexing, content hashing, 3MF preview extraction
- [ ] `server.py` — Flask app, all API endpoints, static serving, open/reveal, thumbnail cache
- [ ] `static/index.html` — SPA shell, CDN Three.js, layout structure
- [ ] `static/style.css` — grid layout, sidebar, responsive, neutral theme
- [ ] `static/app.js` — Level 1 (folder grid, category/tag sidebars, search, filters)
- [ ] `static/app.js` — Level 2 (file grid, breadcrumb, format filter, Open/Reveal/Cover)
- [ ] `static/app.js` — Three.js thumbnail renderer (STL/OBJ/3MF) + server cache POST
- [ ] `static/icons/` — SVG format icons (step, f3d, bgcode, pdf, folder)
- [ ] Scan progress UI (polling + spinner)
- [ ] Cross-platform open/reveal validation

## v2 Ideas

- Interactive 3D viewer on hover or click (full orbit/zoom, not just static render)
- Bulk tag editor (multi-select folders, apply/remove tags)
- Print queue / wishlist collection
- Export library index to CSV / JSON
- AI auto-tagging via local LLM or OpenRouter
- Keyboard navigation (arrows, Enter, Esc)
- Dark mode toggle
- Drag-and-drop tag assignment
