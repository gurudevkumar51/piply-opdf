"""
Stage 2: splitting detected layout regions into review units.

Asserts the unit hierarchy from ``wiki/business_rules.md`` holds for both
digital and scanned inputs:

    PARAGRAPH -> SENTENCE -> WORD
    HEADER / FOOTER / TITLE / LIST_ITEM -> WORD
    KEY_VALUE -> KEY / SEPARATOR / VALUE

Header and footer reaching WORD is the fix for those regions being detected but
never appearing as reviewable units.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

import piply_opdf.segmentation  # noqa: F401  (registers segmenters)
from piply_opdf.core import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.core.segmenter import segment_tree, segmenter_registry
from piply_opdf.detectors.footer import FooterDetector
from piply_opdf.detectors.header import HeaderDetector
from piply_opdf.detectors.key_value import KeyValueDetector
from piply_opdf.detectors.paragraph import ParagraphDetector
from piply_opdf.utils.pdf import iter_pages

PAGE_SIZES = [("a4", 595, 842), ("letter", 612, 792)]


def _build(path: Path, width: float, height: float) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    fs = max(8.0, height * 0.013)
    gap = " " * 8

    page.insert_text((width * 0.08, height * 0.05), "ACME Corporation Statement", fontsize=fs)
    page.insert_text((width * 0.08, height * 0.18), f"Invoice Number:{gap}INV-2026-0042", fontsize=fs)

    y = height * 0.32
    for line in [
        "This agreement describes the terms under which services are",
        "provided to the customer during the stated billing period and",
        "remains in force until superseded by a later revision.",
    ]:
        page.insert_text((width * 0.08, y), line, fontsize=fs)
        y += height * 0.024

    page.insert_text((width * 0.08, height * 0.95), "Page 1 of 1", fontsize=fs * 0.85)
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


def _page(path: Path, dpi: int = 300) -> PageContext:
    for index, image in iter_pages(path, dpi=dpi):
        return PageContext(page_number=index + 1, source_path=path.resolve(), image=image, dpi=dpi)
    raise AssertionError(f"{path} produced no pages")


@pytest.fixture(scope="module")
def pairs(tmp_path_factory) -> dict[str, tuple[Path, Path]]:
    root = tmp_path_factory.mktemp("segmentation")
    out: dict[str, tuple[Path, Path]] = {}
    for name, w, h in PAGE_SIZES:
        digital = _build(root / f"{name}.pdf", w, h)
        out[name] = (digital, _rasterise(digital, root / f"{name}_scanned.pdf"))
    return out


# ── registry ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "component_type",
    [
        ComponentType.PARAGRAPH, ComponentType.SENTENCE, ComponentType.HEADER,
        ComponentType.FOOTER, ComponentType.TITLE, ComponentType.LIST_ITEM,
        ComponentType.KEY_VALUE,
    ],
)
def test_segmenter_registered_for_splittable_types(component_type):
    assert segmenter_registry.is_registered(component_type)


@pytest.mark.parametrize("component_type", [ComponentType.WORD, ComponentType.CELL])
def test_terminal_units_have_no_segmenter(component_type):
    """WORD and CELL are the smallest units — recursion must stop there."""
    assert segmenter_registry.create(component_type) is None


# ── header / footer reach WORD ───────────────────────────────────────────────

@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1])
def test_header_and_footer_split_into_words(pairs, size, variant):
    page = _page(pairs[size][variant])

    for detector in (HeaderDetector(), FooterDetector()):
        found = detector.detect(page)
        assert found, f"{detector.component_type} not detected"
        for component in found:
            segment_tree(component, page)
            assert component.children, f"{component.id} produced no units"
            assert all(c.type == ComponentType.WORD for c in component.children)


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
def test_word_counts_match_between_digital_and_scanned(pairs, size):
    """The same visual document must yield the same units either way."""
    digital, scanned = pairs[size]

    counts = []
    for path in (digital, scanned):
        page = _page(path)
        footers = FooterDetector().detect(page)
        assert footers
        segment_tree(footers[0], page)
        counts.append(len(footers[0].children))

    assert counts[0] == counts[1], f"digital {counts[0]} vs scanned {counts[1]} words"


# ── paragraph -> sentence -> word ────────────────────────────────────────────

@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1])
def test_paragraph_splits_to_sentences_then_words(pairs, size, variant):
    page = _page(pairs[size][variant])
    paragraphs = [
        c for c in ParagraphDetector().detect(page) if c.type == ComponentType.PARAGRAPH
    ]
    assert paragraphs, "no multi-line paragraph detected"

    paragraph = paragraphs[0]
    paragraph.children = []          # discard detector-attached words
    paragraph.metadata.pop("key", None)
    segment_tree(paragraph, page)

    assert paragraph.children
    assert all(c.type == ComponentType.SENTENCE for c in paragraph.children)
    assert any(s.children for s in paragraph.children), "sentences never reached words"
    for sentence in paragraph.children:
        assert all(w.type == ComponentType.WORD for w in sentence.children)


# ── key_value -> key / separator / value ─────────────────────────────────────

@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1])
def test_key_value_splits_into_three_roles(pairs, size, variant):
    page = _page(pairs[size][variant])
    pairs_found = KeyValueDetector().detect(page)
    assert pairs_found, "no key-value detected"

    component = pairs_found[0]
    segment_tree(component, page)

    roles = [c.metadata.get("role") for c in component.children]
    assert roles == ["key", "separator", "value"], roles

    key, separator, value = component.children
    assert key.bbox.x1 <= separator.bbox.x
    assert separator.bbox.x1 <= value.bbox.x


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
def test_digital_key_value_units_carry_text(pairs, size):
    page = _page(pairs[size][0])
    component = KeyValueDetector().detect(page)[0]
    segment_tree(component, page)

    by_role = {c.metadata["role"]: c for c in component.children}
    assert by_role["key"].text
    assert by_role["value"].text
    assert by_role["separator"].text in (":", "=")


# ── recursion safety ─────────────────────────────────────────────────────────

def test_segment_tree_respects_max_depth(pairs):
    page = _page(pairs["a4"][0])
    paragraphs = [
        c for c in ParagraphDetector().detect(page) if c.type == ComponentType.PARAGRAPH
    ]
    paragraph = paragraphs[0]
    paragraph.children = []

    segment_tree(paragraph, page, max_depth=1)
    # One level only: sentences exist, but they must not have been expanded.
    assert paragraph.children
    assert all(not s.children for s in paragraph.children)


def test_segment_tree_is_safe_on_unsplittable_component(pairs):
    page = _page(pairs["a4"][0])
    orphan = DetectedComponent(
        id="word_001_001",
        type=ComponentType.WORD,
        page=1,
        bbox=BBox(10, 10, 50, 20),
        text="hello",
    )
    assert segment_tree(orphan, page).children == []
