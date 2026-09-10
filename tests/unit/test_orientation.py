"""
Page orientation: sideways or not.

The interesting assertions here are the **negative** ones. A wrong quarter turn
is catastrophic — it breaks every later stage at once — so the design refuses to
guess, and the tests check the refusals as carefully as the answers.

Two things are deliberately never claimed:

* which way up a page is (0 versus 180, or 90 versus 270), and
* an answer at all for a page with too little line structure.

See the module docstring in ``piply_opdf.quality.orientation`` for the four
measurements that were tried and rejected for the up/down question.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from piply_opdf.quality.orientation import (
    SIDEWAYS,
    UNDECIDED,
    UPRIGHT,
    correct_orientation,
    estimate_orientation,
)


def _text_page(width: int = 1200, height: int = 1600, lines: int = 34) -> np.ndarray:
    """A page of ordinary prose: clear bands of ink with gaps between."""
    page = np.full((height, width), 255, np.uint8)
    margin = width // 10
    spacing = (height - 2 * margin) // lines
    for row in range(lines):
        y = margin + row * spacing
        # Ragged right edge, so the page is not perfectly regular.
        end = width - margin - (row % 5) * (width // 14)
        cv2.rectangle(page, (margin, y), (end, y + spacing // 3), 40, -1)
    return page


def _blank_page(width: int = 1200, height: int = 1600) -> np.ndarray:
    return np.full((height, width), 255, np.uint8)


def _photograph(width: int = 1200, height: int = 1600) -> np.ndarray:
    """Smooth noise: no line structure in any direction."""
    rng = np.random.default_rng(4)
    image = (rng.random((height, width)) * 255).astype(np.uint8)
    return cv2.GaussianBlur(image, (31, 31), 0)


# ── the question it does answer ──────────────────────────────────────────────

def test_a_page_of_text_is_upright():
    assert estimate_orientation(_text_page()).verdict == UPRIGHT


def test_the_same_page_turned_is_sideways():
    turned = np.rot90(_text_page()).copy()
    assert estimate_orientation(turned).verdict == SIDEWAYS


@pytest.mark.parametrize("turns", [1, 3])
def test_both_quarter_turns_read_as_sideways(turns):
    turned = np.rot90(_text_page(), k=turns).copy()
    assert estimate_orientation(turned).verdict == SIDEWAYS


def test_verdict_survives_a_colour_page():
    colour = cv2.cvtColor(_text_page(), cv2.COLOR_GRAY2BGR)
    assert estimate_orientation(colour).verdict == UPRIGHT


@pytest.mark.parametrize("size", [(600, 800), (1700, 2200), (2550, 3300)])
def test_verdict_does_not_depend_on_resolution(size):
    """Orientation is a property of the layout, not the pixel count."""
    width, height = size
    page = _text_page(width, height, lines=max(12, height // 48))
    assert estimate_orientation(page).verdict == UPRIGHT
    assert estimate_orientation(np.rot90(page).copy()).verdict == SIDEWAYS


# ── the questions it refuses ─────────────────────────────────────────────────

def test_a_sideways_page_offers_both_turns_and_asks_for_a_person():
    """Which of the two turns is needed cannot be decided from ink alone.

    Four measurements were tried and rejected — the best managed 2/8, worse
    than chance. Guessing would turn one page in four upside down.
    """
    estimate = estimate_orientation(np.rot90(_text_page()).copy())

    assert estimate.verdict == SIDEWAYS
    assert estimate.candidates == (90, 270), "both turns must be offered"
    assert estimate.needs_review, "a person has to choose the direction"


def test_an_upright_page_needs_no_review():
    estimate = estimate_orientation(_text_page())
    assert not estimate.needs_review
    assert estimate.candidates == ()


@pytest.mark.parametrize("page", [_blank_page(), _photograph()])
def test_a_page_without_line_structure_is_undecided(page):
    """A photograph or a blank sheet has no answer. Saying so beats guessing."""
    estimate = estimate_orientation(page)
    assert estimate.verdict == UNDECIDED
    assert estimate.needs_review


def test_degenerate_input_does_not_crash():
    for bad in (None, np.zeros((0, 0), np.uint8)):
        assert estimate_orientation(bad).verdict == UNDECIDED


# ── correction ───────────────────────────────────────────────────────────────

def test_nothing_is_rotated_without_an_explicit_instruction():
    """The image must come back untouched while the direction is unknown."""
    turned = np.rot90(_text_page()).copy()
    result, estimate = correct_orientation(turned)

    assert estimate.verdict == SIDEWAYS
    assert result is turned, "a sideways page must not be turned on a guess"


def test_a_chosen_rotation_is_applied_exactly():
    page = _text_page()
    result, _ = correct_orientation(page, rotation=90)

    assert result.shape[:2] == page.shape[:2][::-1]
    # np.rot90 is exact: turning back must restore the original bit for bit.
    assert np.array_equal(np.rot90(result, k=-1), page)


def test_a_zero_rotation_does_not_copy():
    page = _text_page()
    result, _ = correct_orientation(page, rotation=0)
    assert result is page


def test_correcting_a_sideways_page_makes_it_upright():
    turned = np.rot90(_text_page()).copy()
    corrected, _ = correct_orientation(turned, rotation=90)
    assert estimate_orientation(corrected).verdict == UPRIGHT
