"""
Containers: what is inside a box is found by the ordinary detectors.

A panel holding a signature, a stamp, key-value pairs and captions needs no
parser of its own. It is handed to the same detectors that search a page, in a
cropped view they cannot distinguish from one.

The hard part is coordinates. A detector works in the crop's own frame, and
everything it produces — the box, any children, **and geometry it stashed in
metadata** — has to come back to full-page coordinates together. Miss one and a
component's own box is right while its parts point somewhere else.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

import piply_opdf.segmentation  # noqa: F401  (registers segmenters)
from piply_opdf.core import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.core.segmenter import segment_tree, segmenter_registry
from piply_opdf.detectors.panel import PanelDetector
from piply_opdf.segmentation.container import INTERIOR_ORDER, ContainerSegmenter
from piply_opdf.utils.pdf import iter_pages

PAGE_SIZES = [("a4", 595, 842), ("letter", 612, 792)]


def _signature_box_page(path: Path, w: float, h: float) -> Path:
    """A framed block like the one on a medical form: captions and key-values
    in two columns."""
    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    page.draw_rect(fitz.Rect(w * 0.08, h * 0.36, w * 0.92, h * 0.51), color=(0, 0, 0), width=1)
    page.insert_text((w * 0.10, h * 0.47), "Signature of Life Assured/ Client", fontsize=8)
    page.insert_text((w * 0.10, h * 0.492), "Date:        11/02/2026", fontsize=8)
    page.insert_text((w * 0.54, h * 0.47), "Signature & Seal of Medical Examiner", fontsize=8)
    page.insert_text((w * 0.54, h * 0.492), "Place:       Vizag", fontsize=8)
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
def boxes(tmp_path_factory) -> dict[str, tuple[Path, Path]]:
    root = tmp_path_factory.mktemp("containers")
    out: dict[str, tuple[Path, Path]] = {}
    for name, w, h in PAGE_SIZES:
        digital = _signature_box_page(root / f"{name}.pdf", w, h)
        out[name] = (digital, _rasterise(digital, root / f"{name}_scanned.pdf"))
    return out


def _segmented_panel(path: Path) -> tuple[DetectedComponent, PageContext]:
    page = _page(path)
    panels = PanelDetector().detect(page)
    assert panels, "no panel detected"
    panel = panels[0]
    segment_tree(panel, page)
    return panel, page


# ── cropped contexts ─────────────────────────────────────────────────────────

def test_sub_context_reports_local_coordinates(boxes):
    page = _page(boxes["a4"][0])
    region = BBox(200, 300, 600, 400)
    sub = page.sub_context(region)

    assert sub is not None
    assert sub.is_crop is True
    assert sub.origin == (200, 300)
    assert (sub.width, sub.height) == (600, 400)
    # a box at the crop's origin maps back to the region's origin
    assert sub.to_page(BBox(0, 0, 10, 10)).to_tuple() == (200, 300, 10, 10)


def test_full_page_context_is_not_a_crop(boxes):
    page = _page(boxes["a4"][0])
    assert page.is_crop is False
    assert page.origin == (0, 0)
    assert page.to_page(BBox(5, 6, 7, 8)).to_tuple() == (5, 6, 7, 8)


def test_sub_context_rejects_a_region_too_small(boxes):
    page = _page(boxes["a4"][0])
    assert page.sub_context(BBox(10, 10, 4, 4)) is None


def test_text_layer_is_restricted_and_moved(boxes):
    """A crop must see only its own text, in its own coordinates.

    Without this, text strategies inside a container would return whole-page
    positions and every child would land in the wrong place.
    """
    page = _page(boxes["a4"][0])
    assert page.has_text_layer

    panel = PanelDetector().detect(page)[0]
    sub = page.sub_context(panel.bbox, inset=8)
    assert sub is not None

    assert sub.text_blocks, "crop should still see the text inside the box"
    assert len(sub.text_blocks) <= len(page.text_blocks)

    # every block sits inside the crop, in local coordinates
    for block in sub.text_blocks:
        pixel = sub.to_pixels(block.bbox)
        assert 0 <= pixel.x <= sub.width
        assert 0 <= pixel.y <= sub.height


def test_nested_crop_keeps_absolute_origin(boxes):
    page = _page(boxes["a4"][0])
    outer = page.sub_context(BBox(100, 100, 800, 600))
    inner = outer.sub_context(BBox(50, 40, 200, 150))
    assert inner.origin == (150, 140)


# ── registration ─────────────────────────────────────────────────────────────

def test_panel_has_a_container_segmenter():
    segmenter = segmenter_registry.create(ComponentType.PANEL)
    assert isinstance(segmenter, ContainerSegmenter)


def test_panel_is_not_searched_inside_itself():
    """A panel looking for panels would find its own frame, forever."""
    assert ComponentType.PANEL not in INTERIOR_ORDER


def test_page_only_types_are_not_searched_inside():
    """Header, footer and title mean position on a *page*, not in a box."""
    for component_type in (ComponentType.HEADER, ComponentType.FOOTER, ComponentType.TITLE):
        assert component_type not in INTERIOR_ORDER


# ── the requirement ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_panel_is_broken_into_its_contents(boxes, size, variant):
    panel, _ = _segmented_panel(boxes[size][variant])
    assert panel.children, "panel produced no children"
    assert any(c.type == ComponentType.KEY_VALUE for c in panel.children)


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_children_lie_inside_their_panel(boxes, size, variant):
    """The coordinate test. A child outside its parent means a translation was
    missed somewhere."""
    panel, _ = _segmented_panel(boxes[size][variant])
    allowed = panel.bbox.padded(12)

    for child in panel.children:
        assert child.bbox.covered_fraction([allowed]) > 0.9, (
            f"{child.id} at {child.bbox.to_tuple()} escapes panel {panel.bbox.to_tuple()}"
        )


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_grandchildren_lie_inside_their_parent(boxes, size, variant):
    """Metadata geometry must move with the component.

    The key-value detectors record key/separator/value positions in metadata
    for the segmenter to use later. Translating only ``bbox`` leaves those
    behind, and the parts land in the wrong part of the page.
    """
    panel, _ = _segmented_panel(boxes[size][variant])

    checked = 0
    for child in panel.children:
        for unit in child.children:
            assert unit.bbox.covered_fraction([child.bbox.padded(12)]) > 0.85, (
                f"{unit.id} at {unit.bbox.to_tuple()} escapes {child.id} "
                f"at {child.bbox.to_tuple()}"
            )
            checked += 1
    assert checked, "no grandchildren produced"


@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_key_value_parts_are_ordered_left_to_right(boxes, variant):
    panel, _ = _segmented_panel(boxes["a4"][variant])

    pairs = [c for c in panel.children if c.type == ComponentType.KEY_VALUE]
    assert pairs

    for pair in pairs:
        roles = [u.metadata.get("role") for u in pair.children]
        if roles != ["key", "separator", "value"]:
            continue
        key, separator, value = pair.children
        assert key.bbox.x1 <= separator.bbox.x + 2
        assert separator.bbox.x1 <= value.bbox.x + 2


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_nothing_inside_is_reported_twice(boxes, size, variant):
    """A residual region must not restate content already recognised.

    The residual sweep exists so nothing is lost, not to compete for space that
    is already claimed.
    """
    panel, _ = _segmented_panel(boxes[size][variant])

    recognised = [
        c.bbox.padded(max(4, int(c.bbox.height * 0.6)))
        for c in panel.children
        if c.type not in ComponentType.GRAPHIC
    ]
    if not recognised:
        pytest.skip("nothing recognised to overlap with")

    for child in panel.children:
        if child.type in ComponentType.GRAPHIC:
            assert child.bbox.covered_fraction(recognised) <= 0.45, (
                f"{child.id} restates content already found"
            )


@pytest.mark.parametrize("size", [s[0] for s in PAGE_SIZES])
def test_both_paths_decompose_the_panel(boxes, size):
    """Both routes must open the box and find key-values in it.

    Exact counts are deliberately *not* compared here. How a line splits into
    pairs is a property of the key-value detector, and it is tested directly —
    with a cleaner layout — in ``test_form_layouts.py``. Asserting counts here
    as well would make this test fail for reasons that have nothing to do with
    containers.
    """
    for path in boxes[size]:
        panel, _ = _segmented_panel(path)
        assert panel.children, f"{path.name}: panel produced no children"
        assert any(c.type == ComponentType.KEY_VALUE for c in panel.children), (
            f"{path.name}: no key-value found inside the panel"
        )


@pytest.mark.parametrize("variant", [0, 1], ids=["digital", "scanned"])
def test_children_record_which_container_they_came_from(boxes, variant):
    panel, _ = _segmented_panel(boxes["a4"][variant])
    for child in panel.children:
        assert child.metadata.get("inside") == panel.id
        assert child.id.startswith(panel.id)


def test_segmentation_terminates_with_a_bounded_tree(boxes):
    """Segmenting a container must finish, and not nest without limit.

    Note the depth cap governs *segmentation*, not detection: a detector may
    attach children itself while finding a component — the text paragraph
    strategy attaches words — and those arrive before segmentation is asked to
    do anything. So the guarantee is a bounded tree, not childless children.
    """
    panel, _ = _segmented_panel(boxes["a4"][0])

    def depth(component, level=0):
        if not component.children:
            return level
        return max(depth(c, level + 1) for c in component.children)

    assert panel.children
    assert depth(panel) <= 4, f"tree nested {depth(panel)} deep"


def test_a_component_that_is_not_a_container_is_untouched(boxes):
    page = _page(boxes["a4"][0])
    orphan = DetectedComponent(
        id="word_001_001", type=ComponentType.WORD, page=1,
        bbox=BBox(10, 10, 40, 20), text="hello",
    )
    assert segment_tree(orphan, page).children == []
