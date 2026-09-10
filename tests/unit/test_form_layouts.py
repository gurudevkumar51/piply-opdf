"""
Form-shaped pages: multi-column key-value rows, and regions that look like
tables but are not.

Both scenarios come from real documents that were being read wrongly:

* a two-column lab-report header was reported as one PARAGRAPH instead of four
  key-value pairs;
* a scanned ID card and a photograph were reported as TABLEs, because a purely
  geometric grid test sees their rectangular edges and never asks whether the
  region contains text.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import fitz
import numpy as np
import pytest

import piply_opdf.segmentation  # noqa: F401  (registers segmenters)
from piply_opdf.core import ComponentType, PageContext
from piply_opdf.core.segmenter import segment_tree
from piply_opdf.detectors.key_value import KeyValueDetector
from piply_opdf.detectors.paragraph import ParagraphDetector
from piply_opdf.detectors.table import TableDetector
from piply_opdf.utils.pdf import iter_pages

# Four rows, two key-value pairs each — the shape of a lab-report header.
FORM_ROWS = [
    ("Ref. Dr.", "SELF-INSURANCE", "Collected On", "11-Feb-2026 11:58 AM"),
    ("Req No.", "PHC262862", "Registered On", "11-Feb-2026 11:57 AM"),
    ("Sample Type", "Plasma-R", "Reported On", "11-Feb-2026 04:30 PM"),
    ("Client Name", "MediBuddy Bajaj Allianz", "Client Code", "CMLVSPD10"),
]
EXPECTED_PAIRS = len(FORM_ROWS) * 2


def _build_form(path: Path, width: float = 595, height: float = 842) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    y = height * 0.14
    for key_a, value_a, key_b, value_b in FORM_ROWS:
        page.insert_text((width * 0.08, y), key_a, fontsize=9)
        page.insert_text((width * 0.22, y), f": {value_a}", fontsize=9)
        page.insert_text((width * 0.55, y), key_b, fontsize=9)
        page.insert_text((width * 0.72, y), f": {value_b}", fontsize=9)
        y += height * 0.021
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
def form_pair(tmp_path_factory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("forms")
    digital = _build_form(root / "form.pdf")
    return digital, _rasterise(digital, root / "form_scanned.pdf")


# ── multi-column key-value ───────────────────────────────────────────────────

@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_every_pair_in_a_two_column_form_is_found(form_pair, variant):
    page = _page(form_pair[variant])
    found = KeyValueDetector().detect(page)
    assert len(found) == EXPECTED_PAIRS, f"got {len(found)}: {[c.text for c in found]}"


@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_form_block_is_not_swallowed_by_paragraph(form_pair, variant):
    """The original bug: the whole block came back as one PARAGRAPH.

    Key-value runs before paragraph in the pipeline, so once the pairs are
    claimed there should be nothing prose-shaped left of them.
    """
    page = _page(form_pair[variant])
    claimed = [c.bbox for c in KeyValueDetector().detect(page)]
    remaining = ParagraphDetector().detect(page, claimed)
    paragraphs = [c for c in remaining if c.type == ComponentType.PARAGRAPH]
    assert not paragraphs, [c.text for c in paragraphs]


def test_colon_inside_a_time_is_not_a_field_separator(form_pair):
    """``11:58`` must not split into key="11-Feb-2026 11", value="58 AM"."""
    page = _page(form_pair[0])
    values = {c.metadata.get("value", "") for c in KeyValueDetector().detect(page)}
    assert any("11:58" in v for v in values), values
    keys = {c.metadata.get("key", "") for c in KeyValueDetector().detect(page)}
    assert not any(k.strip().endswith("11") for k in keys), keys


def test_abbreviated_keys_are_accepted(form_pair):
    """"Ref. Dr." and "Req No." end in a full stop but are ordinary labels."""
    page = _page(form_pair[0])
    keys = {c.metadata.get("key", "") for c in KeyValueDetector().detect(page)}
    assert "Ref. Dr." in keys, keys
    assert "Req No." in keys, keys


@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_each_pair_segments_into_three_roles(form_pair, variant):
    page = _page(form_pair[variant])
    for component in KeyValueDetector().detect(page):
        segment_tree(component, page)
        roles = [c.metadata.get("role") for c in component.children]
        assert roles == ["key", "separator", "value"], roles


def test_words_on_one_baseline_group_into_one_line(form_pair):
    """Separate PDF text blocks sharing a baseline must read as one line.

    Form rows are commonly emitted as several independent blocks; without
    baseline merging each fragment looks like its own line and no pairing is
    possible.
    """
    from piply_opdf.detectors.text_layer import extract_words, group_into_lines

    page = _page(form_pair[0])
    lines = group_into_lines(extract_words(page))
    # One visual line per form row, each carrying both pairs.
    assert len(lines) == len(FORM_ROWS), [ln.text for ln in lines]
    for line in lines:
        assert line.text.count(":") >= 2, line.text


# ── things that are not tables ───────────────────────────────────────────────

def _photo_page(path: Path, seed: int) -> Path:
    """A page whose only content is a photograph with strong rectangular edges."""
    rng = np.random.default_rng(seed)
    image = (rng.random((420, 320, 3)) * 255).astype(np.uint8)
    image = cv2.GaussianBlur(image, (9, 9), 0)
    cv2.rectangle(image, (4, 4), (316, 416), (30, 30, 30), 3)      # card border
    cv2.rectangle(image, (20, 40), (120, 180), (60, 60, 60), 2)    # photo box
    for i in range(5):                                             # printed rows
        cv2.line(image, (140, 60 + i * 28), (300, 60 + i * 28), (50, 50, 50), 2)

    ok, buffer = cv2.imencode(".png", image)
    assert ok

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(80, 120, 480, 640), stream=buffer.tobytes())
    doc.save(str(path))
    doc.close()
    return path


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_photograph_with_rectangular_edges_is_not_a_table(tmp_path, seed):
    """An ID card or photo has grid-like edges but no tabular text."""
    pdf = _photo_page(tmp_path / f"photo_{seed}.pdf", seed)
    page = _page(pdf)
    assert TableDetector().detect_tables(page.image) == []


def test_a_single_ink_table_is_not_rejected_as_a_stamp(tmp_path):
    """A bordered table printed in one ink must survive the content gate.

    A stamp is one colour with broken, fragmented edges. So is a bordered table
    printed in a single ink — its rules fragment the same way. Treating STAMP as
    disqualifying cost a real 575-cell invoice table on a live document.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    ink = (0.10, 0.16, 0.44)                     # a single non-black ink
    left, top, cell_w, cell_h = 50, 100, 100, 22
    for row in range(10):
        for col in range(5):
            rect = fitz.Rect(
                left + col * cell_w, top + row * cell_h,
                left + (col + 1) * cell_w, top + (row + 1) * cell_h,
            )
            page.draw_rect(rect, color=ink, width=0.7)
            page.insert_text((rect.x0 + 4, rect.y0 + 15), f"{row}-{col}", fontsize=7, color=ink)
    pdf = tmp_path / "single_ink_table.pdf"
    doc.save(str(pdf))
    doc.close()

    page_ctx = _page(pdf)
    assert TableDetector().detect_tables(page_ctx.image), (
        "a single-ink bordered table was rejected"
    )


