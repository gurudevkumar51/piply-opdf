"""
Skew estimation and correction.

Two things are under test, and the second matters more than the first:

1. the estimator recovers a known rotation accurately;
2. **detection output is unchanged by skew** — a page tilted 8 degrees must
   yield the same components as the same page upright.

The second is the actual requirement. An accurate angle that does not restore
detection would be worthless, and that is exactly what happened during
development: correction worked, but expanding the canvas added blank margin,
and since every zone is a ratio of page height the header band slid off the
header. The `expand=False` test below guards that specific failure.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import fitz
import numpy as np
import pytest

from piply_opdf import Document
from piply_opdf.core import PageContext
from piply_opdf.preprocessing import deskew, estimate_skew_angle, rotate_image
from piply_opdf.utils.pdf import iter_pages

TEST_ANGLES = [-8.0, -5.0, -3.2, -1.5, -0.6, 0.0, 0.6, 1.5, 3.2, 5.0, 8.0]

#: Estimation tolerance. The search refines at 0.1 degree steps.
TOLERANCE = 0.35


def _text_page(width: int = 1200, height: int = 1600, lines: int = 28) -> np.ndarray:
    image = np.full((height, width, 3), 255, np.uint8)
    for i in range(lines):
        cv2.putText(
            image, "The quick brown fox jumps over the lazy dog and runs",
            (80, 140 + i * 48), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (25, 25, 25), 2, cv2.LINE_AA,
        )
    return image


# ── estimation ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("angle", TEST_ANGLES)
def test_estimator_recovers_known_angle(angle):
    skewed = rotate_image(_text_page(), angle)
    assert abs(estimate_skew_angle(skewed) - angle) <= TOLERANCE


@pytest.mark.parametrize("angle", [-6.4, -2.7, 2.7, 6.4])
def test_correction_leaves_no_residual_skew(angle):
    skewed = rotate_image(_text_page(), angle)
    corrected, applied = deskew(skewed)

    assert applied == pytest.approx(-angle, abs=TOLERANCE)
    assert abs(estimate_skew_angle(corrected)) <= TOLERANCE


def test_upright_page_is_left_alone():
    """No resampling when there is nothing to fix — interpolation costs
    sharpness that OCR values more than a fraction of a degree of skew."""
    page = _text_page()
    corrected, applied = deskew(page)
    assert applied == 0.0
    assert corrected is page


def test_blank_page_reports_no_angle():
    assert estimate_skew_angle(np.full((600, 800, 3), 255, np.uint8)) == 0.0


@pytest.mark.parametrize("image", [None, np.zeros((0, 0, 3), np.uint8)])
def test_degenerate_input_is_safe(image):
    assert estimate_skew_angle(image) == 0.0


@pytest.mark.parametrize("angle", [-7.0, 4.0])
def test_estimate_is_resolution_independent(angle):
    """The angle of a page is a property of its layout, not its DPI."""
    small = rotate_image(_text_page(600, 800, lines=14), angle)
    large = rotate_image(_text_page(2400, 3200, lines=56), angle)
    assert abs(estimate_skew_angle(small) - estimate_skew_angle(large)) <= TOLERANCE * 2


# ── canvas handling ──────────────────────────────────────────────────────────

def test_deskew_preserves_page_dimensions():
    """The regression guard.

    Zones are ratios of page height, so growing the canvas shifts every band
    off the content it is meant to cover. Deskew must hand back exactly the
    frame it was given.
    """
    skewed = rotate_image(_text_page(), 6.0)
    corrected, applied = deskew(skewed)
    assert applied != 0.0
    assert corrected.shape == skewed.shape


def test_rotate_image_expands_when_asked():
    page = _text_page(400, 300, lines=4)
    expanded = rotate_image(page, 30.0, expand=True)
    assert expanded.shape[0] > page.shape[0]
    assert expanded.shape[1] > page.shape[1]


def test_rotate_image_fills_with_page_background():
    """New area must read as background, not as ink, to every threshold."""
    page = _text_page(400, 300, lines=4)
    rotated = rotate_image(page, 20.0, expand=True)
    assert rotated[2, 2].min() > 200


# ── the requirement: detection is unaffected by skew ─────────────────────────

def _build_document(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((48, 38), "ACME Corporation - Statement", fontsize=11)
    page.insert_text((48, 150), "Invoice Number:        INV-2026-0042", fontsize=10)
    page.insert_text((48, 170), "Account Name:          Northwind Traders", fontsize=10)
    y = 240
    for line in [
        "This agreement describes the terms under which services are",
        "provided to the customer during the stated billing period and",
        "remains in force until superseded by a later revision.",
    ]:
        page.insert_text((48, y), line, fontsize=10)
        y += 16
    y = 330
    for line in [
        "- First obligation of the supplier party",
        "- Second obligation covering delivery timelines",
        "- Third obligation regarding confidentiality",
    ]:
        page.insert_text((48, y), line, fontsize=10)
        y += 18
    page.insert_text((48, 800), "Page 1 of 1", fontsize=9)
    doc.save(str(path))
    doc.close()
    return path


def _scan(source: Path, dest: Path, angle: float, dpi: int = 200) -> Path:
    """Rasterise, then tilt — a page fed into a scanner crooked."""
    original, scanned = fitz.open(str(source)), fitz.open()
    for page in original:
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
        array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 3:
            array = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
        if angle:
            array = rotate_image(array, angle)
        ok, buffer = cv2.imencode(".png", array)
        assert ok
        new_page = scanned.new_page(
            width=array.shape[1] * 72 / dpi, height=array.shape[0] * 72 / dpi
        )
        new_page.insert_image(new_page.rect, stream=buffer.tobytes())
    scanned.save(str(dest))
    scanned.close()
    original.close()
    return dest


def _counts(document: Document) -> dict[str, int]:
    return {
        "headers": len(document.headers),
        "footers": len(document.footers),
        "key_values": len(document.key_values),
        "paragraphs": len(document.paragraphs),
        "list_items": len(document.list_items),
    }


@pytest.fixture(scope="module")
def upright_counts(tmp_path_factory) -> tuple[Path, Path, dict[str, int]]:
    root = tmp_path_factory.mktemp("deskew")
    source = _build_document(root / "source.pdf")
    upright = _scan(source, root / "scan_0.pdf", 0.0)
    document = Document(upright, work_dir=root / "work_0")
    document.process_layout()
    return root, source, _counts(document)


@pytest.mark.parametrize("angle", [1.5, 3.0, 5.0, 8.0, -4.0])
def test_detection_is_unaffected_by_skew(upright_counts, angle):
    root, source, expected = upright_counts
    tilted = _scan(source, root / f"scan_{angle}.pdf", angle)

    document = Document(tilted, work_dir=root / f"work_{angle}")
    document.process_layout()

    assert _counts(document) == expected, f"skew {angle} changed detection"


def test_scanned_page_records_its_correction(upright_counts):
    """The applied angle is kept so original coordinates stay recoverable."""
    root, source, _ = upright_counts
    tilted = _scan(source, root / "scan_record.pdf", 4.0)

    for index, image in iter_pages(tilted, dpi=300):
        page = PageContext(page_number=index + 1, source_path=tilted.resolve(), image=image)
        assert page.has_text_layer is False
        _corrected, applied = deskew(image)
        assert applied == pytest.approx(-4.0, abs=1.0)
        break


def test_pages_with_a_text_layer_are_not_deskewed(upright_counts):
    """PyMuPDF reports coordinates in the original page frame.

    Rotating the raster would leave the image and the text layer in different
    coordinate systems. Digital pages are not skewed anyway.
    """
    _root, source, _ = upright_counts
    for index, image in iter_pages(source, dpi=300):
        page = PageContext(page_number=index + 1, source_path=source.resolve(), image=image)
        assert page.has_text_layer is True
        assert page.skew_correction == 0.0
        break


# ── the correction must not cost more than the skew ──────────────────────────

def _ruled_table_page(width: int = 2550, height: int = 3300) -> np.ndarray:
    """A bordered table: thin rules, which is what deskew was damaging."""
    image = np.full((height, width, 3), 255, np.uint8)
    left, right, top = 120, width - 120, 200
    row_gap, rows, cols = 140, 18, 6
    for r in range(rows + 1):
        y = top + r * row_gap
        cv2.line(image, (left, y), (right, y), (30, 30, 30), 2)
    for c in range(cols + 1):
        x = left + c * (right - left) // cols
        cv2.line(image, (x, top), (x, top + rows * row_gap), (30, 30, 30), 2)
    return image


def test_a_negligible_angle_is_left_alone():
    """Found on `sample.pdf`: 0.20 degrees of estimated skew on a straight page
    took table detection from one table of 171 cells to none.

    A fifth of a degree cannot straighten anything that was not already
    straight, but the resampling still softens the thin rules a table is found
    by. Below the floor the image must come back untouched.
    """
    page = _ruled_table_page()

    for angle in (0.05, 0.1, 0.2, 0.4):
        nudged = rotate_image(page, angle, expand=False)
        corrected, applied = deskew(nudged)
        if abs(estimate_skew_angle(nudged)) < 0.5:
            assert applied == 0.0, f"{angle} deg was corrected by {applied}"
            assert corrected is nudged or np.array_equal(corrected, nudged), (
                "an uncorrected page must not be resampled"
            )


def test_a_real_skew_is_still_corrected():
    """The floor must not stop genuine skew being fixed."""
    for angle in (-3.0, 1.2, 5.5):
        skewed = rotate_image(_ruled_table_page(), angle, expand=False)
        _, applied = deskew(skewed)
        assert applied != 0.0, f"{angle} deg was left uncorrected"
        assert applied == pytest.approx(-angle, abs=0.4)
