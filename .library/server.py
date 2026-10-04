"""
3D Print Library Flask Server.

Serves the SPA frontend, REST API for folders/files/tags/categories,
thumbnail cache, and triggers for file open/reveal and scanner rescan.
Binds to 127.0.0.1:5050 only.
"""

import logging
import os
import platform
import subprocess
import threading
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request, send_file, send_from_directory

from scanner import (
    DB_PATH,
    LIBRARY_DIR,
    THUMBNAILS_DIR,
    get_db,
    init_db,
    run_full_scan,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    static_folder=str(LIBRARY_DIR / "static"),
    static_url_path="/static",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def dict_from_row(row) -> dict:
    """
    Convert a sqlite3.Row to a plain dict.

    Parameters
    ----------
    row : sqlite3.Row
        A row returned from a query with row_factory=sqlite3.Row.

    Returns
    -------
    dict
        Dictionary with column names as keys.
    """
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# SPA Shell
# ---------------------------------------------------------------------------


def _is_first_run() -> bool:
    """
    Detect first run: no config.json AND no categories.json.

    Returns
    -------
    bool
        True if neither config nor categories file exists.
    """
    from config import CONFIG_PATH
    from categories import CATEGORIES_PATH
    return not CONFIG_PATH.is_file() and not CATEGORIES_PATH.is_file()


@app.route("/")
def index():
    """Serve SPA or redirect to setup wizard on first run."""
    if _is_first_run():
        from flask import redirect
        return redirect("/setup")
    return send_from_directory(app.static_folder, "index.html")


@app.route("/setup")
def setup_page():
    """Serve the first-run setup wizard."""
    return send_from_directory(app.static_folder, "setup.html")


@app.route("/api/setup/complete", methods=["POST"])
def api_setup_complete():
    """
    Complete the setup wizard.

    Expects JSON body: {"mode": "starter" | "existing" | "blank"}

    Actions by mode:
      - starter: seed all merged categories, create folders on disk
      - existing: derive categories from on-disk folder names
      - blank: only Uncategorized

    Writes config.json and categories.json at completion.
    """
    from config import load_config, save_config
    from categories import (
        load_default_categories, save_categories, CATEGORIES_PATH
    )

    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "blank")

    cfg = load_config()
    library_root = Path(cfg.get("library_folder", ""))

    if mode == "starter":
        # Seed all merged categories and create folders
        categories = load_default_categories()
        if library_root.is_dir():
            for cat in categories:
                cat_name = cat.get("name", "")
                if cat_name and cat_name != "Uncategorized":
                    cat_dir = library_root / cat_name
                    cat_dir.mkdir(exist_ok=True)
            # Also create Uncategorized
            (library_root / "Uncategorized").mkdir(exist_ok=True)
        save_categories(categories)

    elif mode == "existing":
        # Derive categories from on-disk folder names
        import re
        categories = []
        if library_root.is_dir():
            for item in sorted(library_root.iterdir()):
                if not item.is_dir():
                    continue
                if item.name.startswith("."):
                    continue
                # Check if it matches the "N - Name" pattern
                if re.match(r"^\d+\s*-\s*.+", item.name):
                    categories.append({
                        "name": item.name,
                        "keywords": [],
                    })
                elif item.name not in ("Uncategorized",):
                    # Non-numbered folder — include as-is
                    categories.append({
                        "name": item.name,
                        "keywords": [],
                    })
        # Always include Uncategorized
        if not any(c["name"] == "Uncategorized" for c in categories):
            categories.append({"name": "Uncategorized", "keywords": []})
        save_categories(categories)

    else:  # blank
        categories = [{"name": "Uncategorized", "keywords": []}]
        save_categories(categories)

    # Ensure config is saved (marks first-run as complete)
    save_config(cfg)

    return jsonify({"status": "ok", "mode": mode, "categories_count": len(categories)})


@app.route("/generate")
def generate_page():
    """Serve the batch thumbnail generation page."""
    return send_from_directory(app.static_folder, "generate.html")