def test_a_real_table_is_still_detected(tmp_path):
    """The content gate must not suppress genuine tables."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    left, top, cell_w, cell_h = 60, 120, 110, 26
    for row in range(6):
        for col in range(4):
            rect = fitz.Rect(
                left + col * cell_w, top + row * cell_h,
                left + (col + 1) * cell_w, top + (row + 1) * cell_h,
            )
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            page.insert_text((rect.x0 + 5, rect.y0 + 17), f"R{row}C{col}", fontsize=8)
    pdf = tmp_path / "table.pdf"
    doc.save(str(pdf))
    doc.close()

    page_ctx = _page(pdf)
    assert TableDetector().detect_tables(page_ctx.image), "genuine table was rejected"


# ── a ruled grid that is really a labelled-field list ────────────────────────

def _kv_grid_pdf(path: Path, spacer_columns: int = 3) -> Path:
    """A form: label, colon, value — with empty ruled columns between.

    The shape of `ChallanReceipt.pdf`, whose six reported columns are really
    label / spacer / colon / value / spacer / spacer.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    left, top, row_h = 40, 80, 26
    widths = [130, 30, 20, 200] + [60] * spacer_columns
    edges, x = [left], left
    for w in widths:
        x += w
        edges.append(x)

    rows = [
        ("PAN", "AOKPN4722Q"), ("Name", "GAJENDRA NARAYAN"),
        ("Assessment Year", "2025-26"), ("Financial Year", "2024-25"),
        ("Major Head", "Income Tax (0021)"), ("Minor Head", "Other Receipts"),
        ("Nature of Payment", "Fee for delay"), ("Amount", "1,000"),
    ]
    for r in range(len(rows) + 1):
        y = top + r * row_h
        page.draw_line(fitz.Point(edges[0], y), fitz.Point(edges[-1], y), width=0.6)
    for x in edges:
        page.draw_line(fitz.Point(x, top), fitz.Point(x, top + len(rows) * row_h), width=0.6)

    for r, (key, value) in enumerate(rows):
        y = top + r * row_h + 17
        page.insert_text((edges[0] + 4, y), key, fontsize=8)
        page.insert_text((edges[2] + 6, y), ":", fontsize=8)
        page.insert_text((edges[3] + 4, y), value, fontsize=8)

    doc.save(str(path))
    doc.close()
    return path


