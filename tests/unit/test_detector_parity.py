"""
Digital/scanned parity for the strategy-based detectors.

The guarantee under test: a document and its rasterised twin — visually
identical, one with a text layer and one without — must yield the *same*
components. That is the whole point of the text/CV strategy split, and it is
the regression that would reappear if a CV fallback were dropped or mistuned.

As with the header/footer suite, the corpus is generated in-process at several
page sizes and render resolutions, so nothing here is tuned to one file.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from piply_opdf.core import ComponentType, PageContext
from piply_opdf.detectors.key_value import CvKeyValueStrategy, KeyValueDetector, TextKeyValueStrategy
from piply_opdf.detectors.list_item import CvListItemStrategy, ListItemDetector, TextListItemStrategy
from piply_opdf.detectors.paragraph import CvParagraphStrategy, ParagraphDetector, TextParagraphStrategy
from piply_opdf.utils.pdf import iter_pages

PAGE_SIZES = [("a4", 595, 842), ("letter", 612, 792), ("a5", 420, 595)]
RENDER_DPIS = [200, 300, 400]


def _build(path: Path, width: float, height: float) -> Path:
    """A page with key-values, a prose paragraph and a bullet list."""
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    fs = max(7.0, height * 0.012)
    gap = " " * 8

    page.insert_text((width * 0.08, height * 0.18), f"Invoice Number:{gap}INV-2026-0042", fontsize=fs)
    page.insert_text((width * 0.08, height * 0.21), f"Account Name:{gap}Northwind Traders", fontsize=fs)

    y = height * 0.30
    for line in [
        "This agreement describes the terms under which services are",
        "provided to the customer during the stated billing period and",
        "remains in force until superseded by a later revision.",
    ]:
        page.insert_text((width * 0.08, y), line, fontsize=fs)
        y += height * 0.022

    y = height * 0.44
    for line in [
        "- First obligation of the supplier party",
        "- Second obligation covering delivery timelines",
        "- Third obligation regarding confidentiality",
    ]:
        page.insert_text((width * 0.08, y), line, fontsize=fs)
        y += height * 0.024

    doc.save(str(path))
    doc.close()
    return path


def _rasterise(src: Path, dest: Path, dpi: int = 200) -> Path:
    original, scanned = fitz.open(str(src)), fitz.open()
    for page in original:
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
        new_page = scanned.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=pix.tobytes("png"))
    scanned.save(str(dest))
    scanned.close()
    original.close()
    return dest


def _page(path: Path, dpi: int) -> PageContext:
    for index, image in iter_pages(path, dpi=dpi):
        return PageContext(page_number=index + 1, source_path=path.resolve(), image=image, dpi=dpi)
    raise AssertionError(f"{path} produced no pages")


@pytest.fixture(scope="module")
def pairs(tmp_path_factory) -> dict[str, tuple[Path, Path]]:
    root = tmp_path_factory.mktemp("parity")
    out: dict[str, tuple[Path, Path]] = {}
    for name, w, h in PAGE_SIZES:
        digital = _build(root / f"{name}.pdf", w, h)
        out[name] = (digital, _rasterise(digital, root / f"{name}_scanned.pdf"))
    return out


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
def test_strategy_selection_differs_by_input(pairs, size):
    digital, scanned = pairs[size]
    dp, sp = _page(digital, 300), _page(scanned, 300)

    assert isinstance(ParagraphDetector().select_strategy(dp), TextParagraphStrategy)
    assert isinstance(ParagraphDetector().select_strategy(sp), CvParagraphStrategy)
    assert isinstance(KeyValueDetector().select_strategy(dp), TextKeyValueStrategy)
    assert isinstance(KeyValueDetector().select_strategy(sp), CvKeyValueStrategy)
    assert isinstance(ListItemDetector().select_strategy(dp), TextListItemStrategy)
    assert isinstance(ListItemDetector().select_strategy(sp), CvListItemStrategy)


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("dpi", RENDER_DPIS)
def test_key_values_found_in_both_variants(pairs, size, dpi):
    digital, scanned = pairs[size]
    assert KeyValueDetector().detect(_page(digital, dpi)), f"digital {size}@{dpi}"
    assert KeyValueDetector().detect(_page(scanned, dpi)), f"scanned {size}@{dpi}"


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("dpi", RENDER_DPIS)
def test_list_items_found_in_both_variants(pairs, size, dpi):
    digital, scanned = pairs[size]
    assert ListItemDetector().detect(_page(digital, dpi)), f"digital {size}@{dpi}"
    assert ListItemDetector().detect(_page(scanned, dpi)), f"scanned {size}@{dpi}"


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("dpi", RENDER_DPIS)
def test_prose_found_in_both_variants(pairs, size, dpi):
    digital, scanned = pairs[size]
    for path in (digital, scanned):
        found = ParagraphDetector().detect(_page(path, dpi))
        assert found, f"{path.stem}@{dpi}"
        assert all(c.type in (ComponentType.PARAGRAPH, ComponentType.SENTENCE) for c in found)


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
def test_scanned_components_are_flagged_for_ocr(pairs, size):
    """CV strategies yield geometry only; text must come from the OCR phase."""
    _, scanned = pairs[size]
    page = _page(scanned, 300)
    for detector in (KeyValueDetector(), ListItemDetector(), ParagraphDetector()):
        for component in detector.detect(page):
            assert component.text == ""
            assert component.metadata.get("needs_ocr") is True


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
def test_digital_components_carry_text(pairs, size):
    digital, _ = pairs[size]
    page = _page(digital, 300)
    for detector in (KeyValueDetector(), ListItemDetector(), ParagraphDetector()):
        found = detector.detect(page)
        assert found and all(c.text.strip() for c in found)


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
def test_key_value_records_split_geometry_without_creating_units(pairs, size):
    """Detection locates the split; it must not create units itself.

    Unit creation belongs to the segmentation stage — a detector that attached
    children here would pre-empt ``segment_tree`` and the SEPARATOR unit would
    never be produced. See tests/unit/test_segmentation.py for the units.
    """
    from piply_opdf.core import BBox

    _, scanned = pairs[size]
    found = KeyValueDetector().detect(_page(scanned, 300))
    assert found

    for component in found:
        assert component.children == [], "detection must not create units"

        key = BBox.from_any(component.metadata.get("key_bbox"))
        value = BBox.from_any(component.metadata.get("value_bbox"))
        assert key is not None and value is not None
        assert key.x1 <= value.x, "key must sit left of value"


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1])
def test_ordinals_are_serial_and_gap_free(pairs, size, variant):
    page = _page(pairs[size][variant], 300)
    for detector in (KeyValueDetector(), ListItemDetector(), ParagraphDetector()):
        by_type: dict[str, list[int]] = {}
        for component in detector.detect(page):
            by_type.setdefault(component.type, []).append(component.index)
        for component_type, indices in by_type.items():
            assert indices == list(range(1, len(indices) + 1)), f"{component_type}: {indices}"


@pytest.mark.parametrize("size,w,h", PAGE_SIZES)
def test_prose_starting_with_short_words_is_not_a_list(tmp_path, size, w, h):
    """The CV marker gap is relative to text height, which is permissive.

    What keeps that from misreading prose as bullets is the requirement that a
    real list repeats the *same glyph* at the *same indent*. These lines all
    begin with a short word at a shared indent but with varying widths, so they
    must not be reported as list items.
    """
    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    fs = max(7.0, h * 0.012)
    y = h * 0.30
    for line in [
        "A customer may terminate this agreement at any time.",
        "I confirm the balance shown above is correct and due.",
        "We will notify the account holder before any change.",
        "It remains the responsibility of the supplier party.",
    ]:
        page.insert_text((w * 0.08, y), line, fontsize=fs)
        y += h * 0.024

    digital = tmp_path / f"prose_{size}.pdf"
    doc.save(str(digital))
    doc.close()
    scanned = _rasterise(digital, tmp_path / f"prose_{size}_scanned.pdf")

    assert ListItemDetector().detect(_page(digital, 300)) == []
    assert ListItemDetector().detect(_page(scanned, 300)) == []


def test_exclusions_suppress_all_detectors(pairs):
    from piply_opdf.core import BBox

    for variant in (0, 1):
        page = _page(pairs["letter"][variant], 300)
        whole = [BBox(0, 0, page.width, page.height)]
        assert KeyValueDetector().detect(page, whole) == []
        assert ListItemDetector().detect(page, whole) == []
        assert ParagraphDetector().detect(page, whole) == []
