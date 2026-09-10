"""
Panel detection and Rule 1 — the cell-count rule.

A closed frame is either a table or a panel, and only the cell count separates
them:

    2 or more cells  ->  TABLE
    exactly 1 cell   ->  PANEL

A one-cell table and a boxed paragraph are pixel-identical, so this boundary is
set by definition rather than guessed. See docs/components.md, Rule 1.

Pages are built in-process at several sizes and resolutions, and each is tested
both as a digital PDF and as a scan, so the tests check the logic rather than
one file.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import fitz
import numpy as np
import pytest

from piply_opdf.core import ComponentType, PageContext
from piply_opdf.detectors.common import count_cells, find_frames
from piply_opdf.detectors.panel import CvPanelStrategy, PanelDetector
from piply_opdf.detectors.table import TableDetector
from piply_opdf.utils.pdf import iter_pages

PAGE_SIZES = [("a4", 595, 842), ("letter", 612, 792)]
DPIS = [200, 300, 400]


# ── page building ────────────────────────────────────────────────────────────

def _boxed_note(page, w, h) -> None:
    """A framed block of text — one cell."""
    page.draw_rect(fitz.Rect(w * 0.08, h * 0.10, w * 0.92, h * 0.23), color=(0, 0, 0), width=1)
    page.insert_text((w * 0.10, h * 0.13), "INTERPRETATION:", fontsize=9)
    for i, line in enumerate([
        "The available research data indicates that AIDS is caused",
        "by HIV virus transmitted by sexual contact or exposure to",
        "blood or certain blood products during the pre-natal period.",
    ]):
        page.insert_text((w * 0.10, h * 0.155 + i * h * 0.019), line, fontsize=8)


def _grid_table(page, w, h, rows: int = 4, cols: int = 4) -> None:
    """A ruled table — many cells."""
    left, top = w * 0.08, h * 0.30
    cw, ch = (w * 0.84) / cols, (h * 0.13) / rows
    for r in range(rows):
        for c in range(cols):
            rect = fitz.Rect(left + c * cw, top + r * ch, left + (c + 1) * cw, top + (r + 1) * ch)
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            page.insert_text((rect.x0 + 4, rect.y0 + ch * 0.65), f"R{r}C{c}", fontsize=7)


def _signature_box(page, w, h) -> None:
    """A framed signature area — one cell."""
    page.draw_rect(fitz.Rect(w * 0.08, h * 0.48, w * 0.92, h * 0.58), color=(0, 0, 0), width=1)
    page.insert_text((w * 0.10, h * 0.56), "Signature of Life Assured/ Client", fontsize=8)
    page.insert_text((w * 0.52, h * 0.56), "Signature & Seal of Medical Examiner", fontsize=8)


def _framed_photo(page, w, h, seed: int = 3) -> None:
    """A photograph inside a frame — one cell, but its content defeats a
    purely geometric cell count."""
    rng = np.random.default_rng(seed)
    photo = cv2.GaussianBlur((rng.random((160, 130, 3)) * 255).astype(np.uint8), (9, 9), 0)
    ok, buffer = cv2.imencode(".png", photo)
    assert ok
    frame = fitz.Rect(w * 0.08, h * 0.62, w * 0.30, h * 0.81)
    page.draw_rect(frame, color=(0, 0, 0), width=1.2)
    page.insert_image(fitz.Rect(frame.x0 + 2, frame.y0 + 2, frame.x1 - 2, frame.y1 - 2),
                      stream=buffer.tobytes())


def _build(path: Path, w: float, h: float, parts) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    for part in parts:
        part(page, w, h)
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
def mixed(tmp_path_factory) -> dict[str, tuple[Path, Path]]:
    """One page per size holding: boxed note, table, signature box, framed photo."""
    root = tmp_path_factory.mktemp("panels")
    parts = [_boxed_note, _grid_table, _signature_box, _framed_photo]
    out: dict[str, tuple[Path, Path]] = {}
    for name, w, h in PAGE_SIZES:
        digital = _build(root / f"{name}.pdf", w, h, parts)
        out[name] = (digital, _rasterise(digital, root / f"{name}_scanned.pdf"))
    return out


# ── Rule 1: cell counting ────────────────────────────────────────────────────

@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_frames_are_found(mixed, size, variant):
    page = _page(mixed[size][variant])
    frames = find_frames(page.image)
    # boxed note, table, signature box, framed photo
    assert len(frames) >= 4, f"only found {len(frames)} frames"


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_ruled_table_counts_many_cells(mixed, size, variant):
    page = _page(mixed[size][variant])
    counts = [count_cells(page.image, f) for f in find_frames(page.image)]
    assert max(counts) >= 9, f"a 4x4 table should count many cells, got {counts}"


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_undivided_frames_count_one_cell(mixed, size, variant):
    page = _page(mixed[size][variant])
    counts = sorted(count_cells(page.image, f) for f in find_frames(page.image))
    # boxed note and signature box are plainly undivided
    assert counts[:2] == [1, 1], counts


# ── detection outcomes ───────────────────────────────────────────────────────

@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_three_panels_and_one_table(mixed, size, variant):
    """The core requirement: boxes are panels, the ruled grid is a table."""
    page = _page(mixed[size][variant])

    panels = PanelDetector().detect(page)
    tables = TableDetector().detect_tables(page.image)

    assert len(panels) == 3, [p.bbox.to_tuple() for p in panels]
    assert len(tables) == 1, tables


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
def test_digital_and_scanned_agree(mixed, size):
    digital, scanned = mixed[size]
    assert len(PanelDetector().detect(_page(digital))) == \
           len(PanelDetector().detect(_page(scanned)))


@pytest.mark.parametrize("dpi", DPIS)
def test_stable_across_resolutions(mixed, dpi):
    page = _page(mixed["a4"][1], dpi=dpi)
    assert len(PanelDetector().detect(page)) == 3


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_a_table_is_never_reported_as_a_panel(mixed, size, variant):
    """Rule 1 in the direction that matters most.

    A table wrongly called a panel would lose its row and column structure.
    """
    page = _page(mixed[size][variant])
    table = TableDetector().detect_tables(page.image)[0]

    for panel in PanelDetector().detect(page):
        overlap = panel.bbox.intersection_area(
            type(panel.bbox)(table.x, table.y, table.width, table.height)
        )
        assert overlap < panel.bbox.area * 0.5, f"{panel.id} overlaps the table"


@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_framed_photo_is_a_panel(mixed, variant):
    """A picture's own detail can look like cell dividers.

    Geometry alone counted several cells here, which would have made a framed
    photograph into a table. The classifier settles it.
    """
    page = _page(mixed["a4"][variant])
    panels = PanelDetector().detect(page)

    # the photo frame is the narrow one on the left
    narrow = [p for p in panels if p.bbox.width < page.width * 0.4]
    assert narrow, [p.bbox.to_tuple() for p in panels]


# ── properties ───────────────────────────────────────────────────────────────

def test_panels_are_marked_as_containers(mixed):
    for panel in PanelDetector().detect(_page(mixed["a4"][0])):
        assert panel.type == ComponentType.PANEL
        assert panel.metadata["is_container"] is True
        assert panel.metadata["cell_count"] == 1


def test_ordinals_are_serial_and_gap_free(mixed):
    panels = PanelDetector().detect(_page(mixed["a4"][0]))
    assert [p.index for p in panels] == list(range(1, len(panels) + 1))


def test_exclusions_suppress_panels(mixed):
    from piply_opdf.core import BBox
    page = _page(mixed["a4"][0])
    whole = [BBox(0, 0, page.width, page.height)]
    assert PanelDetector().detect(page, whole) == []


def test_page_border_is_not_a_panel(tmp_path):
    """A frame around the whole page is the page edge, not a box."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(4, 4, 591, 838), color=(0, 0, 0), width=1)
    page.insert_text((60, 300), "Body text on a bordered page.", fontsize=10)
    pdf = tmp_path / "bordered.pdf"
    doc.save(str(pdf))
    doc.close()

    assert PanelDetector().detect(_page(pdf)) == []


def test_plain_page_has_no_panels(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for i in range(12):
        page.insert_text((60, 120 + i * 20), "Ordinary prose with no boxes at all.", fontsize=10)
    pdf = tmp_path / "plain.pdf"
    doc.save(str(pdf))
    doc.close()

    assert PanelDetector().detect(_page(pdf)) == []


def test_no_text_layer_strategy_exists():
    """A frame is drawn, not written, so it never appears in a text layer."""
    strategies = PanelDetector().strategies
    assert len(strategies) == 1
    assert isinstance(strategies[0], CvPanelStrategy)


@pytest.mark.parametrize("image", [None, np.zeros((0, 0, 3), np.uint8)])
def test_degenerate_input_is_safe(image):
    assert find_frames(image) == []
