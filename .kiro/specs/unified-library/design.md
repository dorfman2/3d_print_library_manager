# Design — Unified 3D Print Library

## Overview

Merge the Sorter into the existing Viewer's Flask app. The sorter becomes a
background-thread scheduler controlled from the web UI. Both halves share one
config file, one library folder, and one SQLite database.

## Architecture

```
.library/
├── scanner.py         ← EXISTING: indexes library, extracts 3MF previews
├── server.py          ← EXTENDED: adds sync API + scheduler + config endpoints
├── sorter.py          ← NEW: cross-platform port of sort_downloads.py (5 phases)
├── config.py          ← NEW: shared config load/save (JSON)
├── categories.py      ← NEW: category list + keyword scoring + name cleanup
├── config.json        ← NEW: runtime config (gitignored)
├── categories.json    ← NEW: editable categories (gitignored, seeded on first run)
├── categories.default.json ← NEW: bundled default category list
├── library.db         ← EXISTING: folders, files, tags, scan_status
├── thumbnails/        ← EXISTING: cached PNGs
└── static/
    ├── index.html     ← EXTENDED: add Sync panel link
    ├── app.js         ← EXISTING viewer logic
    ├── sync.html      ← NEW: sync control panel page
    ├── sync.js        ← NEW: sync panel logic
    ├── style.css      ← EXTENDED: sync panel styles
    └── ...
```

## Component Responsibilities

### sorter.py (new — ported from sort_downloads.py)

Pure, cross-platform functions. No tkinter, no registry, no pystray.

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class SyncPlanItem:
    """A single planned move in a sync operation."""
    source_path: Path
    raw_name: str
    cleaned_name: str
    category: str
    dest_path: Path
    is_duplicate: bool
    item_type: str  # 'dir' | 'file'

@dataclass
class SyncResult:
    """Outcome of a sync run."""
    zips_extracted: list[str]
    zips_deleted: list[str]
    moved: list[SyncPlanItem]
    skipped: list[SyncPlanItem]
    library_zips_cleaned: list[str]
    dry_run: bool

def run_sync(source: Path, library: Path, categories: list[dict],
             dry_run: bool = True) -> SyncResult:
    """Execute the five-phase sync. Returns a SyncResult."""
    ...

def preprocess_source_zips(source: Path, dry_run: bool) -> tuple[list, list]: ...
def build_library_index(library: Path) -> set[str]: ...
def collect_candidates(source: Path, library_index: set, categories: list,
                       library: Path) -> list[SyncPlanItem]: ...
def execute_moves(plan: list[SyncPlanItem], dry_run: bool) -> tuple[list, list]: ...
def clean_library_zips(library: Path, dry_run: bool) -> list[str]: ...
```

### categories.py (new)

```python
def clean_name(raw_name: str) -> str:
    """Apply the 8-step name-cleanup rules. Returns cleaned display name."""
    ...

def categorize(name: str, categories: list[dict]) -> str:
    """Score name against each category's keywords. Return best category folder name."""
    ...

# Small words downcased in non-first position
SMALL_WORDS = {"and","for","of","the","in","or","to","at","a","an",
               "but","by","as","nor","on"}

# Noise tokens stripped during cleanup
NOISE_TOKENS = {"stl","3mf","obj","step","gcode","final","remix","remixed",
                "remixof","print","printed","printable","updated","fixed",
                "free","paid","model_files","files"}
```

### config.py (new)

```python
DEFAULT_CONFIG = {
    "source_folder": None,      # None → resolve to OS Downloads
    "library_folder": None,     # None → parent of .library/
    "sync_interval_minutes": 60,
    "sync_enabled": False,
    "server_port": 5050,
}

def load_config() -> dict: ...
def save_config(cfg: dict) -> None: ...
def resolve_downloads_folder() -> Path:
    """Cross-platform Downloads: ~/Downloads on both macOS and Windows."""
    ...
```

## Category Reconciliation — Merged Starter Library

The two projects had different default category lists (work-focused vs hobby-focused).
The unified app ships a **merged** `categories.default.json` (19 categories +
Uncategorized) that combines both:

```
0 - Calibration            8 - Models and Display     16 - Work Fixtures and Tooling
1 - Machines               9 - Tabletop               17 - Work Spare Parts
2 - Home and Household     10 - RC Flight             18 - Mounting
3 - Office                 11 - MultiBoard            Uncategorized
4 - Tools and Organization 12 - MMU
5 - Repairs and Replacements 13 - NERF
6 - Electronics            14 - Legos
7 - Gifts and Toys         15 - Cosplay
```

**Decision:** Categories are fully user-configurable, stored in `categories.json`.
The merged list is only a *starter*; each user tunes their own.

### First-run setup wizard (`/setup`)

On first run (no `config.json` / `categories.json`), show a setup wizard with
three paths:

| Choice | Categories | Folders on disk |
|--------|-----------|-----------------|
| **Starter library** | seed all 19 merged categories | create category folders |
| **Use existing library** | derive from on-disk folder names | none created/renamed |
| **Custom / blank** | only `Uncategorized` | none |

The wizard also collects the library location (default `~/3D Prints`) and the
source/watch folder (default `~/Downloads`). Result is written to `config.json` +
`categories.json`. The wizard is skippable; the Sync panel can configure the same
settings later.

### Keyword scoring caveat (work categories)

Work categories (16–18) share generic keywords with hobby categories (`jig`,
`fixture`, `bracket`, `mount`). Since ties break to the lowest category number,
work items could misroute to Tools (4) or Repairs (5). Mitigation: work categories
use *distinctive* keywords (`jam nut`, `preforming`, `work holding`, `molex`,
`training board`, `din rail`) that win on score. Users tune as needed. This is a
documented tuning tradeoff, not a bug.

- The Viewer derives categories from folder names on disk — it stays agnostic.
- The Sorter reads `categories.json` for keyword→folder mapping.
- The UI category editor writes `categories.json`; renaming a category moves the
  on-disk folder AND migrates viewer metadata (see EDGE_CASES EC-1).

## API Additions (server.py)

```
GET  /sync                          Serve sync.html panel
GET  /api/config                    Return current config
PATCH /api/config                   Update config (source, library, interval, etc.)