@app.route("/sync")
def sync_page():
    """Serve the sync control panel page."""
    return send_from_directory(app.static_folder, "sync.html")


# ---------------------------------------------------------------------------
# Thumbnail serving
# ---------------------------------------------------------------------------


@app.route("/thumbnails/<path:filename>")
def serve_thumbnail(filename: str):
    """
    Serve a cached thumbnail image.

    Parameters
    ----------
    filename : str
        The thumbnail filename (e.g., "<hash>.png").
    """
    return send_from_directory(str(THUMBNAILS_DIR), filename)


# ---------------------------------------------------------------------------
# API: Categories
# ---------------------------------------------------------------------------


@app.route("/api/categories")
def api_categories():
    """
    Return list of categories with folder counts.

    Returns
    -------
    JSON array of objects: {name, count}
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT category as name, COUNT(*) as count
               FROM folders
               GROUP BY category
               ORDER BY category"""
        ).fetchall()
        return jsonify([dict_from_row(r) for r in rows])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Folders
# ---------------------------------------------------------------------------


@app.route("/api/folders")
def api_folders():
    """
    Return list of folders with optional filtering.

    Query params:
        category - filter by category name
        tag - filter by tag name
        q - search folder names and tags
        parent_id - filter by parent folder id
        format - filter folders containing files of this format
    """
    conn = get_db()
    try:
        category = request.args.get("category")
        tag = request.args.get("tag")
        q = request.args.get("q")
        parent_id = request.args.get("parent_id")
        fmt = request.args.get("format")

        query = """
            SELECT DISTINCT f.id, f.path, f.name, f.raw_name, f.category,
                   f.parent_id, f.is_leaf, f.is_synthetic, f.cover_file_id,
                   f.cover_image, f.status, f.notes, f.created_at, f.updated_at
            FROM folders f
        """
        joins: list[str] = []
        conditions: list[str] = []
        params: list[object] = []

        if tag:
            joins.append(
                "JOIN folder_tags ft ON ft.folder_id = f.id "
                "JOIN tags t ON t.id = ft.tag_id"
            )
            conditions.append("t.name = ?")
            params.append(tag)

        if fmt:
            joins.append(
                "JOIN files fi ON fi.folder_id = f.id"
            )
            conditions.append("fi.format = ?")
            params.append(fmt)

        if category:
            conditions.append("f.category = ?")
            params.append(category)

        if parent_id:
            if parent_id == "null":
                conditions.append("f.parent_id IS NULL")
            else:
                conditions.append("f.parent_id = ?")
                params.append(int(parent_id))

        if q:
            conditions.append(
                "(f.name LIKE ? OR EXISTS "
                "(SELECT 1 FROM folder_tags ft2 JOIN tags t2 ON t2.id = ft2.tag_id "
                "WHERE ft2.folder_id = f.id AND t2.name LIKE ?))"
            )
            params.append(f"%{q}%")
            params.append(f"%{q}%")

        if joins:
            query += " " + " ".join(joins)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY f.category, f.name"

        rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            folder = dict_from_row(row)
            # Add file count
            count_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM files WHERE folder_id = ?",
                (folder["id"],),
            ).fetchone()
            folder["file_count"] = count_row["cnt"] if count_row else 0

            # Add tags
            tag_rows = conn.execute(
                """SELECT t.name FROM tags t
                   JOIN folder_tags ft ON ft.tag_id = t.id
                   WHERE ft.folder_id = ?""",
                (folder["id"],),
            ).fetchall()
            folder["tags"] = [r["name"] for r in tag_rows]

            # Add format badges
            format_rows = conn.execute(
                """SELECT DISTINCT format FROM files
                   WHERE folder_id = ?""",
                (folder["id"],),
            ).fetchall()
            folder["formats"] = [r["format"] for r in format_rows]

            # Add cover thumbnail path
            if folder["cover_file_id"]:
                cover_row = conn.execute(
                    "SELECT thumbnail FROM files WHERE id = ?",
                    (folder["cover_file_id"],),
                ).fetchone()
                folder["cover_thumbnail"] = (
                    cover_row["thumbnail"] if cover_row else None
                )
            else:
                # Default: first file with a thumbnail
                first_thumb = conn.execute(
                    """SELECT thumbnail FROM files
                       WHERE folder_id = ? AND thumbnail IS NOT NULL
                       AND thumbnail != '__failed__'
                       LIMIT 1""",
                    (folder["id"],),
                ).fetchone()
                folder["cover_thumbnail"] = (
                    first_thumb["thumbnail"] if first_thumb else None
                )

            result.append(folder)
        return jsonify(result)
    finally:
        conn.close()


