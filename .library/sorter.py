"""
Sorter module for the 3D Print Library.

Implements the five-phase sync pipeline that ingests new 3D print files from
a Source folder (e.g., Downloads) into the organized library. Cross-platform
(macOS and Windows) — no OS-specific calls.

Phases:
    1. Pre-process Source ZIPs (extract in place, delete redundant)
    2. Build library index (collect cleaned names of existing projects)
    3. Collect and categorize candidates (name cleanup + keyword scoring + dedup)
    4. Move to library (with collision handling)
    5. Clean library ZIPs (recursive extraction + deletion)
"""

import logging
import platform
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from categories import categorize, clean_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Print file extensions recognized by the sorter
PRINT_EXTENSIONS: set[str] = {
    ".stl", ".3mf", ".obj", ".step", ".stp", ".f3d", ".f3z",
    ".amf", ".gcode", ".bgcode", ".gco",
}

# Directories to skip when scanning
SKIP_DIRS: set[str] = {".library", ".kiro", ".git", "__pycache__", ".venv", "venv"}

# Maximum path length on Windows
WINDOWS_MAX_PATH: int = 260


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


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

    zips_extracted: list[str] = field(default_factory=list)
    zips_deleted: list[str] = field(default_factory=list)
    moved: list[SyncPlanItem] = field(default_factory=list)
    skipped: list[SyncPlanItem] = field(default_factory=list)
    library_zips_cleaned: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Pre-process Source ZIPs
# ─────────────────────────────────────────────────────────────────────────────


def _zip_contains_print_files(zip_path: Path) -> bool:
    """
    Check if a ZIP archive contains at least one recognized print file.

    Parameters
    ----------
    zip_path : Path
        Path to the ZIP file.

    Returns
    -------
    bool
        True if the ZIP contains at least one file with a print extension.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                ext: str = Path(member).suffix.lower()
                if ext in PRINT_EXTENSIONS:
                    return True
    except (zipfile.BadZipFile, OSError) as exc:
        logger.warning("Cannot inspect ZIP %s: %s", zip_path, exc)
    return False


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> bool:
    """
    Safely extract a ZIP file, rejecting path traversal entries.

    Parameters
    ----------
    zip_path : Path
        Path to the ZIP file.
    dest_dir : Path
        Directory to extract into.

    Returns
    -------
    bool
        True if extraction succeeded.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                # Reject path traversal and absolute paths (EC-9)
                if ".." in member or Path(member).is_absolute():
                    logger.warning(
                        "Skipping ZIP member with path traversal: %s in %s",
                        member,
                        zip_path,
                    )
                    continue
                # Verify extraction stays within dest_dir
                target: Path = (dest_dir / member).resolve()
                if not str(target).startswith(str(dest_dir.resolve())):
                    logger.warning(
                        "Skipping ZIP member escaping dest: %s in %s",
                        member,
                        zip_path,
                    )
                    continue
                zf.extract(member, dest_dir)
        return True
    except (zipfile.BadZipFile, OSError) as exc:
        logger.error("Failed to extract ZIP %s: %s", zip_path, exc)
        return False


