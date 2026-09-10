"""
The three images a page is carried through as: original, structural, working.

The rules being protected here:

* the original is **never** modified;
* layout reads the structural image, so enhancement cannot damage what table
  detection depends on;
* enhancement that destroys line structure is **discarded**;
* nothing is turned a quarter turn on a guess.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from piply_opdf.quality.images import build_page_images, structure_evidence
from piply_opdf.quality.orientation import SIDEWAYS


def _ruled_page(width: int = 1400, height: int = 1800) -> np.ndarray:
    """A bordered table: thin rules, which is what enhancement can destroy."""
    page = np.full((height, width, 3), 255, np.uint8)
    left, right, top = 100, width - 100, 150
    rows, cols, row_h = 16, 6, 90
    for r in range(rows + 1):
        y = top + r * row_h
        cv2.line(page, (left, y), (right, y), (30, 30, 30), 2)
    for c in range(cols + 1):
        x = left + c * (right - left) // cols
        cv2.line(page, (x, top), (x, top + rows * row_h), (30, 30, 30), 2)
    for r in range(rows):
        for c in range(cols):
            cv2.putText(page, f"{r}-{c}",
                        (left + c * (right - left) // cols + 8, top + r * row_h + 58),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 40, 40), 2)
    return page


def _text_page(width: int = 1200, height: int = 1600) -> np.ndarray:
    """Prose set in real glyphs, with the margins a real page has.

    Two things this fixture has to get right at once:

    * **not ruled** — a filled bar *is* a long horizontal run, so a page of
      bars scores as pure ruled structure and would make ``structure_evidence``
      look broken when it is behaving correctly;
    * **strongly banded** — enough contrast between glyph rows and the gaps
      between them to read as upright.

    Even so it measures about 1.85 on the line-variation ratio, against 2.0-2.7
    for the real sample documents. Drawn text is a weaker signal than print.
    """
    page = np.full((height, width, 3), 255, np.uint8)
    margin = width // 6
    body = "the quick brown fox jumps over the lazy dog "
    spacing = (height - 2 * margin) // 24

    y, row = margin, 0
    while y < height - margin:
        length = 44 if row % 6 == 0 else 78          # a ragged right edge
        cv2.putText(page, (body * 8)[:length], (margin, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (25, 25, 25), 2, cv2.LINE_AA)
        y += spacing
        row += 1
    return page


# ── the original is untouchable ──────────────────────────────────────────────

def test_the_original_is_never_modified():
    page = _ruled_page()
    before = page.copy()

    images = build_page_images(page, enhance=lambda im: cv2.GaussianBlur(im, (5, 5), 0))

    assert images.original is page
    assert np.array_equal(page, before), "the source image was written to"


def test_without_enhancement_working_is_the_structural_image():
    """No copy, no processing, no risk — the same array, not an equal one."""
    images = build_page_images(_text_page())
    assert images.working is images.structural
    assert not images.was_enhanced


# ── enhancement is judged, not trusted ───────────────────────────────────────

def test_enhancement_that_destroys_structure_is_discarded():
    """The reason layout does not read the enhanced image.

    Measured on `sample.pdf`: the enhanced page lost a 171-cell table at 0.05
    degrees of rotation where the unenhanced page survived 2 degrees. Here the
    same effect is forced — an "enhancement" that erases the rules.
    """
    page = _ruled_page()

    def destroys_rules(image):
        # Aggressive opening removes the thin lines and keeps the glyphs.
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(cv2.morphologyEx(
            grey, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)), cv2.COLOR_GRAY2BGR)

    images = build_page_images(page, enhance=destroys_rules)

    assert not images.was_enhanced, "structure-destroying enhancement was kept"
    assert images.notes["enhancement"] == "rejected: destroyed line structure"
    assert images.notes["structure_after"] < images.notes["structure_before"]


def test_harmless_enhancement_is_kept():
    page = _ruled_page()
    images = build_page_images(page, enhance=lambda im: cv2.convertScaleAbs(im, alpha=1.05))

    assert images.was_enhanced
    assert images.notes["enhancement"] == "kept"


def test_a_failing_enhancement_does_not_stop_the_page():
    def explodes(_image):
        raise RuntimeError("bad page")

    images = build_page_images(_text_page(), enhance=explodes)

    assert not images.was_enhanced
    assert "failed" in str(images.notes["enhancement"])


def test_enhancement_returning_nothing_is_survivable():
    images = build_page_images(_text_page(), enhance=lambda _im: None)
    assert not images.was_enhanced


# ── structure evidence ───────────────────────────────────────────────────────

def test_structure_evidence_sees_rules():
    ruled = structure_evidence(_ruled_page())
    prose = structure_evidence(_text_page())
    assert ruled > prose, f"ruled={ruled:.4f} prose={prose:.4f}"


def test_structure_evidence_of_a_blank_page_is_zero():
    assert structure_evidence(np.full((400, 400, 3), 255, np.uint8)) == 0.0


# ── orientation ──────────────────────────────────────────────────────────────

def test_a_sideways_page_is_reported_but_not_turned():
    """The direction cannot be decided from ink, so nothing is turned on a guess."""
    turned = np.rot90(_text_page()).copy()
    images = build_page_images(turned)

    assert images.orientation.verdict == SIDEWAYS
    assert images.needs_orientation_review
    assert not images.orientation_applied
    assert images.structural.shape == turned.shape, "the page was rotated without being asked"


def test_a_chosen_rotation_is_applied():
    turned = np.rot90(_text_page()).copy()
    images = build_page_images(turned, orientation_rotation=90)

    assert images.orientation_applied
    assert images.structural.shape[:2] == turned.shape[:2][::-1]


def test_a_page_with_a_text_layer_is_not_deskewed():
    """PyMuPDF reports text in the original frame; rotating would desynchronise."""
    images = build_page_images(_text_page(), has_text_layer=True)
    assert images.skew_corrected == 0.0
    assert images.structural is images.original


def test_degenerate_input_is_rejected_clearly():
    with pytest.raises(ValueError):
        build_page_images(None)


# ── wired into the pipeline ──────────────────────────────────────────────────

def test_layout_survives_a_document_that_has_been_enhanced(tmp_path):
    """The regression this whole change exists to prevent.

    `run_all()` enhances, then detects. When layout read the *enhanced* PDF,
    `sample.pdf` went from one table of 171 cells to none: sharpening for
    legibility thinned the hairline rules the table is found by.

    Layout now reads the structural image — orientation and deskew only — so
    enhancement cannot take the table away.
    """
    import fitz

    from piply_opdf import Document

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    left, top, row_h, col_w, cols, rows = 50, 90, 26, 92, 5, 14
    for r in range(rows + 1):
        y = top + r * row_h
        page.draw_line(fitz.Point(left, y), fitz.Point(left + cols * col_w, y), width=0.6)
    for c in range(cols + 1):
        x = left + c * col_w
        page.draw_line(fitz.Point(x, top), fitz.Point(x, top + rows * row_h), width=0.6)
    for r in range(rows):
        for c in range(cols):
            page.insert_text((left + c * col_w + 5, top + r * row_h + 17),
                             f"R{r}C{c}", fontsize=7)
    pdf = tmp_path / "ruled.pdf"
    doc.save(str(pdf))
    doc.close()

    document = Document(pdf, work_dir=tmp_path / "work")
    document.assess()
    document.enhance()                     # produces the enhanced PDF
    document.process_layout()              # must still read the original

    assert document.tables, "the table was lost after enhancement"
    assert document.tables[0].cells, "the table came back with no cells"


def test_the_pipeline_records_the_three_images(tmp_path):
    """`page_images` is how OCR later finds the enhanced copy."""
    import fitz

    from piply_opdf import Document

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for row in range(20):
        page.insert_text((60, 90 + row * 22), "the quick brown fox jumps", fontsize=10)
    pdf = tmp_path / "prose.pdf"
    doc.save(str(pdf))
    doc.close()

    document = Document(pdf, work_dir=tmp_path / "work2")
    document.process_layout()

    assert document.page_images, "no page images were recorded"
    images = document.page_images[1]
    assert images.original is not None
    assert images.structural is not None
    assert images.working is not None