def _real_table_pdf(path: Path) -> Path:
    """Every column carrying its own kind of data."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    left, top, row_h, col_w, cols = 40, 80, 24, 90, 5
    rows = 9
    for r in range(rows + 1):
        y = top + r * row_h
        page.draw_line(fitz.Point(left, y), fitz.Point(left + cols * col_w, y), width=0.6)
    for c in range(cols + 1):
        x = left + c * col_w
        page.draw_line(fitz.Point(x, top), fitz.Point(x, top + rows * row_h), width=0.6)
    for r in range(rows):
        for c in range(cols):
            page.insert_text((left + c * col_w + 4, top + r * row_h + 16),
                             f"R{r}C{c}", fontsize=7)
    doc.save(str(path))
    doc.close()
    return path


def test_a_ruled_key_value_form_is_not_reported_as_a_table(tmp_path):
    """Found on `ChallanReceipt.pdf`.

    Six columns were reported for what is one label and one value per row. The
    consequence is not cosmetic: the value of `PAN` lands in "row 3, column 4"
    rather than under its own name, so neither the operator nor the knowledge
    base ever sees the field.
    """
    from piply_opdf.detectors.table.key_value_shape import looks_like_key_value_grid

    page = _page(_kv_grid_pdf(tmp_path / "form.pdf"))
    tables = TableDetector().detect_tables(page.image)
    assert tables, "the grid should still be found geometrically"

    from piply_opdf.document import Document
    doc = Document(tmp_path / "form.pdf", work_dir=tmp_path / "work")
    doc.process_layout(use_enhanced=False)

    assert doc.key_values, "the rows should come back as labelled fields"
    assert not doc.tables, f"still reported as a table: {len(doc.tables)}"


def test_a_real_table_is_not_turned_into_key_values(tmp_path):
    """The rule must only fire where columns are genuinely empty."""
    from piply_opdf.document import Document

    doc = Document(_real_table_pdf(tmp_path / "table.pdf"), work_dir=tmp_path / "work2")
    doc.process_layout(use_enhanced=False)

    assert doc.tables, "a table with every column filled must stay a table"