def preprocess_source_zips(
    source: Path, dry_run: bool = True
) -> tuple[list[str], list[str]]:
    """
    Phase 1: Extract print-containing ZIPs in Source, delete redundant ones.

    A ZIP is "redundant" if its contents already exist as an extracted folder
    with the same stem name. Only processes root-level ZIPs in the Source folder.

    Parameters
    ----------
    source : Path
        The source/downloads folder to scan.
    dry_run : bool
        If True, no files are modified — only reports what would happen.

    Returns
    -------
    tuple[list[str], list[str]]
        (extracted, deleted) — lists of ZIP filenames processed.
    """
    extracted: list[str] = []
    deleted: list[str] = []

    if not source.is_dir():
        logger.warning("Source folder does not exist: %s", source)
        return extracted, deleted

    for item in sorted(source.iterdir()):
        if not item.is_file() or item.suffix.lower() != ".zip":
            continue

        # Skip ZIPs without print files (EC-11)
        if not _zip_contains_print_files(item):
            logger.debug("Skipping non-print ZIP: %s", item.name)
            continue

        stem_dir: Path = source / item.stem

        if stem_dir.is_dir():
            # Folder with same name exists — ZIP is redundant
            logger.info("Redundant ZIP (folder exists): %s", item.name)
            if not dry_run:
                try:
                    item.unlink()
                    deleted.append(item.name)
                except OSError as exc:
                    logger.error("Failed to delete redundant ZIP %s: %s", item, exc)
            else:
                deleted.append(item.name)
        else:
            # Extract in place
            logger.info("Extracting ZIP: %s", item.name)
            if not dry_run:
                extract_dir: Path = source / item.stem
                extract_dir.mkdir(parents=True, exist_ok=True)
                if _safe_extract_zip(item, extract_dir):
                    extracted.append(item.name)
                    # Delete the ZIP after successful extraction
                    try:
                        item.unlink()
                    except OSError as exc:
                        logger.error(
                            "Extracted but failed to delete ZIP %s: %s", item, exc
                        )
                else:
                    # Extraction failed; clean up empty dir
                    if extract_dir.exists() and not any(extract_dir.iterdir()):
                        extract_dir.rmdir()
            else:
                extracted.append(item.name)

    return extracted, deleted


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: Build Library Index
# ─────────────────────────────────────────────────────────────────────────────


