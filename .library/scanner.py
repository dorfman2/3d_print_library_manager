"""
3D Print Library Scanner.

Walks the 3D Prints filesystem, indexes folders and files into SQLite,
extracts embedded 3MF preview thumbnails, and supports incremental rescan.
"""

import hashlib
import logging
import os
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Base directory: parent of .library/
BASE_DIR: Path = Path(__file__).resolve().parent.parent
LIBRARY_DIR: Path = BASE_DIR / ".library"
DB_PATH: Path = LIBRARY_DIR / "library.db"
THUMBNAILS_DIR: Path = LIBRARY_DIR / "thumbnails"

# Directories to skip during scanning
SKIP_DIRS: set[str] = {".library", ".kiro", ".git", "__pycache__"}

# Asset subdirectory names that get flattened into parent
ASSET_DIRS: set[str] = {"files", "images", "assets", "renders", "photos"}

# File formats recognized as printable (for leaf classification)
PRINTABLE_FORMATS: set[str] = {"stl", "3mf", "obj", "step", "stp", "f3d"}

# All supported formats (printable + display-only)
SUPPORTED_FORMATS: set[str] = PRINTABLE_FORMATS | {"bgcode", "pdf"}

# Formats to ignore entirely
IGNORED_EXTENSIONS: set[str] = {
    "ini", "txt", "md", "xml", "json", "cfg", "log", "zip", "7z", "rar",
}

# Regex to match category folder names (e.g. "0 - Calibration", "6 - Work Fixtures and Tooling")
CATEGORY_PATTERN: re.Pattern[str] = re.compile(r"^\d+ - .+")

SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS folders (
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

CREATE TABLE IF NOT EXISTS files (
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

CREATE TABLE IF NOT EXISTS tags (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  name  TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS folder_tags (
  folder_id  INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
  tag_id     INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (folder_id, tag_id)
);

CREATE TABLE IF NOT EXISTS scan_status (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  total       INTEGER DEFAULT 0,
  processed   INTEGER DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'running'
);

CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_id);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash);
CREATE INDEX IF NOT EXISTS idx_folders_category ON folders(category);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_folder_tags_folder ON folder_tags(folder_id);
CREATE INDEX IF NOT EXISTS idx_folder_tags_tag ON folder_tags(tag_id);
"""


def get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Open a connection to the library SQLite database.

    Uses Row factory for dict-like access on query results.
    Enables WAL mode and foreign keys.

    Parameters
    ----------
    db_path : Optional[Path]
        Path to the database file. Defaults to the standard DB_PATH.

    Returns
    -------
    sqlite3.Connection
        An open connection with row_factory set to sqlite3.Row.
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """
    Initialize the database schema.

    Creates all tables and indexes if they do not already exist.

    Parameters
    ----------
    db_path : Optional[Path]
        Path to the database file. Defaults to the standard DB_PATH.
    """
    conn = get_db(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        logger.info("Database schema initialized at %s", db_path or DB_PATH)
    finally:
        conn.close()


def clean_display_name(raw_name: str) -> str:
    """
    Clean a folder name for display purposes.

    Strips _model_files suffixes, UUIDs, leading part-number prefixes,
    and normalizes separators to spaces with title case.

    Parameters
    ----------
    raw_name : str
        The original folder name from the filesystem.

    Returns
    -------
    str
        A cleaned, human-readable display name.
    """
    name = raw_name
    # Strip _model_files or -model_files suffix
    name = re.sub(r"[_-]model_files$", "", name)
    # Strip trailing UUID
    name = re.sub(
        r"-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        "",
        name,
    )
    # Strip leading 5+ digit part number prefix
    name = re.sub(r"^\d{5,}-", "", name)
    # Normalize separators
    name = name.replace("-", " ").replace("_", " ")
    name = " ".join(name.split())
    return name.title() if name else raw_name


def get_file_format(path: Path) -> Optional[str]:
    """
    Get the normalized format extension for a file path.

    Parameters
    ----------
    path : Path
        Path to the file.

    Returns
    -------
    Optional[str]
        Lowercase extension without dot if it's a supported format, else None.
    """
    ext = path.suffix.lower().lstrip(".")
    if ext in SUPPORTED_FORMATS:
        return ext
    return None


def has_printable_files(directory: Path) -> bool:
    """
    Check if a directory directly contains any printable-format files.

    Does not recurse into subdirectories.

    Parameters
    ----------
    directory : Path
        The directory to check.

    Returns
    -------
    bool
        True if at least one printable-format file exists directly in the directory.
    """
    try:
        for entry in directory.iterdir():
            if entry.is_file():
                ext = entry.suffix.lower().lstrip(".")
                if ext in PRINTABLE_FORMATS:
                    return True
    except PermissionError:
        logger.warning("Permission denied accessing %s", directory)
    return False


def collect_files_for_folder(directory: Path) -> list[Path]:
    """
    Collect all supported files for a leaf folder, including asset subdirectories.

    Flattens files from asset subdirectories (files/, images/, etc.) into the
    parent folder's file list.

    Parameters
    ----------
    directory : Path
        The leaf folder path.

    Returns
    -------
    list[Path]
        List of file paths with supported formats.
    """
    result: list[Path] = []
    try:
        for entry in directory.iterdir():
            if entry.is_file():
                ext = entry.suffix.lower().lstrip(".")
                if ext in SUPPORTED_FORMATS:
                    result.append(entry)
            elif entry.is_dir() and entry.name.lower() in ASSET_DIRS:
                # Flatten asset subdirectory contents
                try:
                    for sub_entry in entry.iterdir():
                        if sub_entry.is_file():
                            ext = sub_entry.suffix.lower().lstrip(".")
                            if ext in SUPPORTED_FORMATS:
                                result.append(sub_entry)
                except PermissionError:
                    logger.warning("Permission denied accessing %s", entry)
    except PermissionError:
        logger.warning("Permission denied accessing %s", directory)
    return result


def discover_categories() -> list[tuple[str, Path]]:
    """
    Find all top-level category directories matching the numbered pattern.

    Scans BASE_DIR for directories matching ``^\\d+ - .+`` pattern.

    Returns
    -------
    list[tuple[str, Path]]
        List of (category_name, category_path) tuples sorted by name.
    """
    categories: list[tuple[str, Path]] = []
    try:
        for entry in sorted(BASE_DIR.iterdir()):
            if entry.is_dir() and CATEGORY_PATTERN.match(entry.name):
                categories.append((entry.name, entry))
    except PermissionError:
        logger.error("Permission denied accessing base directory %s", BASE_DIR)
    logger.info("Discovered %d categories", len(categories))
    return categories


def is_asset_dir(directory: Path) -> bool:
    """
    Check if a directory is an asset subdirectory that should be flattened.

    Parameters
    ----------
    directory : Path
        The directory to check.

    Returns
    -------
    bool
        True if the directory name matches an asset folder pattern.
    """
    return directory.name.lower() in ASSET_DIRS


def classify_folder(directory: Path) -> tuple[bool, bool]:
    """
    Classify a folder as leaf or container.

    A leaf folder has printable files directly (or in asset subdirs).
    A container folder has only subdirectories with printable content.

    Parameters
    ----------
    directory : Path
        The folder to classify.

    Returns
    -------
    tuple[bool, bool]
        (is_leaf, has_content) — is_leaf=True if it has printable files,
        has_content=True if it or its children have any printable files.
    """
    has_direct_printable = has_printable_files(directory)

    # Check asset subdirs for printable files too
    if not has_direct_printable:
        try:
            for entry in directory.iterdir():
                if entry.is_dir() and is_asset_dir(entry):
                    if has_printable_files(entry):
                        has_direct_printable = True
                        break
        except PermissionError:
            pass

    if has_direct_printable:
        return True, True

    # Check if any non-asset subdirectories exist with content
    has_child_content = False
    try:
        for entry in directory.iterdir():
            if entry.is_dir() and not is_asset_dir(entry):
                if entry.name.lower() not in SKIP_DIRS:
                    _, child_has_content = classify_folder(entry)
                    if child_has_content:
                        has_child_content = True
                        break
    except PermissionError:
        pass

    return False, has_child_content


def scan_folders(conn: sqlite3.Connection) -> dict[str, int]:
    """
    Walk the filesystem and populate the folders table.

    Discovers categories, walks each category tree, classifies folders
    as leaf or container, flattens asset directories, and creates synthetic
    folders for loose files in category roots.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict[str, int]
        Mapping of folder path (str) to folder DB id.
    """
    now = datetime.now(timezone.utc).isoformat()
    folder_ids: dict[str, int] = {}
    categories = discover_categories()

    for category_name, category_path in categories:
        # Check for loose printable files in category root
        loose_files = [
            f for f in category_path.iterdir()
            if f.is_file() and f.suffix.lower().lstrip(".") in SUPPORTED_FORMATS
        ]

        # Get non-skip, non-asset subdirectories
        subdirs: list[Path] = []
        try:
            for entry in sorted(category_path.iterdir()):
                if entry.is_dir():
                    if entry.name.lower() not in SKIP_DIRS and not is_asset_dir(entry):
                        subdirs.append(entry)
        except PermissionError:
            logger.warning("Permission denied: %s", category_path)
            continue

        # Create synthetic "(Loose Files)" folder if there are loose files
        if loose_files:
            synthetic_path = str(category_path / "(Loose Files)")
            cursor = conn.execute(
                """INSERT OR IGNORE INTO folders
                   (path, name, raw_name, category, parent_id, is_leaf,
                    is_synthetic, status, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, 1, 'ok', '', ?, ?)""",
                (
                    synthetic_path,
                    "(Loose Files)",
                    "(Loose Files)",
                    category_name,
                    None,
                    now,
                    now,
                ),
            )
            if cursor.lastrowid:
                folder_ids[synthetic_path] = cursor.lastrowid
            else:
                row = conn.execute(
                    "SELECT id FROM folders WHERE path = ?", (synthetic_path,)
                ).fetchone()
                if row:
                    folder_ids[synthetic_path] = row["id"]

        # Walk each subdirectory
        for subdir in subdirs:
            _walk_folder(conn, subdir, category_name, None, folder_ids, now)

    conn.commit()
    logger.info("Scanned %d folders total", len(folder_ids))
    return folder_ids


def _walk_folder(
    conn: sqlite3.Connection,
    directory: Path,
    category: str,
    parent_id: Optional[int],
    folder_ids: dict[str, int],
    now: str,
) -> None:
    """
    Recursively walk a folder and insert it into the database.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    directory : Path
        The current directory to process.
    category : str
        The category name this folder belongs to.
    parent_id : Optional[int]
        The DB id of the parent folder, or None for top-level.
    folder_ids : dict[str, int]
        Accumulator mapping folder paths to their DB ids.
    now : str
        ISO timestamp for created_at/updated_at.
    """
    is_leaf, has_content = classify_folder(directory)

    # Skip folders with zero printable content
    if not has_content:
        return

    raw_name = directory.name
    display_name = clean_display_name(raw_name)
    folder_path = str(directory)

    cursor = conn.execute(
        """INSERT OR IGNORE INTO folders
           (path, name, raw_name, category, parent_id, is_leaf,
            is_synthetic, status, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, 'ok', '', ?, ?)""",
        (
            folder_path,
            display_name,
            raw_name,
            category,
            parent_id,
            1 if is_leaf else 0,
            now,
            now,
        ),
    )

    if cursor.lastrowid:
        folder_id = cursor.lastrowid
    else:
        row = conn.execute(
            "SELECT id FROM folders WHERE path = ?", (folder_path,)
        ).fetchone()
        if row:
            folder_id = row["id"]
        else:
            logger.error("Failed to insert or find folder: %s", folder_path)
            return

    folder_ids[folder_path] = folder_id

    # If container, recurse into non-asset subdirectories
    if not is_leaf:
        try:
            for entry in sorted(directory.iterdir()):
                if entry.is_dir():
                    if entry.name.lower() not in SKIP_DIRS and not is_asset_dir(entry):
                        _walk_folder(conn, entry, category, folder_id, folder_ids, now)
        except PermissionError:
            logger.warning("Permission denied: %s", directory)


def hash_file(file_path: Path) -> str:
    """
    Compute SHA-256 hash of a file's content.

    Parameters
    ----------
    file_path : Path
        Path to the file to hash.

    Returns
    -------
    str
        Hex digest of the SHA-256 hash.
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def extract_3mf_preview(file_path: Path, content_hash: str) -> Optional[str]:
    """
    Attempt to extract an embedded preview PNG from a .3mf file.

    Checks for Metadata/thumbnail.png first, then Metadata/plate_1.png.
    Saves to thumbnails/<hash>.png if found.

    Parameters
    ----------
    file_path : Path
        Path to the .3mf file.
    content_hash : str
        SHA-256 hash of the file (used as thumbnail filename).

    Returns
    -------
    Optional[str]
        Relative thumbnail path (e.g., "<hash>.png") if extracted, else None.
    """
    thumbnail_candidates = ["Metadata/thumbnail.png", "Metadata/plate_1.png"]
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            for candidate in thumbnail_candidates:
                if candidate in names:
                    data = zf.read(candidate)
                    out_path = THUMBNAILS_DIR / f"{content_hash}.png"
                    out_path.write_bytes(data)
                    return f"{content_hash}.png"
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        logger.debug("Failed to extract 3MF preview from %s: %s", file_path, exc)
    return None


def scan_files(
    conn: sqlite3.Connection,
    folder_ids: dict[str, int],
) -> int:
    """
    Index files for all leaf folders, compute hashes, extract 3MF previews.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    folder_ids : dict[str, int]
        Mapping of folder path to DB id from scan_folders.

    Returns
    -------
    int
        Total number of files indexed.
    """
    now = datetime.now(timezone.utc).isoformat()
    total_files = 0

    for folder_path_str, folder_id in folder_ids.items():
        folder_path = Path(folder_path_str)

        # For synthetic folders, collect from the category root
        is_synthetic = "(Loose Files)" in folder_path_str
        if is_synthetic:
            actual_dir = folder_path.parent
            files = [
                f for f in actual_dir.iterdir()
                if f.is_file() and f.suffix.lower().lstrip(".") in SUPPORTED_FORMATS
            ]
        else:
            # Check if folder is a leaf
            row = conn.execute(
                "SELECT is_leaf FROM folders WHERE id = ?", (folder_id,)
            ).fetchone()
            if not row or not row["is_leaf"]:
                continue
            files = collect_files_for_folder(folder_path)

        for file_path in files:
            ext = file_path.suffix.lower().lstrip(".")
            try:
                stat = file_path.stat()
                size_bytes = stat.st_size
                modified_at = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()
            except OSError as exc:
                logger.warning("Cannot stat %s: %s", file_path, exc)
                continue

            # Check if already in DB with same hash
            existing = conn.execute(
                "SELECT id, content_hash FROM files WHERE path = ?",
                (str(file_path),),
            ).fetchone()

            content_hash = hash_file(file_path)

            if existing and existing["content_hash"] == content_hash:
                # Unchanged — mark as ok (in case previously missing)
                conn.execute(
                    "UPDATE files SET status = 'ok' WHERE id = ?",
                    (existing["id"],),
                )
                continue

            # Extract 3MF preview if applicable
            thumbnail: Optional[str] = None
            if ext == "3mf":
                thumbnail = extract_3mf_preview(file_path, content_hash)

            if existing:
                # File changed — update
                # Delete old thumbnail if hash changed
                old_hash = existing["content_hash"]
                if old_hash:
                    old_thumb_path = THUMBNAILS_DIR / f"{old_hash}.png"
                    if old_thumb_path.exists():
                        old_thumb_path.unlink()

                conn.execute(
                    """UPDATE files SET
                       filename = ?, format = ?, size_bytes = ?,
                       modified_at = ?, content_hash = ?, thumbnail = ?,
                       status = 'ok'
                       WHERE id = ?""",
                    (
                        file_path.name,
                        ext,
                        size_bytes,
                        modified_at,
                        content_hash,
                        thumbnail,
                        existing["id"],
                    ),
                )
            else:
                # New file — insert
                conn.execute(
                    """INSERT INTO files
                       (folder_id, path, filename, format, size_bytes,
                        modified_at, content_hash, thumbnail, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ok')""",
                    (
                        folder_id,
                        str(file_path),
                        file_path.name,
                        ext,
                        size_bytes,
                        modified_at,
                        content_hash,
                        thumbnail,
                    ),
                )

            total_files += 1

    conn.commit()
    logger.info("Indexed %d files (new or changed)", total_files)
    return total_files


def mark_missing_files(conn: sqlite3.Connection) -> int:
    """
    Mark files that no longer exist on disk as 'missing'.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    int
        Number of files marked as missing.
    """
    rows = conn.execute(
        "SELECT id, path FROM files WHERE status = 'ok'"
    ).fetchall()
    missing_count = 0
    for row in rows:
        if not Path(row["path"]).exists():
            conn.execute(
                "UPDATE files SET status = 'missing' WHERE id = ?", (row["id"],)
            )
            missing_count += 1
    if missing_count:
        conn.commit()
        logger.info("Marked %d files as missing", missing_count)
    return missing_count


def cleanup_orphaned_thumbnails(conn: sqlite3.Connection) -> int:
    """
    Remove thumbnail files that are no longer referenced by any file in the DB.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    int
        Number of orphaned thumbnail files deleted.
    """
    # Get all referenced thumbnail filenames
    rows = conn.execute(
        "SELECT DISTINCT thumbnail FROM files WHERE thumbnail IS NOT NULL"
    ).fetchall()
    referenced: set[str] = {row["thumbnail"] for row in rows}

    removed = 0
    for thumb_file in THUMBNAILS_DIR.iterdir():
        if thumb_file.name == ".gitkeep":
            continue
        if thumb_file.name not in referenced:
            thumb_file.unlink()
            removed += 1

    if removed:
        logger.info("Removed %d orphaned thumbnails", removed)
    return removed


def auto_tag_categories(conn: sqlite3.Connection) -> None:
    """
    Auto-create tags from category names and apply to folders on first scan.

    Only tags folders that don't already have a category tag.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    """
    categories = conn.execute(
        "SELECT DISTINCT category FROM folders"
    ).fetchall()

    for cat_row in categories:
        category = cat_row["category"]
        # Strip the number prefix to get tag name (e.g., "0 - Calibration" -> "Calibration")
        tag_name = re.sub(r"^\d+\s*-\s*", "", category).strip()
        if not tag_name:
            continue

        # Ensure tag exists
        conn.execute(
            "INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,)
        )
        tag_row = conn.execute(
            "SELECT id FROM tags WHERE name = ?", (tag_name,)
        ).fetchone()
        if not tag_row:
            continue
        tag_id = tag_row["id"]

        # Apply to all folders in this category that don't already have it
        folders = conn.execute(
            "SELECT id FROM folders WHERE category = ?", (category,)
        ).fetchall()
        for folder_row in folders:
            conn.execute(
                "INSERT OR IGNORE INTO folder_tags (folder_id, tag_id) VALUES (?, ?)",
                (folder_row["id"], tag_id),
            )

    conn.commit()
    logger.info("Auto-tagged folders with category names")


def update_scan_status(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    processed: Optional[int] = None,
    total: Optional[int] = None,
    status: Optional[str] = None,
    finished: bool = False,
) -> None:
    """
    Update the scan_status record for progress tracking.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    scan_id : int
        The scan_status row id.
    processed : Optional[int]
        Number of items processed so far.
    total : Optional[int]
        Total number of items to process.
    status : Optional[str]
        Status string ('running', 'complete', 'error').
    finished : bool
        If True, set finished_at timestamp.
    """
    updates: list[str] = []
    params: list[object] = []

    if processed is not None:
        updates.append("processed = ?")
        params.append(processed)
    if total is not None:
        updates.append("total = ?")
        params.append(total)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if finished:
        updates.append("finished_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())

    if updates:
        params.append(scan_id)
        conn.execute(
            f"UPDATE scan_status SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()


def run_full_scan() -> None:
    """
    Execute a complete scan: folders, files, tagging, and cleanup.

    This is the main entry point for both CLI and server-triggered scans.
    """
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

    conn = get_db()
    try:
        # Create scan status record
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO scan_status (started_at, status) VALUES (?, 'running')",
            (now,),
        )
        scan_id = cursor.lastrowid
        conn.commit()

        # Phase 1: Scan folders
        folder_ids = scan_folders(conn)
        update_scan_status(conn, scan_id, total=len(folder_ids))

        # Phase 2: Index files
        file_count = scan_files(conn, folder_ids)
        update_scan_status(conn, scan_id, processed=file_count)

        # Phase 3: Mark missing files
        mark_missing_files(conn)

        # Phase 4: Cleanup orphaned thumbnails
        cleanup_orphaned_thumbnails(conn)

        # Phase 5: Auto-tag with category names
        auto_tag_categories(conn)

        # Mark scan complete
        update_scan_status(
            conn, scan_id, status="complete", finished=True
        )
        logger.info(
            "Full scan complete. %d folders, %d files processed.",
            len(folder_ids),
            file_count,
        )
    except Exception:
        logger.exception("Scan failed")
        if scan_id:
            update_scan_status(conn, scan_id, status="error", finished=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_full_scan()
