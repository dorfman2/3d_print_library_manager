"""
3D Print Library Flask Server.

Serves the SPA frontend, REST API for folders/files/tags/categories,
thumbnail cache, and triggers for file open/reveal and scanner rescan.
Binds to 127.0.0.1:5050 only.
"""

import logging
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


@app.route("/")
def index():
    """Serve the SPA index.html."""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/generate")
def generate_page():
    """Serve the batch thumbnail generation page."""
    return send_from_directory(app.static_folder, "generate.html")


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
                subprocess.run(
                    ["cmd", "/c", "start", "", str(file_path)], check=True
                )
            else:
                subprocess.run(["xdg-open", str(file_path)], check=True)
        except subprocess.CalledProcessError as exc:
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
                subprocess.run(
                    ["explorer", "/select,", str(file_path)], check=True
                )
            else:
                # Linux: open parent directory
                subprocess.run(
                    ["xdg-open", str(file_path.parent)], check=True
                )
        except subprocess.CalledProcessError as exc:
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
# Run
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5050, debug=False)