@app.route("/api/folders/<int:folder_id>")
def api_folder_detail(folder_id: int):
    """
    Return a single folder with its files and tags.

    Parameters
    ----------
    folder_id : int
        The folder database ID.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Folder not found"}), 404

        folder = dict_from_row(row)

        # Files
        file_rows = conn.execute(
            """SELECT * FROM files WHERE folder_id = ?
               ORDER BY filename""",
            (folder_id,),
        ).fetchall()
        folder["files"] = [dict_from_row(f) for f in file_rows]

        # Tags
        tag_rows = conn.execute(
            """SELECT t.name FROM tags t
               JOIN folder_tags ft ON ft.tag_id = t.id
               WHERE ft.folder_id = ?""",
            (folder_id,),
        ).fetchall()
        folder["tags"] = [r["name"] for r in tag_rows]

        # Child folders (if container)
        if not folder["is_leaf"]:
            child_rows = conn.execute(
                "SELECT * FROM folders WHERE parent_id = ? ORDER BY name",
                (folder_id,),
            ).fetchall()
            folder["children"] = [dict_from_row(c) for c in child_rows]

        return jsonify(folder)
    finally:
        conn.close()


@app.route("/api/folders/<int:folder_id>/files")
def api_folder_files(folder_id: int):
    """
    Return files in a folder.

    Parameters
    ----------
    folder_id : int
        The folder database ID.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Folder not found"}), 404

        file_rows = conn.execute(
            """SELECT * FROM files WHERE folder_id = ?
               ORDER BY filename""",
            (folder_id,),
        ).fetchall()
        return jsonify([dict_from_row(f) for f in file_rows])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Tags
# ---------------------------------------------------------------------------


