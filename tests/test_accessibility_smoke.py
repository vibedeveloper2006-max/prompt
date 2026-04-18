"""
tests/test_accessibility_smoke.py
---------------------------------
Validates that the frontend index.html meets basic WCAG/ARIA standards.
"""

import os
import pytest
from bs4 import BeautifulSoup


@pytest.fixture
def index_soup():
    path = os.path.join(os.getcwd(), "frontend", "index.html")
    with open(path, "r", encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")


def test_has_main_landmark(index_soup):
    """Ensures at least one <main> landmark exists."""
    main = index_soup.find("main")
    assert main is not None
    assert main.has_attr("id")


def test_has_h1_header(index_soup):
    """Ensures a single semantic H1 exists for page context."""
    h1s = index_soup.find_all("h1")
    assert len(h1s) == 1


def test_form_controls_have_labels(index_soup):
    """Ensures all interactive inputs/selects have associated labels or ARIA labels."""
    inputs = index_soup.find_all(["input", "select"])
    for control in inputs:
        # Check if it's hidden or decorative
        if control.get("type") == "hidden":
            continue

        # Check for explicit 'id' + <label for="...">
        control_id = control.get("id")
        if control_id:
            label = index_soup.find("label", attrs={"for": control_id})
            if label:
                continue

        # Check for aria-label or aria-labelledby
        if control.has_attr("aria-label") or control.has_attr("aria-labelledby"):
            continue

        pytest.fail(
            f"Form control {control} is missing a text label or ARIA descriptor."
        )


def test_images_have_alt_text(index_soup):
    """Ensures all images have alt attributes (even if empty for decorative)."""
    imgs = index_soup.find_all("img")
    for img in imgs:
        assert img.has_attr("alt"), f"Image {img} missing alt attribute."


def test_has_nav_landmark(index_soup):
    """Ensures navigation landmark is semantic."""
    nav = index_soup.find("nav")
    assert nav is not None
    assert nav.has_attr("aria-label")


def test_has_footer_landmark(index_soup):
    """Ensures footer landmark is semantic."""
    footer = index_soup.find("footer")
    assert footer is not None
