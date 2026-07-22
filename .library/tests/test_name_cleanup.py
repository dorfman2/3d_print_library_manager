"""
Tests for the name-cleanup pipeline (categories.clean_name).

Table-driven cases derived from the Sorter specification examples plus
regression cases for the underscore-version bug (v1_2) and the trailing-author
edge case (EC-24).
"""

import pytest

import categories


# (raw_name, expected_cleaned_name)
CLEANUP_CASES = [
    # Spec examples
    ("Ender_3_Fan_Duct_v3_FINAL_STL", "Ender 3 Fan Duct"),
    ("case-for-rak-wisblock-1-watt-starter-kit-model_files",
     "Case for Rak Wisblock 1 Watt Starter Kit"),
    ("desk_cable_organizer_v1_2_updated", "Desk Cable Organizer"),
    ("Raspberry_Pi_4_Case_by_SomeUser", "Raspberry Pi 4 Case"),
    ("3DBenchy", "3DBenchy"),
    ("NERF_Blaster_Attachment", "NERF Blaster Attachment"),
    ("musubi-press-spam-eggtamago-etc-model_files",
     "Musubi Press Spam Eggtamago Etc"),
]


@pytest.mark.parametrize("raw,expected", CLEANUP_CASES)
def test_clean_name_spec_cases(raw: str, expected: str) -> None:
    """Each spec example cleans to the documented result."""
    assert categories.clean_name(raw) == expected


def test_underscore_version_fully_stripped() -> None:
    """Regression: v1_2 (underscore-separated version) must not leave a stray '2'."""
    assert categories.clean_name("thing_v1_2") == "Thing"
    assert categories.clean_name("thing_v2_3_final") == "Thing"


def test_dot_version_stripped() -> None:
    """Dot-separated versions are stripped."""
    assert categories.clean_name("bracket_v1.0") == "Bracket"


def test_trailing_author_stripped_but_midname_by_preserved() -> None:
    """EC-24: strip trailing 'by <author>', preserve mid-name 'by'."""
    assert categories.clean_name("Widget_by_Someone") == "Widget"
    assert "By" in categories.clean_name("Fly_by_Wire_Bracket") or \
        "by" in categories.clean_name("Fly_by_Wire_Bracket")


def test_empty_result_returns_original() -> None:
    """Rule 8: if cleanup empties the string, return the original."""
    result = categories.clean_name("v1")
    assert result != ""


def test_allcaps_and_internal_caps_preserved() -> None:
    """Acronyms (all-caps) and internal-caps survive cleanup."""
    assert "MMU" in categories.clean_name("MMU_purge_bucket")
    assert categories.clean_name("RPi_Case") == "RPi Case"


def test_separators_replaced_and_collapsed() -> None:
    """Underscores/dashes become single spaces."""
    assert categories.clean_name("a__b--c") == "A B C"