@app.route("/api/tags")
def api_tags():
    """Return all tags with usage counts."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT t.name, COUNT(ft.folder_id) as count
               FROM tags t
               LEFT JOIN folder_tags ft ON ft.tag_id = t.id
               GROUP BY t.id
               ORDER BY t.name"""
        ).fetchall()
        return jsonify([dict_from_row(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/folders/<int:folder_id>/tags", methods=["POST"])
def api_add_tag(folder_id: int):
    """
    Add a tag to a folder.

    Body: {"name": "tag_name"}
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Folder not found"}), 404

        data = request.get_json()
        if not data or "name" not in data:
            return jsonify({"error": "Missing 'name' field"}), 400

        tag_name = data["name"].strip()
        if not tag_name:
            return jsonify({"error": "Tag name cannot be empty"}), 400

        # Ensure tag exists
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
        tag_row = conn.execute(
            "SELECT id FROM tags WHERE name = ?", (tag_name,)
        ).fetchone()

        # Link to folder
        conn.execute(
            "INSERT OR IGNORE INTO folder_tags (folder_id, tag_id) VALUES (?, ?)",
            (folder_id, tag_row["id"]),
        )
        conn.commit()
        return jsonify({"status": "ok", "tag": tag_name}), 201
    finally:
        conn.close()


@app.route("/api/folders/<int:folder_id>/tags/<name>", methods=["DELETE"])
def api_remove_tag(folder_id: int, name: str):
    """
    Remove a tag from a folder.

    Parameters
    ----------
    folder_id : int
        The folder database ID.
    name : str
        The tag name to remove.
    """
    conn = get_db()
    try:
        tag_row = conn.execute(
            "SELECT id FROM tags WHERE name = ?", (name,)
        ).fetchone()
        if not tag_row:
            return jsonify({"error": "Tag not found"}), 404

        conn.execute(
            "DELETE FROM folder_tags WHERE folder_id = ? AND tag_id = ?",
            (folder_id, tag_row["id"]),
        )
        conn.commit()
        return jsonify({"status": "ok"})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Cover and Notes
# ---------------------------------------------------------------------------


@app.route("/api/folders/<int:folder_id>/cover", methods=["PATCH"])
def api_set_cover(folder_id: int):
    """
    Set the cover image for a folder.

    Body: {"file_id": int} or {"image_path": str}
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Folder not found"}), 404

        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing request body"}), 400

        if "file_id" in data:
            conn.execute(
                "UPDATE folders SET cover_file_id = ?, updated_at = datetime('now') WHERE id = ?",
                (data["file_id"], folder_id),
            )
        elif "image_path" in data:
            conn.execute(
                "UPDATE folders SET cover_image = ?, updated_at = datetime('now') WHERE id = ?",
                (data["image_path"], folder_id),
            )
        else:
            return jsonify({"error": "Provide 'file_id' or 'image_path'"}), 400

        conn.commit()
        return jsonify({"status": "ok"})
    finally:
        conn.close()


@app.route("/api/folders/<int:folder_id>/notes", methods=["PATCH"])
def api_set_notes(folder_id: int):
    """
    Update notes for a folder.

    Body: {"notes": str}
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Folder not found"}), 404

        data = request.get_json()
        if data is None or "notes" not in data:
            return jsonify({"error": "Missing 'notes' field"}), 400

        conn.execute(
            "UPDATE folders SET notes = ?, updated_at = datetime('now') WHERE id = ?",
            (data["notes"], folder_id),
        )
        conn.commit()
        return jsonify({"status": "ok"})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Raw file serving
# ---------------------------------------------------------------------------


@app.route("/api/files/<int:file_id>/raw")
def api_file_raw(file_id: int):
    """
    Serve a raw model file for Three.js rendering.

    Validates file_id exists in DB before serving.

    Parameters
    ----------
    file_id : int
        The file database ID.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT path, filename FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "File not found"}), 404

        file_path = Path(row["path"])
        if not file_path.exists():
            return jsonify({"error": "File not found on disk"}), 404

        return send_file(str(file_path), download_name=row["filename"])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Open / Reveal
# ---------------------------------------------------------------------------


@app.route("/api/open/<int:file_id>", methods=["POST"])
def api_open_file(file_id: int):
    """
    Open a file with the OS default application.

    Validates file_id exists in DB before executing OS command.
    Uses 'open' on macOS and 'cmd /c start' on Windows.

    Parameters
    ----------
    file_id : int
        The file database ID.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT path FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "File not found"}), 404

        file_path = Path(row["path"])
        if not file_path.exists():
            return jsonify({"error": "File not found on disk"}), 404

        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.run(["open", str(file_path)], check=True)
            elif system == "Windows":
                # os.startfile launches in the default app without a console
                # flash or shell-quoting issues. Windows-only, so reference it
                # inside this branch.
                os.startfile(str(file_path))  # type: ignore[attr-defined]  # noqa: E501
            else:
                subprocess.run(["xdg-open", str(file_path)], check=True)
        except (subprocess.CalledProcessError, OSError) as exc:
            logger.error("Failed to open file %s: %s", file_path, exc)
            return jsonify({"error": "Failed to open file"}), 500

        return jsonify({"status": "ok"})
    finally:
        conn.close()


@app.route("/api/reveal/<int:file_id>", methods=["POST"])
def api_reveal_file(file_id: int):
    """
    Reveal a file in Finder (macOS) or Explorer (Windows).

    Validates file_id exists in DB before executing OS command.

    Parameters
    ----------
    file_id : int
        The file database ID.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT path FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "File not found"}), 404

        file_path = Path(row["path"])
        if not file_path.exists():
            return jsonify({"error": "File not found on disk"}), 404

        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.run(["open", "-R", str(file_path)], check=True)
            elif system == "Windows":
                # explorer.exe returns exit code 1 even on success, so do NOT
                # use check=True. The selector and path must be a single arg:
                # "/select,<path>".
                subprocess.run(["explorer", f"/select,{file_path}"])
            else:
                # Linux: open parent directory
                subprocess.run(["xdg-open", str(file_path.parent)], check=True)
        except (subprocess.CalledProcessError, OSError) as exc:
            logger.error("Failed to reveal file %s: %s", file_path, exc)
            return jsonify({"error": "Failed to reveal file"}), 500

        return jsonify({"status": "ok"})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Thumbnails upload
