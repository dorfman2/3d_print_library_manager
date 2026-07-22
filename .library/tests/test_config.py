"""
Tests for the shared config module (config.py) and category persistence.

Uses monkeypatch only to redirect module-level PATH CONSTANTS to tmp_path so
tests write/read real JSON files without touching the user's real config.
"""

from pathlib import Path

import pytest

import config
import categories


def test_config_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """save_config then load_config returns the same values."""
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)

    cfg = dict(config.DEFAULT_CONFIG)
    cfg["sync_interval_minutes"] = 30
    cfg["sync_enabled"] = True
    cfg["source_folder"] = str(tmp_path / "Downloads")
    cfg["library_folder"] = str(tmp_path / "Library")
    config.save_config(cfg)

    loaded = config.load_config()
    assert loaded["sync_interval_minutes"] == 30
    assert loaded["sync_enabled"] is True
    assert loaded["source_folder"] == str(tmp_path / "Downloads")
    assert loaded["library_folder"] == str(tmp_path / "Library")


def test_load_config_defaults_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing config file yields defaults with resolved paths."""
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "nope.json")
    loaded = config.load_config()
    # None placeholders resolve to real paths
    assert loaded["source_folder"] is not None
    assert loaded["library_folder"] is not None
    assert loaded["sync_interval_minutes"] == 60


def test_resolve_downloads_folder_returns_path() -> None:
    """resolve_downloads_folder always returns an existing directory."""
    result = config.resolve_downloads_folder()
    assert isinstance(result, Path)
    assert result.is_dir()


def test_save_config_only_writes_known_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown keys are not persisted."""
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)
    cfg = dict(config.DEFAULT_CONFIG)
    cfg["bogus_key"] = "should not persist"
    config.save_config(cfg)

    import json
    written = json.loads(cfg_path.read_text())
    assert "bogus_key" not in written


def test_categories_save_and_load_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """save_categories then load_categories returns the same list."""
    cat_path = tmp_path / "categories.json"
    monkeypatch.setattr(categories, "CATEGORIES_PATH", cat_path)

    cats = [
        {"name": "0 - Calibration", "keywords": ["benchy", "calibration"]},
        {"name": "Uncategorized", "keywords": []},
    ]
    categories.save_categories(cats)
    loaded = categories.load_categories()
    assert loaded == cats


def test_load_categories_empty_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No categories.json → empty list (no auto-seed)."""
    monkeypatch.setattr(categories, "CATEGORIES_PATH", tmp_path / "none.json")
    assert categories.load_categories() == []
