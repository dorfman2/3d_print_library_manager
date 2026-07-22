"""
Shared configuration module for the 3D Print Library.

Provides a single JSON config file (`config.json`) that stores user settings
for both the viewer and sorter components. Resolves default paths for the
source (Downloads) and library folders cross-platform.
"""

import json
import logging
from pathlib import Path
from typing import Any

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


def resolve_downloads_folder() -> Path:
    """
    Resolve the OS Downloads folder cross-platform.

    Returns the user's ~/Downloads directory on both macOS and Windows.
    Falls back to the home directory if ~/Downloads does not exist.

    Returns
    -------
    Path
        Absolute path to the Downloads folder.
    """
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
