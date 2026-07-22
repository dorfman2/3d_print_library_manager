"""
Tests for scanner.migrate_folder_metadata (EC-1).

Verifies that tags, notes, and cover selections survive a folder move/rename by
being re-attached to the new path instead of orphaned. Uses a real SQLite
database on tmp_path (monkeypatch redirects DB_PATH only).
"""

from pathlib import Path

import pytest

import scanner


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated real SQLite DB and redirect scanner.DB_PATH to it."""
    db_path = tmp_path / "library.db"
    monkeypatch.setattr(scanner, "DB_PATH", db_path)
    scanner.init_db()
    return db_path


def _insert_folder_with_tag(old_path: str) -> None:
    """Insert a folder row plus a tag and a note using the real DB."""
    conn = scanner.get_db()
    try:
        cur = conn.execute(
            "INSERT INTO folders (path, name, raw_name, category, notes, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (old_path, "Widget", "widget", "6 - Electronics", "my note",
             "2026-01-01", "2026-01-01"),
        )
        folder_id = cur.lastrowid
        conn.execute("INSERT INTO tags (name) VALUES (?)", ("favorite",))
        tag_id = conn.execute(
            "SELECT id FROM tags WHERE name = ?", ("favorite",)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO folder_tags (folder_id, tag_id) VALUES (?, ?)",
            (folder_id, tag_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_migrate_preserves_tags_and_notes(isolated_db: Path) -> None:
    """After migration, the new path carries the tag and note."""
    old = "/lib/6 - Electronics/Widget"
    new = "/lib/16 - Work Fixtures and Tooling/Widget"
    _insert_folder_with_tag(old)

    scanner.migrate_folder_metadata(old, new)

    conn = scanner.get_db()
    try:
        row = conn.execute(
            "SELECT id, notes FROM folders WHERE path = ?", (new,)
        ).fetchone()
        assert row is not None, "folder should now live at new path"
        assert row["notes"] == "my note"

        # Old path no longer present
        old_row = conn.execute(
            "SELECT id FROM folders WHERE path = ?", (old,)
        ).fetchone()
        assert old_row is None

        # Tag still attached
        tag_count = conn.execute(
            "SELECT COUNT(*) AS c FROM folder_tags WHERE folder_id = ?",
            (row["id"],),
        ).fetchone()["c"]
        assert tag_count == 1
    finally:
        conn.close()


def test_migrate_noop_when_old_path_absent(isolated_db: Path) -> None:
    """Migrating a non-existent path is a safe no-op."""
    scanner.migrate_folder_metadata("/lib/does/not/exist", "/lib/new")
    conn = scanner.get_db()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM folders").fetchone()["c"]
        assert count == 0
    finally:
        conn.close()


def test_migrate_skips_when_new_path_exists(isolated_db: Path) -> None:
    """If the new path already exists, migration does not clobber it."""
    old = "/lib/A/Widget"
    new = "/lib/B/Widget"
    _insert_folder_with_tag(old)
    # Insert a folder already at new path
    conn = scanner.get_db()
    try:
        conn.execute(
            "INSERT INTO folders (path, name, raw_name, category, notes, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new, "Other", "other", "cat", "keep me", "2026-01-01", "2026-01-01"),
        )
        conn.commit()
    finally:
        conn.close()

    scanner.migrate_folder_metadata(old, new)

    conn = scanner.get_db()
    try:
        row = conn.execute(
            "SELECT notes FROM folders WHERE path = ?", (new,)
        ).fetchone()
        # New path folder is untouched
        assert row["notes"] == "keep me"
        # Old path still present (migration refused)
        old_row = conn.execute(
            "SELECT id FROM folders WHERE path = ?", (old,)
        ).fetchone()
        assert old_row is not None
    finally:
        conn.close()
