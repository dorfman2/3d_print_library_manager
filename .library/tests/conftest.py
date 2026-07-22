"""
Shared pytest fixtures for the 3D Print Library test suite.

All tests use real files on tmp_path — no mocks (per python-prefs.md). The only
use of monkeypatch is to redirect module-level PATH CONSTANTS to temporary
locations so tests never touch the real config/library/database. This is path
redirection to real temp files, not behavior mocking.
"""

import sys
from pathlib import Path

import pytest

# Make the .library modules importable (tests live in .library/tests/)
LIBRARY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LIBRARY_DIR))


@pytest.fixture()
def tmp_library(tmp_path: Path) -> Path:
    """Return an empty temporary library root directory."""
    lib = tmp_path / "Library"
    lib.mkdir()
    return lib


@pytest.fixture()
def tmp_source(tmp_path: Path) -> Path:
    """Return an empty temporary source (Downloads) directory."""
    src = tmp_path / "Downloads"
    src.mkdir()
    return src


@pytest.fixture()
def default_categories() -> list:
    """Load the bundled merged default category list (real file)."""
    import json
    path = LIBRARY_DIR / "categories.default.json"
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)["categories"]
