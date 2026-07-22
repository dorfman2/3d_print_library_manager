---
inclusion: always
---

# System Patterns - Technical Architecture

## Important Security Patterns
- File open/reveal endpoints validate that the requested file_id exists in the DB before executing OS commands
- No user input is passed directly to shell commands; paths are looked up from DB by integer ID
- Server binds to `127.0.0.1` only (not `0.0.0.0`) — not network-accessible by default
- No authentication needed (local-only tool) but no destructive file operations exposed via API

## Learnings and Project Insights
- stl-thumb is Linux/Windows only (no macOS Homebrew formula, no ARM binary)
- trimesh + pyglet/pyrender require a windowed display session on macOS — unusable headless
- .3mf files in this library ARE valid ZIP archives — 100% parse with Python `zipfile`; 74% (267/359) contain embedded preview PNGs at `Metadata/thumbnail.png` or `Metadata/plate_1.png`
- Earlier test failure was a shell quoting issue piping paths with special chars into Python inline; script-file approach works perfectly
- Three.js STLLoader/3MFLoader/OBJLoader works reliably in all browsers with WebGL — best cross-platform rendering path for files without embedded previews
- Scanner extracts 3MF previews server-side (stdlib zipfile) covering majority of 3MF files instantly
- Printables downloads often unzip into `files/` + `images/` subfolders — must be flattened into parent
- Folder names contain special chars: `=`, `+`, Unicode dashes, parentheses — full paths must be quoted/escaped
- SHA-256 hashing ~700 files of mixed sizes takes <30 seconds on SSD

## System Architecture
```
User Browser (localhost:5050)
    │
    ├─ GET /static/*           → SPA shell (index.html, app.js, style.css)
    ├─ GET /api/folders        → JSON list of folders with metadata
    ├─ GET /api/folders/:id    → Single folder + files + tags
    ├─ GET /thumbnails/*.png   → Cached thumbnail images
    ├─ POST /api/thumbnails    → Client posts rendered PNG for caching
    ├─ GET /api/open/:file_id  → Triggers OS open command server-side
    └─ POST /api/scan          → Triggers incremental rescan
    │
Flask Server (server.py)
    │
    └─ SQLite (library.db)
        ├─ folders (path, name, category, is_leaf, cover, tags, notes)
        ├─ files (path, folder_id, format, size, hash, thumbnail)
        ├─ tags + folder_tags (many-to-many)
        └─ scan_status (progress tracking)
```

## Code Structure
- `.library/scanner.py` — standalone script; walks filesystem, populates DB, extracts 3MF previews
- `.library/server.py` — Flask app; imports scanner for rescan trigger; serves all endpoints
- `.library/static/index.html` — SPA shell with sidebar + main grid container
- `.library/static/app.js` — all UI logic: fetch, render, navigate, Three.js thumbnail generation
- `.library/static/style.css` — CSS Grid layout, responsive, dark/light neutral theme
- `.library/static/icons/` — SVG format icons for STEP, F3D, bgcode, PDF, generic folder

## Design Patterns in Use
- **Two-level browse** — folder grid (Level 1) drills into file grid (Level 2); breadcrumb for depth
- **Container/Leaf** — folders are either containers (show subfolders) or leaves (show files)
- **Lazy thumbnail rendering** — browser renders on first view; cached PNG served on subsequent loads
- **Incremental scan** — SHA-256 hash comparison skips unchanged files; missing files get status badge
- **Synthetic folders** — loose files in category roots get an auto-created "(Loose Files)" card
- **Asset folder flattening** — `files/`, `images/` subfolders are not separate folders in the DB

## Tool Usage Patterns

- **`taskUpdate` EPERM workaround**: On Windows, the `taskUpdate` tool intermittently fails with `EPERM: operation not permitted, rename ... .meta.json` when Kiro's file watcher holds a read lock on the meta.json during the atomic rename. This is a timing race, not a permissions issue. **Workaround**: when `taskUpdate` fails with EPERM, fall back to editing `tasks.md` directly via `str_replace` (change `- [~]` or `- [ ]` to `- [x]` for the affected task). This bypasses the meta.json entirely and is reliable. Retry `taskUpdate` once before falling back — the lock is usually brief.

- **Preferred task execution method — kiro-cli**: ALWAYS prefer running spec tasks via the CLI agent rather than IDE-based execution. When tasks are ready to run, present the user with the exact command:
  ```
  kiro-cli chat --agent spec-executor --trust-all-tools "Execute all tasks in .kiro/specs/<spec-name>/tasks.md"
  ```
  Replace `<spec-name>` with the actual feature name. The `--trust-all-tools` flag enables autonomous execution without per-tool approval prompts. This approach is ~2.4x cheaper and ~7.6x faster than IDE Chat execution. The agent definition lives at `.kiro/agents/spec-executor.json`.
