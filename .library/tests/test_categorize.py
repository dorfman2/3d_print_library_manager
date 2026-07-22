"""
Tests for keyword-based categorization (categories.categorize).

Verifies keyword scoring, tie-breaking by lowest category number, the
distinctive work-category keywords beating generic single-word matches (EC-33),
and the no-match fallback to Uncategorized (EC-26).
"""

import pytest

import categories


# (name, expected_category)
CATEGORY_CASES = [
    ("Case for Rak Wisblock Starter Kit", "6 - Electronics"),
    ("NERF Blaster Attachment", "13 - NERF"),
    ("Raspberry Pi 4 Case", "6 - Electronics"),
    ("Gridfinity Bin", "4 - Tools and Organization"),
    ("Warhammer 40k Terrain", "9 - Tabletop"),
    ("Lego Technic Gear", "14 - Legos"),
    ("Cosplay Helmet Prop", "15 - Cosplay"),
]


@pytest.mark.parametrize("name,expected", CATEGORY_CASES)
def test_categorize_keyword_match(
    name: str, expected: str, default_categories: list
) -> None:
    """Names map to the expected category via keyword scoring."""
    assert categories.categorize(name, default_categories) == expected


def test_work_keyword_beats_generic_jig(default_categories: list) -> None:
    """EC-33: 'preforming jig' scores higher than the generic 'jig' in Tools."""
    result = categories.categorize("Cable Preforming Jig", default_categories)
    assert result == "16 - Work Fixtures and Tooling"


def test_distinctive_work_spare_keyword(default_categories: list) -> None:
    """Distinctive 'jam nut' routes to Work Spare Parts."""
    result = categories.categorize("ME12 JamNut Adapter", default_categories)
    assert result == "17 - Work Spare Parts"


def test_no_keyword_match_falls_back_to_uncategorized(
    default_categories: list,
) -> None:
    """EC-26: names with no keyword match go to Uncategorized."""
    result = categories.categorize(
        "Random Thing With No Keywords", default_categories
    )
    assert result == "Uncategorized"


def test_tie_breaks_to_lowest_category_number(default_categories: list) -> None:
    """When scores tie, the lowest-numbered category wins (deterministic)."""
    # 'model' appears in Models and Display; ensure deterministic output
    result = categories.categorize("Display Model", default_categories)
    assert result == "8 - Models and Display"


def test_empty_category_list_returns_uncategorized() -> None:
    """With no categories configured, everything is Uncategorized."""
    assert categories.categorize("Ender 3 Fan Duct", []) == "Uncategorized"