# ---------------------------------------------------------------------------


@app.route("/api/thumbnails", methods=["POST"])
def api_upload_thumbnail():
    """
    Accept a rendered thumbnail from the browser and cache it.

    Body: {"file_id": int, "image": "base64 PNG data"}
    Saves to thumbnails/<content_hash>.png and updates files.thumbnail.
    """
    import base64

    conn = get_db()
    try:
        data = request.get_json()
        if not data or "file_id" not in data or "image" not in data:
            return jsonify({"error": "Missing 'file_id' or 'image'"}), 400

        file_id = data["file_id"]
        row = conn.execute(
            "SELECT id, content_hash, thumbnail FROM files WHERE id = ?",
            (file_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "File not found"}), 404

        content_hash = row["content_hash"]
        if not content_hash:
            return jsonify({"error": "File has no content hash"}), 400

        # Handle __failed__ sentinel
        image_data = data["image"]
        if image_data == "__failed__":
            conn.execute(
                "UPDATE files SET thumbnail = '__failed__' WHERE id = ?",
                (file_id,),
            )
            conn.commit()
            return jsonify({"status": "ok", "thumbnail": "__failed__"}), 201

        # Decode base64 image (strip data URI prefix if present)
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]

        try:
            png_bytes = base64.b64decode(image_data)
        except Exception:
            return jsonify({"error": "Invalid base64 image data"}), 400

        # Save to thumbnails directory
        thumb_filename = f"{content_hash}.png"
        thumb_path = THUMBNAILS_DIR / thumb_filename
        thumb_path.write_bytes(png_bytes)

        # Update DB
        conn.execute(
            "UPDATE files SET thumbnail = ? WHERE id = ?",
            (thumb_filename, file_id),
        )
        conn.commit()

        return jsonify({"status": "ok", "thumbnail": thumb_filename}), 201
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Scan
# ---------------------------------------------------------------------------

_scan_lock = threading.Lock()


@app.route("/api/scan", methods=["POST"])
def api_trigger_scan():
    """
    Trigger a full scan in a background thread.

    Returns 409 if a scan is already running.
    """
    if not _scan_lock.acquire(blocking=False):
        return jsonify({"error": "Scan already running"}), 409

    def _run_scan():
        try:
            run_full_scan()
        finally:
            _scan_lock.release()

    thread = threading.Thread(target=_run_scan, daemon=True)
    thread.start()
    return jsonify({"status": "started"}), 202