def build_library_index(library: Path) -> set[str]:
    """
    Phase 2: Collect cleaned names of all existing projects in the library.

    Walks the library's category folders one level deep and collects the
    cleaned names of each project subfolder for deduplication.

    Parameters
    ----------
    library : Path
        Root path of the library folder.

    Returns
    -------
    set[str]
        Set of casefolded cleaned project names already in the library.
    """
    index: set[str] = set()

    if not library.is_dir():
        logger.warning("Library folder does not exist: %s", library)
        return index

    for category_dir in sorted(library.iterdir()):
        if not category_dir.is_dir():
            continue
        if category_dir.name.startswith(".") or category_dir.name in SKIP_DIRS:
            continue

        for project_dir in sorted(category_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            if project_dir.name.startswith("."):
                continue

            cleaned: str = clean_name(project_dir.name)
            index.add(cleaned.casefold())

    logger.info("Library index: %d existing projects", len(index))
    return index


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: Collect and Categorize Candidates
# ─────────────────────────────────────────────────────────────────────────────


def collect_candidates(
    source: Path,
    library_index: set[str],
    categories: list[dict[str, Any]],
    library: Path,
) -> list[SyncPlanItem]:
    """
    Phase 3: Collect source items, clean names, categorize, and check for dupes.

    Processes root-level items in the Source folder:
    - Directories are treated as project folders
    - Loose print files are wrapped in a subfolder named after the file stem

    Parameters
    ----------
    source : Path
        The source/downloads folder.
    library_index : set[str]
        Set of casefolded cleaned names already in the library.
    categories : list[dict[str, Any]]
        Category configuration list.
    library : Path
        Root path of the library.

    Returns
    -------
    list[SyncPlanItem]
        List of planned move items (some may be marked as duplicates).
    """
    candidates: list[SyncPlanItem] = []

    if not source.is_dir():
        return candidates

    for item in sorted(source.iterdir()):
        # Skip hidden files/dirs and known system dirs
        if item.name.startswith(".") or item.name in SKIP_DIRS:
            continue

        # Skip non-print loose files
        if item.is_file():
            if item.suffix.lower() not in PRINT_EXTENSIONS:
                continue
            # Wrap loose file in a subfolder
            raw_name: str = item.stem
            cleaned: str = clean_name(raw_name)
            category: str = categorize(cleaned, categories)
            is_dup: bool = cleaned.casefold() in library_index
            dest: Path = _compute_dest_path(library, category, cleaned)

            candidates.append(SyncPlanItem(
                source_path=item,
                raw_name=raw_name,
                cleaned_name=cleaned,
                category=category,
                dest_path=dest,
                is_duplicate=is_dup,
                item_type="file",
            ))
        elif item.is_dir():
            raw_name = item.name
            cleaned = clean_name(raw_name)
            category = categorize(cleaned, categories)
            is_dup = cleaned.casefold() in library_index
            dest = _compute_dest_path(library, category, cleaned)

            candidates.append(SyncPlanItem(
                source_path=item,
                raw_name=raw_name,
                cleaned_name=cleaned,
                category=category,
                dest_path=dest,
                is_duplicate=is_dup,
                item_type="dir",
            ))

    return candidates


def _compute_dest_path(library: Path, category: str, cleaned_name: str) -> Path:
    """
    Compute the destination path for a project in the library.

    Parameters
    ----------
    library : Path
        Root path of the library.
    category : str
        Category folder name (e.g. "6 - Electronics").
    cleaned_name : str
        Cleaned project name.

    Returns
    -------
    Path
        Full destination path.
    """
    dest: Path = library / category / cleaned_name

    # Windows MAX_PATH handling (EC-19)
    if platform.system() == "Windows" and len(str(dest)) > WINDOWS_MAX_PATH:
        import hashlib
        hash_suffix: str = hashlib.sha256(
            cleaned_name.encode()
        ).hexdigest()[:8]
        max_name_len: int = WINDOWS_MAX_PATH - len(str(library / category)) - 10
        truncated: str = cleaned_name[:max_name_len] + "_" + hash_suffix
        dest = library / category / truncated
        logger.warning(
            "Path too long, truncated: %s -> %s", cleaned_name, truncated
        )

    return dest


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: Execute Moves
# ─────────────────────────────────────────────────────────────────────────────


def _unique_dest_path(dest: Path) -> Path:
    """
    Find a unique destination path by appending _2, _3, etc. if needed.

    Parameters
    ----------
    dest : Path
        Desired destination path.

    Returns
    -------
    Path
        A path that does not exist on disk.
    """
    if not dest.exists():
        return dest

    base: Path = dest.parent
    name: str = dest.name
    counter: int = 2
    while True:
        candidate: Path = base / f"{name}_{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def execute_moves(
    plan: list[SyncPlanItem], dry_run: bool = True
) -> tuple[list[SyncPlanItem], list[SyncPlanItem]]:
    """
    Phase 4: Execute planned moves from Source to Library.

    Skips duplicates. Creates category folders on first use.
    Uses unique-path collision handling (_2, _3, ...).

    Parameters
    ----------
    plan : list[SyncPlanItem]
        List of planned move items from collect_candidates.
    dry_run : bool
        If True, no files are moved — only reports.

    Returns
    -------
    tuple[list[SyncPlanItem], list[SyncPlanItem]]
        (moved, skipped) — items that were moved and items skipped.
    """
    moved: list[SyncPlanItem] = []
    skipped: list[SyncPlanItem] = []

    for item in plan:
        if item.is_duplicate:
            logger.info("SKIP (duplicate): %s", item.cleaned_name)
            skipped.append(item)
            continue

        if dry_run:
            moved.append(item)
            continue

        try:
            # Ensure category folder exists (EC-27)
            item.dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Get unique destination (collision handling)
            final_dest: Path = _unique_dest_path(item.dest_path)
            if final_dest != item.dest_path:
                logger.info(
                    "Collision resolved: %s -> %s",
                    item.dest_path.name,
                    final_dest.name,
                )
                item.dest_path = final_dest

            if item.item_type == "file":
                # Wrap loose file in a subfolder
                final_dest.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item.source_path), str(final_dest / item.source_path.name))
            else:
                # Move directory
                shutil.move(str(item.source_path), str(final_dest))

            moved.append(item)
            logger.info("MOVED: %s -> %s", item.raw_name, final_dest)

        except OSError as exc:
            # EC-16, EC-17: Don't crash on move failure
            logger.error(
                "Failed to move %s: %s", item.source_path, exc
            )
            skipped.append(item)

    return moved, skipped


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5: Clean Library ZIPs
# ─────────────────────────────────────────────────────────────────────────────


