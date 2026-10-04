"""
Shared configuration module for the 3D Print Library.

Provides a single JSON config file (`config.json`) that stores user settings
for both the viewer and sorter components. Resolves default paths for the
source (Downloads) and library folders cross-platform.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Paths relative to this module's location
LIBRARY_DIR: Path = Path(__file__).resolve().parent
CONFIG_PATH: Path = LIBRARY_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "source_folder": None,
    "library_folder": None,
    "sync_interval_minutes": 60,
    "sync_enabled": False,
    "server_port": 5050,
}


def _windows_downloads_from_registry() -> Optional[Path]:
    """
    Read the real Downloads folder path from the Windows registry.

    Windows users can relocate their Downloads folder; the authoritative
    location is the Known Folders GUID stored under the Shell Folders key.
    This reads that value and expands any embedded environment variables.

    Returns
    -------
    Optional[Path]
        The resolved Downloads path, or None if it cannot be determined
        (non-Windows, missing key, or any registry error).
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg  # Windows-only stdlib; imported lazily

        key_path = (
            r"Software\Microsoft\Windows\CurrentVersion"
            r"\Explorer\Shell Folders"
        )
        guid = "{374DE290-123F-4565-9164-39C4925E467B}"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, guid)
        return Path(os.path.expandvars(value))
    except (ImportError, OSError, FileNotFoundError) as exc:
        logger.warning("Could not read Downloads folder from registry: %s", exc)
        return None


def resolve_downloads_folder() -> Path:
    """
    Resolve the OS Downloads folder cross-platform.

    On Windows, prefers the real (possibly relocated) Downloads folder from
    the registry. Otherwise uses ~/Downloads. Falls back to the home
    directory if nothing valid is found.

    Returns
    -------
    Path
        Absolute path to the Downloads folder.
    """
    win_downloads = _windows_downloads_from_registry()
    if win_downloads and win_downloads.is_dir():
        return win_downloads

    downloads: Path = Path.home() / "Downloads"
    if downloads.is_dir():
        return downloads

    logger.warning(
        "Downloads folder not found at %s, falling back to home directory",
        downloads,
    )
    return Path.home()


def resolve_library_folder() -> Path:
    """
    Resolve the default library folder.

    Defaults to the parent of the `.library/` directory (i.e., the root of
    the user's 3D print collection).

    Returns
    -------
    Path
        Absolute path to the library root folder.
    """
    return LIBRARY_DIR.parent


def load_config() -> dict[str, Any]:
    """
    Load configuration from config.json.

    If the file does not exist or is unreadable, returns a copy of
    DEFAULT_CONFIG with resolved paths.

    Returns
    -------
    dict[str, Any]
        Configuration dictionary with all keys from DEFAULT_CONFIG.
    """
    cfg: dict[str, Any] = dict(DEFAULT_CONFIG)

    if CONFIG_PATH.is_file():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                data: dict[str, Any] = json.load(fh)
            # Merge saved values onto defaults (preserves new keys added later)
            for key in DEFAULT_CONFIG:
                if key in data:
                    cfg[key] = data[key]
            logger.info("Loaded config from %s", CONFIG_PATH)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to read config file %s: %s — using defaults",
                CONFIG_PATH,
                exc,
            )

    # Resolve None values to their platform defaults
    if cfg["source_folder"] is None:
        cfg["source_folder"] = str(resolve_downloads_folder())
    if cfg["library_folder"] is None:
        cfg["library_folder"] = str(resolve_library_folder())

    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    """
    Persist configuration to config.json.

    Parameters
    ----------
    cfg : dict[str, Any]
        Configuration dictionary to save. Only keys present in DEFAULT_CONFIG
        are written.

    Raises
    ------
    OSError
        If the config file cannot be written.
    """
    # Only persist known keys
    data: dict[str, Any] = {k: cfg[k] for k in DEFAULT_CONFIG if k in cfg}

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        logger.info("Saved config to %s", CONFIG_PATH)
    except OSError as exc:
        logger.error("Failed to write config file %s: %s", CONFIG_PATH, exc)
        raise