@app.route("/api/scan/status")
def api_scan_status():
    """Return the current/latest scan progress."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM scan_status ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return jsonify({"status": "idle"})
        return jsonify(dict_from_row(row))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Pending Thumbnails (batch generation)
# ---------------------------------------------------------------------------


@app.route("/api/files/pending-thumbnails")
def api_pending_thumbnails():
    """
    Return all renderable files that lack a cached thumbnail.

    Used by the batch thumbnail generation page to iterate through
    every STL/3MF/OBJ file that has not yet been rendered.

    Returns
    -------
    JSON object with 'files' list and 'total'/'pending' counts.
    """
    conn = get_db()
    try:
        renderable_formats = ("stl", "3mf", "obj")
        placeholders = ",".join("?" for _ in renderable_formats)

        total_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM files WHERE format IN ({placeholders})",
            renderable_formats,
        ).fetchone()
        total = total_row["cnt"] if total_row else 0

        rows = conn.execute(
            f"""SELECT id, filename, format, content_hash, size_bytes
                FROM files
                WHERE format IN ({placeholders})
                AND (thumbnail IS NULL OR thumbnail = '')
                ORDER BY size_bytes ASC""",
            renderable_formats,
        ).fetchall()

        pending = [dict_from_row(r) for r in rows]

        return jsonify({
            "total_renderable": total,
            "pending": len(pending),
            "already_done": total - len(pending),
            "files": pending,
        })
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Config and Categories (Unified Library)
# ---------------------------------------------------------------------------


@app.route("/api/config", methods=["GET"])
def api_get_config():
    """
    Return the current application configuration.

    Returns
    -------
    JSON object with all config keys.
    """
    from config import load_config
    return jsonify(load_config())


@app.route("/api/config", methods=["PATCH"])
def api_patch_config():
    """
    Update application configuration.

    Accepts a partial JSON object. Only keys present in DEFAULT_CONFIG
    are stored. Validates that source != library and they are not nested.

    Returns
    -------
    JSON object with updated config on success, 400 on validation error.
    """
    from config import DEFAULT_CONFIG, load_config, save_config

    data = request.get_json(silent=True) or {}
    cfg = load_config()

    # Merge provided keys
    for key in DEFAULT_CONFIG:
        if key in data:
            cfg[key] = data[key]

    # Validate source != library (EC-4)
    src = Path(cfg.get("source_folder", "")).resolve()
    lib = Path(cfg.get("library_folder", "")).resolve()

    if src == lib:
        return jsonify({"error": "Source and Library folders cannot be the same"}), 400
    if str(src).startswith(str(lib) + "/") or str(src).startswith(str(lib) + "\\"):
        return jsonify({"error": "Source folder cannot be inside the Library"}), 400
    if str(lib).startswith(str(src) + "/") or str(lib).startswith(str(src) + "\\"):
        return jsonify({"error": "Library folder cannot be inside the Source"}), 400

    save_config(cfg)
    return jsonify(cfg)


@app.route("/api/categories/config", methods=["GET"])
def api_get_categories_config():
    """
    Return the full category configuration with keywords.

    Returns
    -------
    JSON object with 'categories' list.
    """
    from categories import load_categories, load_default_categories

    cats = load_categories()
    if not cats:
        # If no user config exists, return empty (wizard hasn't run yet)
        return jsonify({"categories": [], "has_config": False})
    return jsonify({"categories": cats, "has_config": True})


@app.route("/api/categories/config", methods=["PUT"])
def api_put_categories_config():
    """
    Replace the full category configuration.

    Handles renames by moving the on-disk folder if it exists.
    Handles deletes by moving children to Uncategorized.

    Expects JSON body: {"categories": [...]}

    Returns
    -------
    JSON object with saved categories on success.
    """
    from categories import load_categories, save_categories

    data = request.get_json(silent=True) or {}
    new_cats: list = data.get("categories", [])

    if not new_cats:
        return jsonify({"error": "categories list is required"}), 400

    # Load existing categories to detect renames/deletes
    old_cats = load_categories()
    old_names: set = {c["name"] for c in old_cats}
    new_names: set = {c["name"] for c in new_cats}

    # Determine library root for folder operations
    from config import load_config
    cfg = load_config()
    library_root = Path(cfg.get("library_folder", ""))

    # Handle renames: if a category name changed but index is same, move folder
    for i, (old, new) in enumerate(
        zip(old_cats[:len(new_cats)], new_cats[:len(old_cats)])
    ):
        old_name = old.get("name", "")
        new_name = new.get("name", "")
        if old_name and new_name and old_name != new_name:
            old_folder = library_root / old_name
            new_folder = library_root / new_name
            if old_folder.is_dir() and not new_folder.exists():
                try:
                    old_folder.rename(new_folder)
                    logger.info(
                        "Renamed category folder: %s -> %s", old_name, new_name
                    )
                except OSError as exc:
                    logger.error(
                        "Failed to rename category folder %s -> %s: %s",
                        old_name, new_name, exc,
                    )

    # Handle deletes: categories in old but not in new
    deleted_names = old_names - new_names - {"Uncategorized"}
    if deleted_names and library_root.is_dir():
        # Ensure Uncategorized exists
        uncat_dir = library_root / "Uncategorized"
        uncat_dir.mkdir(exist_ok=True)

        for dname in deleted_names:
            del_folder = library_root / dname
            if del_folder.is_dir():
                # Move children to Uncategorized
                for child in del_folder.iterdir():
                    dest = uncat_dir / child.name
                    if not dest.exists():
                        try:
                            child.rename(dest)
                        except OSError as exc:
                            logger.error(
                                "Failed to move %s to Uncategorized: %s",
                                child, exc,
                            )
                # Remove empty dir
                try:
                    del_folder.rmdir()
                except OSError:
                    pass  # Not empty — leave it

    save_categories(new_cats)
    return jsonify({"categories": new_cats, "has_config": True})


# ---------------------------------------------------------------------------
# Sync Scheduler
# ---------------------------------------------------------------------------


class SyncScheduler:
    """
    Runs sync on an interval in a background daemon thread.

    Non-reentrant: if a sync is already running when the timer fires,
    the tick is skipped. After a successful execute sync, triggers
    scanner.run_full_scan() for auto-reindex.
    """

    def __init__(self) -> None:
        """Initialize the scheduler in a stopped state."""
        self._timer: Optional[threading.Timer] = None
        self._running: bool = False
        self._enabled: bool = False
        self._interval_minutes: int = 60
        self._last_run: Optional[str] = None
        self._next_run: Optional[str] = None
        self._state: str = "idle"  # idle | running | scheduled
        self._lock = threading.Lock()
        self._sync_lock = threading.Lock()

    @property
    def status(self) -> dict:
        """
        Return the current scheduler status.

        Returns
        -------
        dict
            Status dictionary with state, last_run, next_run, interval, enabled.
        """
        return {
            "state": self._state,
            "last_run": self._last_run,
            "next_run": self._next_run,
            "interval_minutes": self._interval_minutes,
            "enabled": self._enabled,
        }

    def start(self, interval_minutes: int) -> None:
        """
        Start the scheduler with the given interval.

        Parameters
        ----------
        interval_minutes : int
            Minutes between sync runs (1–1440).
        """
        self._interval_minutes = max(1, min(1440, interval_minutes))
        self._enabled = True
        self._schedule_next()
        logger.info("Scheduler started: every %d minutes", self._interval_minutes)

    def stop(self) -> None:
        """Stop the scheduler and cancel pending timer."""
        self._enabled = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._state = "idle"
        self._next_run = None
        logger.info("Scheduler stopped")

    def run_once(self, dry_run: bool = False) -> Optional[dict]:
        """
        Run sync once (non-reentrant).

        Acquires the shared scan lock to prevent sync/scan collision (EC-12).
        Snapshots the category list at sync start (EC-14).

        Parameters
        ----------
        dry_run : bool
            If True, preview mode only.

        Returns
        -------
        Optional[dict]
            SyncResult serialized as dict, or None if busy.
        """
        # Use shared lock (EC-12): prevents sync while scan runs and vice versa
        if not _scan_lock.acquire(blocking=False):
            logger.info("Sync skipped: scan or sync already running (EC-12/EC-13)")
            return None

        try:
            self._state = "running"

            from categories import load_categories
            from config import load_config
            from sorter import run_sync

            cfg = load_config()
            # Snapshot categories at sync start (EC-14)
            categories = load_categories()
            source = Path(cfg.get("source_folder", ""))
            library = Path(cfg.get("library_folder", ""))

            result = run_sync(source, library, categories, dry_run=dry_run)

            # Auto-trigger rescan after execute (not dry-run)
            if not dry_run and result.moved:
                logger.info("Auto-reindex after sync: %d items moved", len(result.moved))
                try:
                    run_full_scan()
                except Exception as exc:
                    logger.error("Auto-reindex failed: %s", exc)

            from datetime import datetime, timezone
            self._last_run = datetime.now(timezone.utc).isoformat()
            self._state = "idle" if not self._enabled else "scheduled"

            return _sync_result_to_dict(result)

        finally:
            _scan_lock.release()

    def _schedule_next(self) -> None:
        """Schedule the next timer tick."""
        if not self._enabled:
            return

        if self._timer:
            self._timer.cancel()

        interval_seconds = self._interval_minutes * 60
        self._timer = threading.Timer(interval_seconds, self._tick)
        self._timer.daemon = True
        self._timer.start()

        from datetime import datetime, timedelta, timezone
        next_time = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
        self._next_run = next_time.isoformat()
        self._state = "scheduled"

    def _tick(self) -> None:
        """Timer callback — run sync and reschedule."""
        self.run_once(dry_run=False)
        if self._enabled:
            self._schedule_next()


def _sync_result_to_dict(result) -> dict:
    """
    Serialize a SyncResult to a JSON-safe dictionary.

    Parameters
    ----------
    result : SyncResult
        The sync result to serialize.

    Returns
    -------
    dict
        JSON-safe dictionary representation.
    """
    return {
        "dry_run": result.dry_run,
        "zips_extracted": result.zips_extracted,
        "zips_deleted": result.zips_deleted,
        "moved": [
            {
                "source": str(item.source_path),
                "raw_name": item.raw_name,
                "cleaned_name": item.cleaned_name,
                "category": item.category,
                "dest": str(item.dest_path),
                "item_type": item.item_type,
            }
            for item in result.moved
        ],
        "skipped": [
            {
                "source": str(item.source_path),
                "raw_name": item.raw_name,
                "cleaned_name": item.cleaned_name,
                "category": item.category,
                "is_duplicate": item.is_duplicate,
                "item_type": item.item_type,
            }
            for item in result.skipped
        ],
        "library_zips_cleaned": result.library_zips_cleaned,
        "errors": result.errors,
    }


# Global scheduler instance
_scheduler = SyncScheduler()


# ---------------------------------------------------------------------------
# API: Sync Endpoints
# ---------------------------------------------------------------------------


@app.route("/api/sync/preview", methods=["POST"])
def api_sync_preview():
    """
    Run a dry-run sync and return the planned operations.

    Returns
    -------
    JSON SyncResult (dry_run=True).
    """
    result = _scheduler.run_once(dry_run=True)
    if result is None:
        return jsonify({"error": "Sync already running"}), 409
    return jsonify(result)


@app.route("/api/sync/run", methods=["POST"])
def api_sync_run():
    """
    Execute sync in a background thread.

    Returns 202 immediately; poll /api/sync/status for progress.
    """
    if not _scan_lock.acquire(blocking=False):
        return jsonify({"error": "Sync or scan already running"}), 409
    _scan_lock.release()

    def _bg_sync():
        _scheduler.run_once(dry_run=False)

    thread = threading.Thread(target=_bg_sync, daemon=True)
    thread.start()
    return jsonify({"status": "started"}), 202


@app.route("/api/sync/status", methods=["GET"])
def api_sync_status():
    """
    Return current scheduler state.

    Returns
    -------
    JSON object: {state, last_run, next_run, interval_minutes, enabled}
    """
    return jsonify(_scheduler.status)


@app.route("/api/sync/schedule", methods=["POST"])
def api_sync_schedule():
    """
    Enable/disable scheduler and set interval.

    Expects JSON body: {"enabled": bool, "interval_minutes": int}

    Returns
    -------
    JSON object with updated scheduler status.
    """
    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled")
    interval = data.get("interval_minutes")

    if enabled is True:
        minutes = interval if interval else _scheduler._interval_minutes
        _scheduler.start(minutes)

        # Persist to config
        from config import load_config, save_config
        cfg = load_config()
        cfg["sync_enabled"] = True
        cfg["sync_interval_minutes"] = minutes
        save_config(cfg)
    elif enabled is False:
        _scheduler.stop()

        from config import load_config, save_config
        cfg = load_config()
        cfg["sync_enabled"] = False
        save_config(cfg)
    elif interval:
        _scheduler._interval_minutes = max(1, min(1440, interval))

    return jsonify(_scheduler.status)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5050, debug=False)