def clean_library_zips(library: Path, dry_run: bool = True) -> list[str]:
    """
    Phase 5: Recursively find and extract ZIPs within the library, then delete them.

    Only extracts ZIPs that contain print files. Extraction is in-place
    (into the same directory as the ZIP).

    Parameters
    ----------
    library : Path
        Root path of the library.
    dry_run : bool
        If True, no files are modified — only reports.

    Returns
    -------
    list[str]
        List of ZIP filenames that were cleaned.
    """
    cleaned: list[str] = []

    if not library.is_dir():
        return cleaned

    # Walk recursively, skipping dotfolders
    for zip_path in sorted(library.rglob("*.zip")):
        # Skip .library and other hidden dirs (EC-5)
        parts: tuple[str, ...] = zip_path.relative_to(library).parts
        if any(p.startswith(".") or p in SKIP_DIRS for p in parts):
            continue

        if not _zip_contains_print_files(zip_path):
            continue

        logger.info("Library ZIP: %s", zip_path.relative_to(library))

        if not dry_run:
            extract_dir: Path = zip_path.parent
            try:
                if _safe_extract_zip(zip_path, extract_dir):
                    zip_path.unlink()
                    cleaned.append(str(zip_path.relative_to(library)))
                    logger.info("Cleaned library ZIP: %s", zip_path.name)
            except OSError as exc:
                logger.error("Failed to clean library ZIP %s: %s", zip_path, exc)
        else:
            cleaned.append(str(zip_path.relative_to(library)))

    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────


def run_sync(
    source: Path,
    library: Path,
    categories: list[dict[str, Any]],
    dry_run: bool = True,
) -> SyncResult:
    """
    Execute the five-phase sync pipeline.

    Parameters
    ----------
    source : Path
        The source/downloads folder.
    library : Path
        Root path of the library.
    categories : list[dict[str, Any]]
        Category configuration list.
    dry_run : bool
        If True, no files are moved/deleted — preview mode only.

    Returns
    -------
    SyncResult
        Complete outcome of the sync operation.
    """
    result = SyncResult(dry_run=dry_run)

    logger.info(
        "Starting sync: source=%s, library=%s, dry_run=%s",
        source, library, dry_run,
    )

    # Phase 1: Pre-process source ZIPs
    try:
        extracted, deleted = preprocess_source_zips(source, dry_run)
        result.zips_extracted = extracted
        result.zips_deleted = deleted
    except Exception as exc:
        logger.error("Phase 1 error: %s", exc)
        result.errors.append(f"Phase 1: {exc}")

    # Phase 2: Build library index
    try:
        library_index: set[str] = build_library_index(library)
    except Exception as exc:
        logger.error("Phase 2 error: %s", exc)
        result.errors.append(f"Phase 2: {exc}")
        library_index = set()

    # Phase 3: Collect and categorize candidates
    try:
        candidates: list[SyncPlanItem] = collect_candidates(
            source, library_index, categories, library
        )
    except Exception as exc:
        logger.error("Phase 3 error: %s", exc)
        result.errors.append(f"Phase 3: {exc}")
        candidates = []

    # Phase 4: Execute moves
    try:
        moved, skipped_items = execute_moves(candidates, dry_run)
        result.moved = moved
        result.skipped = skipped_items
    except Exception as exc:
        logger.error("Phase 4 error: %s", exc)
        result.errors.append(f"Phase 4: {exc}")

    # Phase 5: Clean library ZIPs
    try:
        library_zips: list[str] = clean_library_zips(library, dry_run)
        result.library_zips_cleaned = library_zips
    except Exception as exc:
        logger.error("Phase 5 error: %s", exc)
        result.errors.append(f"Phase 5: {exc}")

    logger.info(
        "Sync complete: %d moved, %d skipped, %d ZIPs extracted, "
        "%d ZIPs deleted, %d library ZIPs cleaned, %d errors",
        len(result.moved),
        len(result.skipped),
        len(result.zips_extracted),
        len(result.zips_deleted),
        len(result.library_zips_cleaned),
        len(result.errors),
    )

    return result