GET  /api/categories/config         Full category list with keywords
PUT  /api/categories/config         Replace category list (add/rename/delete/keywords)

POST /api/sync/preview              Run dry-run, return SyncResult as JSON
POST /api/sync/run                  Execute sync (background thread), then auto-rescan
GET  /api/sync/status               { state, last_run, next_run, interval, enabled }
POST /api/sync/schedule             Enable/disable scheduler, set interval
```

## Scheduler Design

A background `threading.Timer` (or a simple daemon thread with sleep) inside the
Flask process. No OS-level scheduler needed.

```python
class SyncScheduler:
    """Runs sync on an interval in a background thread."""
    def start(self, interval_minutes: int) -> None: ...
    def stop(self) -> None: ...
    def run_once(self, dry_run: bool = False) -> SyncResult: ...
    @property
    def status(self) -> dict: ...
```

On sync completion (execute mode), the scheduler calls
`scanner.run_full_scan()` so new files appear in the browser immediately.

## UI Design — Sync Panel (`/sync`)

```
┌──────────────────────────────────────────────────────────┐
│  ← Library      Sync Settings                             │
├──────────────────────────────────────────────────────────┤
│  Source folder:  [ ~/Downloads              ] [Browse]    │
│  Library folder: [ ~/3D Prints              ] [Browse]    │
│                                                            │
│  Schedule:  ( ) Off   (•) Every [ 60 ] minutes            │
│  Status: Idle    Last run: 2:14 PM    Next: 3:14 PM       │
│                                                            │
│  [ Preview (Dry Run) ]   [ Run Sync Now ]                 │
├──────────────────────────────────────────────────────────┤
│  Preview / Log                                             │
│  ┌──────────────────────────────────────────────────┐    │
│  │ [DIR]  case-for-rak-wisblock-model_files          │    │
│  │        → Case for Rak Wisblock  [6 - Electronics] │    │
│  │ [SKIP] 3DBenchy  (already in library)             │    │
│  │ [ZIP]  extracted source_files.zip                 │    │
│  └──────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────┤
│  Categories                              [+ Add Category] │
│  0 - Calibration    [keywords: calibration, benchy…] [✎]  │
│  1 - Machines       [keywords: ender, prusa, bambu…] [✎]  │
│  ...                                                       │
└──────────────────────────────────────────────────────────┘
```

Add a small "Sync" link in the main header next to "Generate".

## Cross-Platform Notes

| Feature | macOS | Windows | Approach |
|---------|-------|---------|----------|
| Downloads folder | `~/Downloads` | `~/Downloads` | `Path.home() / "Downloads"` |
| Scheduler | daemon thread | daemon thread | In-process, no OS scheduler |
| Autostart | (optional) launchd | (optional) registry | Documented, not core |
| Open/Reveal | `open` / `open -R` | `start` / `explorer` | Existing viewer code |

## Name Cleanup — Ported Rules (from Sorter spec)

1. Strip trailing noise before replacing separators
2. Strip noise tokens (multi-pass until stable): version numbers, file-type tags,
   `model_files`/`files`, `final`, `remix*`, `by <author>`, `print*`, `updated`,
   `fixed`, `free`, `paid`
3. Replace `_` and `-` with spaces
4. Collapse multiple spaces, trim
5. Title-case fully-lowercase words
6. Preserve internal-uppercase (`3DBenchy`, `RPi`) and all-caps (`NERF`, `MMU`)
7. Downcase small words in non-first position
8. Empty result → return original name

## Testing Strategy (real filesystem, no mocks)

- `tests/test_name_cleanup.py` — table-driven cases from the Sorter spec examples
- `tests/test_categorize.py` — keyword scoring assigns correct category
- `tests/test_sorter_phases.py` — each phase on tmp_path with real files/ZIPs
- `tests/test_sync_integration.py` — full 5-phase dry-run + execute on tmp_path
- `tests/test_config.py` — load/save/seed round-trip
- `tests/test_auto_reindex.py` — sync execute triggers scanner, new files indexed

## Migration Path

1. Port sorter logic into `sorter.py` + `categories.py` (cross-platform)
2. Add `config.py` and seed `categories.default.json`
3. Extend `server.py` with sync/config/category endpoints + scheduler
4. Build `sync.html` + `sync.js` panel
5. Wire auto-rescan after execute sync
6. Add integration tests
7. (Optional, later) keep the Windows tray app as a thin wrapper that calls the
   same `sorter.py` — no logic duplication
