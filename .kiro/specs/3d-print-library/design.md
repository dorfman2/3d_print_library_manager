# Design — 3D Print Library

## Architecture

```
3D Prints/
├── .library/
│   ├── library.db           ← SQLite (stdlib sqlite3)
│   ├── thumbnails/          ← Cached PNGs keyed by SHA-256 content hash
│   ├── scanner.py           ← Filesystem walker + indexer + 3MF preview extractor
│   ├── server.py            ← Flask app (API + static + thumbnail serving)
│   ├── requirements.txt     ← flask>=3.0
│   └── static/
│       ├── index.html       ← SPA shell
│       ├── app.js           ← UI logic + Three.js thumbnail renderer
│       ├── style.css        ← Grid layout + sidebar + responsive
│       └── icons/           ← SVG format icons
│           ├── step.svg
│           ├── f3d.svg
│           ├── bgcode.svg
│           ├── pdf.svg
│           └── folder.svg
```

## Database Schema

```sql
CREATE TABLE folders (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  path            TEXT UNIQUE NOT NULL,
  name            TEXT NOT NULL,
  raw_name        TEXT NOT NULL,
  category        TEXT NOT NULL,
  parent_id       INTEGER REFERENCES folders(id),
  is_leaf         INTEGER NOT NULL DEFAULT 1,
  is_synthetic    INTEGER NOT NULL DEFAULT 0,
  cover_file_id   INTEGER,
  cover_image     TEXT,
  status          TEXT NOT NULL DEFAULT 'ok',
  notes           TEXT DEFAULT '',
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE TABLE files (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  folder_id    INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
  path         TEXT UNIQUE NOT NULL,
  filename     TEXT NOT NULL,
  format       TEXT NOT NULL,
  size_bytes   INTEGER NOT NULL,
  modified_at  TEXT NOT NULL,
  content_hash TEXT,
  thumbnail    TEXT,
  status       TEXT NOT NULL DEFAULT 'ok'
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
  status      TEXT NOT NULL DEFAULT 'running'
);

CREATE INDEX idx_files_folder ON files(folder_id);
CREATE INDEX idx_files_hash ON files(content_hash);
CREATE INDEX idx_folders_category ON folders(category);
CREATE INDEX idx_folders_parent ON folders(parent_id);
CREATE INDEX idx_folder_tags_folder ON folder_tags(folder_id);
CREATE INDEX idx_folder_tags_tag ON folder_tags(tag_id);
```

## API Design

### Folders
- `GET /api/folders` — list; params: `?category=`, `?tag=`, `?q=`, `?parent_id=`, `?format=`
- `GET /api/folders/<id>` — single folder with files + tags
- `PATCH /api/folders/<id>/cover` — body: `{"file_id": int}` or `{"image_path": str}`
- `PATCH /api/folders/<id>/notes` — body: `{"notes": str}`

### Files
- `GET /api/folders/<id>/files` — files in a folder
- `GET /api/files/<id>/raw` — serve raw file for Three.js (send_file)

### Tags
- `GET /api/tags` — all tags with counts
- `POST /api/folders/<id>/tags` — body: `{"name": str}`
- `DELETE /api/folders/<id>/tags/<name>` — remove tag

### Categories
- `GET /api/categories` — list with counts

### Thumbnails
- `GET /thumbnails/<hash>.png` — serve cached thumbnail
- `POST /api/thumbnails` — body: `{"file_id": int, "image": "base64..."}` — save rendered PNG

### File Actions
- `POST /api/open/<file_id>` — OS open
- `POST /api/reveal/<file_id>` — OS reveal

### Scan
- `POST /api/scan` — trigger scan
- `GET /api/scan/status` — progress

## Scanner Design

### Walk Algorithm
1. Identify top-level category folders (match `^\d+ - .+`)
2. For each category, walk subdirectories recursively
3. Classify each folder:
   - Has printable files directly → leaf (is_leaf=1)
   - Has only subdirectories (no printable files) → container (is_leaf=0)
   - Named `files`/`images`/`assets`/`renders`/`photos` (case-insensitive) → flatten into parent
4. Category roots with loose printable files → create synthetic folder (is_synthetic=1)
5. Folders with zero printable files after all rules → skip

### File Processing
1. For each printable file: compute SHA-256, record metadata
2. For .3mf files: attempt zipfile extraction of `Metadata/thumbnail.png` or `Metadata/plate_1.png`
3. Store extracted preview at `thumbnails/<hash>.png`, set `files.thumbnail` field

### Incremental Rescan
- Compare on-disk files against DB by path
- If hash unchanged → skip
- If hash changed → update row, delete old thumbnail, re-extract if 3mf
- If file missing → set status='missing'
- If new file → insert
- Post-scan: delete orphaned thumbnails from disk

### Display Name Cleaning
```python
import re

def clean_display_name(raw_name: str) -> str:
    name = raw_name
    name = re.sub(r'[_-]model_files$', '', name)
    name = re.sub(r'-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', '', name)
    name = re.sub(r'^\d{5,}-', '', name)
    name = name.replace('-', ' ').replace('_', ' ')
    name = ' '.join(name.split())
    return name.title() if name else raw_name
```

## Frontend Design

### Three.js Thumbnail Renderer
- Offscreen `WebGLRenderer` (256×256, antialias, light gray background)
- Camera auto-framed to model bounding box
- Ambient light (0.6) + 2 directional lights for depth
- Render queue: max 3 concurrent, IntersectionObserver for viewport-only
- On render complete: `canvas.toDataURL('image/png')` → POST to `/api/thumbnails`
- Failed renders: show format icon, don't retry (server stores `__failed__`)

### UI State Management
- Single global state object in app.js
- URL hash for navigation: `#/` (Level 1), `#/folder/<id>` (Level 2)
- Back button / breadcrumb updates hash
- Filters stored in state, applied client-side on cached folder list

### Responsive Grid
- CSS Grid: `grid-template-columns: repeat(auto-fill, minmax(180px, 1fr))`
- Sidebar: fixed 220px on desktop, collapsible on narrow viewports
- Cards: square aspect ratio thumbnail + text below

## Edge Case Handling

Per EDGE_CASES.md — key behaviors:
- `thumbnail = '__failed__'` prevents retry loops
- WebGL check on load; graceful degradation to icons
- Integer file_id in all API URLs (no filename encoding issues)
- Post-scan orphan cleanup for thumbnails/
- Container/leaf classification: PDF does NOT count as printable for leaf determination
- Printable formats for classification: stl, 3mf, obj, step, stp, f3d
