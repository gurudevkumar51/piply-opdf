"""
Header/footer detection across page geometries, render resolutions, and both
digital and scanned inputs.

The corpus is generated in-process rather than committed as fixture files, so
these tests assert on *generic* behaviour: nothing here is tuned to a
particular document. Page sizes span portrait, landscape, A4/A5/Letter/Legal;
render DPI spans 150-600; and every document is tested twice - once with its
text layer, once rasterised so no text layer exists at all.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from piply_opdf.core import PageContext
from piply_opdf.detectors.footer import CvFooterStrategy, FooterDetector, TextFooterStrategy
from piply_opdf.detectors.header import CvHeaderStrategy, HeaderDetector, TextHeaderStrategy
from piply_opdf.utils.pdf import iter_pages

# (name, width_pt, height_pt) - portrait, landscape, and small formats
PAGE_SIZES = [
    ("a4", 595, 842),
    ("letter", 612, 792),
    ("legal", 612, 1008),
    ("a4_landscape", 842, 595),
    ("a5", 420, 595),
]

RENDER_DPIS = [150, 300, 600]


def _build_pdf(path: Path, width: float, height: float, *, header: bool, footer: bool) -> Path:
    """Write a single-page PDF with body text, optionally with header/footer.

    All positions are fractions of the page box so the same generator produces
    sensible documents at any page size.
    """
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)

    if header:
        page.insert_text((width * 0.08, height * 0.045), "ACME Corporation - Quarterly Report", fontsize=11)
        page.insert_text((width * 0.08, height * 0.075), "Confidential - Internal Use Only", fontsize=9)

    for i in range(12):
        page.insert_text(
            (width * 0.08, height * 0.30 + i * (height * 0.030)),
            f"Body line {i + 1}: the quick brown fox jumps over the lazy dog.",
            fontsize=10,
        )

    if footer:
        page.insert_text((width * 0.08, height * 0.945), "Page 1 of 3", fontsize=9)
        page.insert_text((width * 0.55, height * 0.945), "Printed 2026-08-15", fontsize=9)

    doc.save(str(path))
    doc.close()
    return path


def _rasterise(src: Path, dest: Path, dpi: int = 200) -> Path:
    """Produce a scanned-equivalent PDF: same visual page, zero text layer."""
    original = fitz.open(str(src))
    scanned = fitz.open()
    for page in original:
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
        new_page = scanned.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=pix.tobytes("png"))
    scanned.save(str(dest))
    scanned.close()
    original.close()
    return dest


def _first_page(path: Path, dpi: int) -> PageContext:
    for index, image in iter_pages(path, dpi=dpi):
        return PageContext(page_number=index + 1, source_path=path.resolve(), image=image, dpi=dpi)
    raise AssertionError(f"{path} produced no pages")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> dict[str, Path]:
    """Digital and scanned variants for every page size and header/footer combo."""
    root = tmp_path_factory.mktemp("corpus")
    built: dict[str, Path] = {}

    for name, width, height in PAGE_SIZES:
        digital = _build_pdf(root / f"{name}.pdf", width, height, header=True, footer=True)
        built[name] = digital
        built[f"{name}__scanned"] = _rasterise(digital, root / f"{name}_scanned.pdf")

    w, h = 612, 792
    for label, has_header, has_footer in [
        ("no_header", False, True),
        ("no_footer", True, False),
        ("neither", False, False),
    ]:
        digital = _build_pdf(root / f"{label}.pdf", w, h, header=has_header, footer=has_footer)
        built[label] = digital
        built[f"{label}__scanned"] = _rasterise(digital, root / f"{label}_scanned.pdf")

    return built


# ── strategy selection ───────────────────────────────────────────────────────

@pytest.mark.parametrize("size_name", [s[0] for s in PAGE_SIZES])
def test_digital_pdf_uses_text_strategy(corpus, size_name):
    page = _first_page(corpus[size_name], dpi=300)
    assert page.has_text_layer is True
    assert isinstance(HeaderDetector().select_strategy(page), TextHeaderStrategy)
    assert isinstance(FooterDetector().select_strategy(page), TextFooterStrategy)


@pytest.mark.parametrize("size_name", [s[0] for s in PAGE_SIZES])
def test_scanned_pdf_falls_back_to_cv_strategy(corpus, size_name):
    """The regression behind issue 4: no text layer must not mean no detection."""
    page = _first_page(corpus[f"{size_name}__scanned"], dpi=300)
    assert page.has_text_layer is False
    assert isinstance(HeaderDetector().select_strategy(page), CvHeaderStrategy)
    assert isinstance(FooterDetector().select_strategy(page), CvFooterStrategy)


# ── detection outcomes ───────────────────────────────────────────────────────

@pytest.mark.parametrize("size_name", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", ["", "__scanned"])
@pytest.mark.parametrize("dpi", RENDER_DPIS)
def test_header_and_footer_found_at_any_size_and_dpi(corpus, size_name, variant, dpi):
    page = _first_page(corpus[f"{size_name}{variant}"], dpi=dpi)

    headers = HeaderDetector().detect(page)
    footers = FooterDetector().detect(page)

    assert headers, f"no header for {size_name}{variant} at {dpi} DPI"
    assert footers, f"no footer for {size_name}{variant} at {dpi} DPI"


@pytest.mark.parametrize("variant", ["", "__scanned"])
def test_absent_header_is_not_invented(corpus, variant):
    page = _first_page(corpus[f"no_header{variant}"], dpi=300)
    assert HeaderDetector().detect(page) == []
    assert FooterDetector().detect(page)


@pytest.mark.parametrize("variant", ["", "__scanned"])
def test_absent_footer_is_not_invented(corpus, variant):
    page = _first_page(corpus[f"no_footer{variant}"], dpi=300)
    assert FooterDetector().detect(page) == []
    assert HeaderDetector().detect(page)


@pytest.mark.parametrize("variant", ["", "__scanned"])
def test_body_only_page_yields_neither(corpus, variant):
    page = _first_page(corpus[f"neither{variant}"], dpi=300)
    assert HeaderDetector().detect(page) == []
    assert FooterDetector().detect(page) == []


# ── geometry invariants ──────────────────────────────────────────────────────

@pytest.mark.parametrize("size_name", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", ["", "__scanned"])
def test_regions_land_in_their_zone_and_inside_the_page(corpus, size_name, variant):
    page = _first_page(corpus[f"{size_name}{variant}"], dpi=300)

    for header in HeaderDetector().detect(page):
        assert header.bbox.y >= 0
        assert header.bbox.y1 <= page.height
        assert header.bbox.x1 <= page.width
        assert header.bbox.center[1] < page.height * 0.5, "header drifted below the top half"

    for footer in FooterDetector().detect(page):
        assert footer.bbox.y1 <= page.height
        assert footer.bbox.x1 <= page.width
        assert footer.bbox.center[1] > page.height * 0.5, "footer drifted above the bottom half"


@pytest.mark.parametrize("size_name", [s[0] for s in PAGE_SIZES])
def test_scanned_regions_are_marked_for_ocr(corpus, size_name):
    """CV strategies locate geometry only; text must come from the OCR phase."""
    page = _first_page(corpus[f"{size_name}__scanned"], dpi=300)
    for component in HeaderDetector().detect(page) + FooterDetector().detect(page):
        assert component.text == ""
        assert component.metadata.get("needs_ocr") is True


@pytest.mark.parametrize("size_name", [s[0] for s in PAGE_SIZES])
def test_digital_regions_carry_text_without_ocr(corpus, size_name):
    page = _first_page(corpus[size_name], dpi=300)
    headers = HeaderDetector().detect(page)
    assert headers
    assert any(h.text.strip() for h in headers)
    assert all(not h.metadata.get("needs_ocr") for h in headers)


# ── exclusions ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variant", ["", "__scanned"])
def test_exclusions_suppress_regions(corpus, variant):
    """A claimed region (e.g. a detected table) must not resurface as a header."""
    from piply_opdf.core import BBox

    page = _first_page(corpus[f"letter{variant}"], dpi=300)
    whole_page = [BBox(0, 0, page.width, page.height)]

    assert HeaderDetector().detect(page, whole_page) == []
    assert FooterDetector().detect(page, whole_page) == []


def test_ordinals_are_serial_and_gap_free(corpus):
    """Ids must number 001, 002, ... per page with no gaps, whatever the source."""
    for key in ("letter", "letter__scanned"):
        page = _first_page(corpus[key], dpi=300)
        for components in (HeaderDetector().detect(page), FooterDetector().detect(page)):
            suffixes = [int(c.id.rsplit("_", 1)[1]) for c in components]
            assert suffixes == list(range(1, len(components) + 1)), f"{key}: {suffixes}"
