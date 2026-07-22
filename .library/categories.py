"""
Categories module for the 3D Print Library.

Provides name-cleanup rules (8-step pipeline) and keyword-based categorization
for sorting incoming 3D print files into the library. Also handles loading
and saving the user's category configuration.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Paths relative to this module
LIBRARY_DIR: Path = Path(__file__).resolve().parent
CATEGORIES_PATH: Path = LIBRARY_DIR / "categories.json"
CATEGORIES_DEFAULT_PATH: Path = LIBRARY_DIR / "categories.default.json"

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Noise tokens stripped during cleanup (checked case-insensitively)
NOISE_TOKENS: set[str] = {
    "stl", "3mf", "obj", "step", "gcode", "final", "remix", "remixed",
    "remixof", "print", "printed", "printable", "updated", "fixed",
    "free", "paid", "model_files", "files",
}

# Small words downcased in non-first position during title-casing
SMALL_WORDS: set[str] = {
    "and", "for", "of", "the", "in", "or", "to", "at", "a", "an",
    "but", "by", "as", "nor", "on",
}

# Regex patterns for noise stripping
_VERSION_PATTERN: re.Pattern[str] = re.compile(
    r"(?<![a-zA-Z])[vV]\d+(?:[._]\d+)*(?![a-zA-Z])"
)
_PRINTABLES_ID_PATTERN: re.Pattern[str] = re.compile(
    r"(?<![a-zA-Z0-9])\d{5,}(?![a-zA-Z0-9])"
)
_UUID_PATTERN: re.Pattern[str] = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
# Trailing "by <author>" — matches when "by" is followed by a single word at the END
# Preserves mid-name "by" (e.g., "Fly by Wire Bracket")
_TRAILING_AUTHOR_PATTERN: re.Pattern[str] = re.compile(
    r"[\s_-]+by[\s_-]+[^\s_-]+\s*$", re.IGNORECASE
)


# ─────────────────────────────────────────────────────────────────────────────
# Name Cleanup
# ─────────────────────────────────────────────────────────────────────────────


def clean_name(raw_name: str) -> str:
    """
    Apply the 8-step name-cleanup pipeline.

    Steps:
        1. Strip trailing noise before replacing separators (UUIDs, Printables IDs)
        2. Strip noise tokens (multi-pass until stable): version numbers, file-type
           tags, model_files/files, final, remix*, by <author>, print*, updated,
           fixed, free, paid
        3. Replace ``_`` and ``-`` with spaces
        4. Collapse multiple spaces, trim
        5. Title-case fully-lowercase words
        6. Preserve internal-uppercase (3DBenchy, RPi) and all-caps (NERF, MMU)
        7. Downcase small words in non-first position
        8. Empty result → return original name

    Parameters
    ----------
    raw_name : str
        The raw folder or file name (without extension).

    Returns
    -------
    str
        Cleaned display name.
    """
    name: str = raw_name.strip()
    if not name:
        return raw_name

    # Step 1: Strip trailing noise before separator replacement
    # Remove UUIDs
    name = _UUID_PATTERN.sub("", name)
    # Remove long numeric IDs (Printables-style)
    name = _PRINTABLES_ID_PATTERN.sub("", name)
    # Remove _model_files / _files suffix
    name = re.sub(r"[_\-]?model_files\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[_\-]?files\b", "", name, flags=re.IGNORECASE)

    # Step 2: Strip noise tokens (multi-pass until stable)
    prev: str = ""
    iterations: int = 0
    while prev != name and iterations < 10:
        prev = name
        iterations += 1

        # Version numbers (v1, V2.3, v12)
        name = _VERSION_PATTERN.sub("", name)

        # Trailing author: only strip "by <word>" at the END of the string
        # Preserves mid-name "by" (e.g., "Fly by Wire Bracket")
        name = _TRAILING_AUTHOR_PATTERN.sub("", name)

        # Noise tokens — strip as whole words (bounded by separators or edges)
        for token in NOISE_TOKENS:
            # Match the token bounded by non-alphanumeric chars, separators, or edges
            pattern = re.compile(
                r"(?<![a-zA-Z])" + re.escape(token) + r"(?![a-zA-Z])",
                re.IGNORECASE,
            )
            name = pattern.sub("", name)

        # Clean up dangling separators left by token removal
        name = re.sub(r"[_-]{2,}", "_", name)
        name = name.strip("_- ")

    # Step 3: Replace _ and - with spaces
    name = name.replace("_", " ").replace("-", " ")

    # Step 4: Collapse multiple spaces, trim
    name = re.sub(r"\s+", " ", name).strip()

    # Step 5 + 6: Smart title-casing
    words: list[str] = name.split(" ")
    result_words: list[str] = []
    for word in words:
        if not word:
            continue
        if _is_all_caps(word) and len(word) > 1:
            # Step 6: Preserve all-caps words (NERF, MMU, RPi-adjacent)
            result_words.append(word)
        elif _has_internal_uppercase(word):
            # Step 6: Preserve internal-uppercase (3DBenchy, RPi, WiFi)
            result_words.append(word)
        elif word.islower():
            # Step 5: Title-case fully-lowercase words
            result_words.append(word.capitalize())
        else:
            # Already has some casing — preserve as-is
            result_words.append(word)

    # Step 7: Downcase small words in non-first position
    for i in range(1, len(result_words)):
        if result_words[i].lower() in SMALL_WORDS:
            result_words[i] = result_words[i].lower()

    cleaned: str = " ".join(result_words)

    # Step 8: If empty after cleanup, return original
    if not cleaned.strip():
        return raw_name

    return cleaned


def _is_all_caps(word: str) -> bool:
    """
    Check if a word is all uppercase letters (possibly with digits).

    Considers words like 'NERF', 'MMU', '3MF' as all-caps.
    Single characters are NOT treated as all-caps (to allow normal title-casing).

    Parameters
    ----------
    word : str
        A single word to check.

    Returns
    -------
    bool
        True if the word's alphabetic characters are all uppercase.
    """
    alpha_chars: str = "".join(c for c in word if c.isalpha())
    if len(alpha_chars) <= 1:
        return False
    return alpha_chars.isupper()


def _has_internal_uppercase(word: str) -> bool:
    """
    Check if a word has uppercase characters after the first position.

    Detects camelCase, PascalCase, and mixed patterns like '3DBenchy', 'RPi'.

    Parameters
    ----------
    word : str
        A single word to check.

    Returns
    -------
    bool
        True if there is an uppercase letter after a lowercase/digit character.
    """
    # Words like "3DBenchy" — have uppercase after position 0 that follows
    # a non-uppercase char
    for i in range(1, len(word)):
        if word[i].isupper() and i > 0:
            # Check if preceded by a lowercase or digit
            if word[i - 1].islower() or word[i - 1].isdigit():
                return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Categorization
# ─────────────────────────────────────────────────────────────────────────────


def categorize(name: str, categories: list[dict[str, Any]]) -> str:
    """
    Score a cleaned name against each category's keywords.

    Scoring is by NUMBER of matched keywords (not mere presence). Multi-word
    keywords count as one match but are weighted higher implicitly because they
    are more specific. Ties are broken by lowest category number (earliest in
    the list).

    Parameters
    ----------
    name : str
        The cleaned display name to categorize.
    categories : list[dict[str, Any]]
        List of category dicts, each with 'name' and 'keywords' keys.

    Returns
    -------
    str
        The category folder name (e.g. "6 - Electronics") or "Uncategorized".
    """
    if not name or not categories:
        return "Uncategorized"

    name_lower: str = name.lower()
    best_category: str = "Uncategorized"
    best_score: int = 0
    best_index: int = len(categories)  # Higher than any real index

    for idx, cat in enumerate(categories):
        cat_name: str = cat.get("name", "")
        keywords: list[str] = cat.get("keywords", [])

        if cat_name == "Uncategorized":
            continue

        score: int = 0
        for keyword in keywords:
            if keyword.lower() in name_lower:
                score += 1

        if score > best_score or (score == best_score and score > 0
                                   and idx < best_index):
            best_score = score
            best_category = cat_name
            best_index = idx

    if best_score == 0:
        return "Uncategorized"

    return best_category


# ─────────────────────────────────────────────────────────────────────────────
# Category Configuration I/O
# ─────────────────────────────────────────────────────────────────────────────


def load_categories() -> list[dict[str, Any]]:
    """
    Load the user's categories from categories.json.

    Does NOT auto-seed from defaults — the setup wizard handles that.
    Returns an empty list if categories.json does not exist.

    Returns
    -------
    list[dict[str, Any]]
        List of category dicts with 'name' and 'keywords' keys.
    """
    if not CATEGORIES_PATH.is_file():
        logger.info("No categories.json found at %s", CATEGORIES_PATH)
        return []

    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        categories: list[dict[str, Any]] = data.get("categories", [])
        logger.info(
            "Loaded %d categories from %s", len(categories), CATEGORIES_PATH
        )
        return categories
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Failed to read categories.json at %s: %s", CATEGORIES_PATH, exc
        )
        return []


def save_categories(categories: list[dict[str, Any]]) -> None:
    """
    Save the user's categories to categories.json.

    Parameters
    ----------
    categories : list[dict[str, Any]]
        List of category dicts with 'name' and 'keywords' keys.

    Raises
    ------
    OSError
        If the file cannot be written.
    """
    data: dict[str, Any] = {
        "version": 1,
        "description": "User-configured category list.",
        "categories": categories,
    }

    try:
        with open(CATEGORIES_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        logger.info("Saved %d categories to %s", len(categories), CATEGORIES_PATH)
    except OSError as exc:
        logger.error(
            "Failed to write categories.json at %s: %s", CATEGORIES_PATH, exc
        )
        raise


def load_default_categories() -> list[dict[str, Any]]:
    """
    Load the bundled default categories from categories.default.json.

    Returns
    -------
    list[dict[str, Any]]
        List of default category dicts.
    """
    if not CATEGORIES_DEFAULT_PATH.is_file():
        logger.warning(
            "Default categories file not found at %s", CATEGORIES_DEFAULT_PATH
        )
        return []

    try:
        with open(CATEGORIES_DEFAULT_PATH, "r", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        return data.get("categories", [])
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Failed to read default categories at %s: %s",
            CATEGORIES_DEFAULT_PATH,
            exc,
        )
        return []
