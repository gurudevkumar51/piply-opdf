"""
Core value types shared across the pipeline.

Everything downstream of layout detection speaks in these types, so detectors,
extractors and the OCR layer never have to agree on ad-hoc dict shapes.

Coordinate convention
---------------------
PyMuPDF reports geometry in **PDF points** (72 per inch). The rest of the
pipeline works on rasters rendered at ``PageContext.dpi`` (300 by default).
``PageContext.scale`` converts between them; :meth:`BBox.scaled` applies it.
All :class:`BBox` instances stored on a :class:`DetectedComponent` are in
**pixels at the page's render DPI**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Iterator

import numpy as np

__all__ = [
    "BBox",
    "TextBlock",
    "PageContext",
    "DetectedComponent",
    "ComponentType",
]


class ComponentType:
    """Canonical component type names. Used as the single vocabulary between
    the package, the persistence layer and the UI."""

    TABLE = "TABLE"
    BORDERLESS_TABLE = "BORDERLESS_TABLE"

    #: A closed frame with no internal division — exactly one cell. A table
    #: requires two or more. Both are boxes; cell count is what separates them,
    #: because a one-cell table and a boxed paragraph are pixel-identical.
    PANEL = "PANEL"

    ROW = "ROW"
    COLUMN = "COLUMN"
    CELL = "CELL"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    KEY_VALUE = "KEY_VALUE"
    PARAGRAPH = "PARAGRAPH"
    SENTENCE = "SENTENCE"
    LIST_ITEM = "LIST_ITEM"
    WORD = "WORD"

    #: **Rule 4.** The three heading levels, told apart by *relative* prominence
    #: and position — never by an absolute font size, because a 14 pt line is a
    #: heading in a document set in 9 pt and body text in one set in 16 pt.
    #:
    #: In priority order: position and hierarchy; size relative to the
    #: surrounding text; weight; whitespace before and after; alignment;
    #: numbering pattern (``1.``, ``1.1``, ``A.``); repetition across pages.
    #:
    #: Where the *level* cannot be decided, the region is still reported as a
    #: heading — with the level marked unknown, low confidence, and the three
    #: carried as candidates so review is one click. A subheading wrongly
    #: promoted to a title corrupts the document outline, and an outline error
    #: is invisible in the text.

    #: The main document or page-section title. Largest or most prominent,
    #: normally once per document or section.
    TITLE = "TITLE"
    #: A major section heading, introducing a significant section.
    HEADING = "HEADING"
    #: Nested under a heading; introduces a smaller subsection.
    SUBHEADING = "SUBHEADING"

    # Non-prose regions. Located by the graphic detector and typed by the
    # content classifier.
    SIGNATURE = "SIGNATURE"
    HANDWRITING = "HANDWRITING"
    LOGO = "LOGO"
    #: An inked seal. Single ink colour, unlike a logo — see Rule 2.
    STAMP = "STAMP"
    IMAGE = "IMAGE"

    #: A ruled line: a horizontal divider, a box edge, an underline. Carries no
    #: content of its own, but it is on the page and something has to own it.
    #: Without this type, thin line-work fell through to the pen rules and was
    #: reported as a SIGNATURE on almost every document that has a divider.
    SEPARATOR = "SEPARATOR"

    #: Residual bucket. Ink that no detector claimed and the classifier could
    #: not confidently type — photographs of people, animals, diagrams, stamps.
    #: Captured deliberately so nothing on a page is silently dropped; what to
    #: do with it is a later decision.
    UNKNOWN = "UNKNOWN"

    #: Types that carry recognisable text and therefore segment down to words.
    TEXTUAL = (
        HEADER, FOOTER, TITLE, HEADING, SUBHEADING,
        PARAGRAPH, SENTENCE, LIST_ITEM, KEY_VALUE, CELL, WORD,
    )

    #: Types that are pictorial: no text units, no OCR by default.
    GRAPHIC = (SIGNATURE, HANDWRITING, LOGO, STAMP, IMAGE, SEPARATOR, UNKNOWN)

    #: Types that hold other components. Their children are found by running
    #: detection again inside them, rather than by a bespoke parser.
    CONTAINER = (PANEL, TABLE, BORDERLESS_TABLE)

    ALL = (
        TABLE, BORDERLESS_TABLE, PANEL, ROW, COLUMN, CELL, HEADER, FOOTER,
        KEY_VALUE, PARAGRAPH, SENTENCE, LIST_ITEM, WORD,
        TITLE, HEADING, SUBHEADING,
        SIGNATURE, HANDWRITING, LOGO, STAMP, IMAGE, SEPARATOR, UNKNOWN,
    )


@dataclass(frozen=True, slots=True)
class BBox:
    """An axis-aligned box in ``(x, y, width, height)`` form."""

    x: int
    y: int
    width: int
    height: int

    # ── constructors ─────────────────────────────────────────────────────────

    @classmethod
    def from_xyxy(cls, x0: float, y0: float, x1: float, y1: float) -> BBox:
        return cls(int(x0), int(y0), int(x1 - x0), int(y1 - y0))

    @classmethod
    def from_any(cls, value: Any) -> BBox | None:
        """Best-effort parse of the several bbox shapes present in legacy data.

        Accepts ``BBox``, ``(x, y, w, h)`` sequences, and mappings keyed either
        ``x/y/width/height`` or ``x0/y0/x1/y1``. Returns *None* when the value
        cannot be interpreted, so callers can skip rather than crash.
        """
        if value is None:
            return None
        if isinstance(value, BBox):
            return value
        if isinstance(value, dict):
            if "width" in value or "height" in value:
                return cls(
                    int(value.get("x", 0)), int(value.get("y", 0)),
                    int(value.get("width", 0)), int(value.get("height", 0)),
                )
            if "x1" in value and "y1" in value:
                return cls.from_xyxy(
                    value.get("x0", 0), value.get("y0", 0), value["x1"], value["y1"],
                )
            return None
        if isinstance(value, (list, tuple)) and len(value) == 4:
            return cls(int(value[0]), int(value[1]), int(value[2]), int(value[3]))
        return None

    # ── derived geometry ─────────────────────────────────────────────────────

    @property
    def x1(self) -> int:
        return self.x + self.width

    @property
    def y1(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def to_xyxy(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x1, self.y1)

    def scaled(self, factor: float) -> BBox:
        return BBox(
            int(self.x * factor), int(self.y * factor),
            int(self.width * factor), int(self.height * factor),
        )

    def padded(self, pad: int) -> BBox:
        return BBox(
            max(0, self.x - pad), max(0, self.y - pad),
            self.width + 2 * pad, self.height + 2 * pad,
        )

    # ── relationships ────────────────────────────────────────────────────────

    def intersection_area(self, other: BBox) -> int:
        dx = min(self.x1, other.x1) - max(self.x, other.x)
        dy = min(self.y1, other.y1) - max(self.y, other.y)
        return dx * dy if dx > 0 and dy > 0 else 0

    def overlap_ratio(self, other: BBox) -> float:
        """Fraction of *self* covered by *other*. 0.0 when *self* has no area."""
        return self.intersection_area(other) / self.area if self.area else 0.0

    def contains_point(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x1 and self.y <= py <= self.y1

    def covered_fraction(self, exclusions: list[BBox]) -> float:
        """Fraction of this box covered by *exclusions* taken together.

        Summing intersections slightly overestimates when exclusions overlap
        each other, which is acceptable: exclusions are distinct components
        and the result is clamped to 1.0.
        """
        if not self.area:
            return 0.0
        total = sum(self.intersection_area(ex) for ex in exclusions)
        return min(1.0, total / self.area)

    def is_excluded_by(self, exclusions: list[BBox], threshold: float = 0.0) -> bool:
        """True when *exclusions* cover this box.

        With ``threshold == 0`` the test is centre-point containment, which is
        what the text-layer detectors have always used. Above zero it becomes
        an area test against the **combined** coverage.

        Combined rather than per-box matters for form rows: a line holding two
        key-value pairs is only ~45% covered by each pair individually, so a
        per-box test lets it through and the row is re-reported as prose.
        """
        if threshold <= 0:
            cx, cy = self.center
            return any(ex.contains_point(cx, cy) for ex in exclusions)
        return self.covered_fraction(exclusions) > threshold


@dataclass(frozen=True, slots=True)
class TextBlock:
    """A block of embedded text as reported by the PDF text layer.

    ``bbox`` is in **PDF points**, matching PyMuPDF's native output. Use
    :meth:`PageContext.to_pixels` to convert.
    """

    bbox: BBox
    text: str

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@dataclass
class DetectedComponent:
    """One detected layout region.

    This is the contract every detector returns and every downstream consumer
    (crop writer, manifest builder, persistence layer) reads.
    """

    id: str
    type: str
    page: int
    bbox: BBox
    text: str = ""
    confidence: float = 1.0
    #: Per-document ordinal within this component type, 1-based. Assigned by
    #: the pipeline after detection so numbering is stable and gap-free.
    index: int = 0
    #: Runner-up types when the evidence narrows to a few but cannot choose.
    #: Present only for near-ties. The operator picks from these with one
    #: click instead of answering an open question — see R13.
    candidates: list[dict[str, Any]] = field(default_factory=list)
    children: list[DetectedComponent] = field(default_factory=list)
    image_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the manifest/JSON shape."""
        return {
            "id": self.id,
            "type": self.type,
            "page": self.page,
            "index": self.index,
            "bbox": list(self.bbox.to_tuple()),
            "text": self.text,
            "confidence": self.confidence,
            "image_path": self.image_path,
            **({"candidates": self.candidates} if self.candidates else {}),
            **({"children": [c.to_dict() for c in self.children]} if self.children else {}),
            **({"metadata": self.metadata} if self.metadata else {}),
        }

    def walk(self) -> Iterator[DetectedComponent]:
        """Depth-first traversal of self and all descendants."""
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class PageContext:
    """Everything a detector needs to work on a single page.

    Carries both representations of the page so a detector can pick a strategy:
    the rendered raster (always available) and the embedded text layer (absent
    on scanned documents). ``has_text_layer`` is the discriminator.
    """

    page_number: int          # 1-based
    source_path: Path
    image: np.ndarray         # rendered at ``dpi``, after any deskew
    dpi: int = 300

    #: Rotation in degrees already applied to :attr:`image` to straighten it.
    #: 0.0 when the page was upright or carries a text layer (those are not
    #: deskewed, because the text layer reports original-frame coordinates).
    #: Recorded so original-page coordinates remain recoverable for overlays.
    skew_correction: float = 0.0

    #: Where this context sits inside the full page, in full-page pixels.
    #: ``None`` means this *is* the full page. When set, the context is a crop —
    #: :attr:`image` holds only that area and every coordinate, including text
    #: blocks, is reported relative to the crop's own top-left corner.
    #:
    #: This is what lets a container be searched with the ordinary detectors:
    #: they cannot tell a cropped context from a page, so no detector needs to
    #: know that containers exist.
    region: BBox | None = None

    @property
    def scale(self) -> float:
        """Multiplier converting PDF points to pixels at this page's DPI."""
        return self.dpi / 72.0

    @property
    def is_crop(self) -> bool:
        return self.region is not None

    @property
    def origin(self) -> tuple[int, int]:
        """Top-left of this context in full-page pixels."""
        return (self.region.x, self.region.y) if self.region else (0, 0)

    def to_page(self, bbox: BBox) -> BBox:
        """Translate a bbox from this context's coordinates to the full page."""
        ox, oy = self.origin
        return BBox(bbox.x + ox, bbox.y + oy, bbox.width, bbox.height)

    def sub_context(self, region: BBox, *, inset: int = 0) -> PageContext | None:
        """A context covering *region* of this one, for searching inside it.

        *region* is in this context's coordinates. *inset* trims the edge, which
        matters for a framed box: without it the frame's own rules are inside
        the crop and get detected as content.

        Returns None when the region is too small to search.
        """
        x0 = max(0, region.x + inset)
        y0 = max(0, region.y + inset)
        x1 = min(self.width, region.x1 - inset)
        y1 = min(self.height, region.y1 - inset)
        if x1 - x0 < 8 or y1 - y0 < 8:
            return None

        ox, oy = self.origin
        absolute = BBox(x0 + ox, y0 + oy, x1 - x0, y1 - y0)

        return PageContext(
            page_number=self.page_number,
            source_path=self.source_path,
            image=self.image[y0:y1, x0:x1],
            dpi=self.dpi,
            skew_correction=self.skew_correction,
            region=absolute,
        )

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    def to_pixels(self, bbox: BBox) -> BBox:
        """Convert a point-space bbox (PyMuPDF) to pixel space."""
        return bbox.scaled(self.scale)

    @cached_property
    def text_blocks(self) -> list[TextBlock]:
        """Embedded text blocks, in PDF points, relative to this context.

        On a crop, blocks outside the region are dropped and the rest are moved
        so their coordinates are relative to the crop. A detector therefore sees
        exactly what it would see if the crop were a page of its own.

        Empty for images and scans.
        """
        if self.source_path.suffix.lower() != ".pdf":
            return []
        try:
            import fitz
        except ImportError:  # pragma: no cover - PyMuPDF is a core dependency
            return []

        try:
            with fitz.open(str(self.source_path)) as doc:
                page = doc[self.page_number - 1]
                blocks = []
                for b in page.get_text("blocks"):
                    # b[6] is the block type: 0 = text, 1 = image
                    if b[6] != 0:
                        continue
                    text = str(b[4]).strip()
                    if not text:
                        continue
                    blocks.append(TextBlock(BBox.from_xyxy(b[0], b[1], b[2], b[3]), text))
                blocks.sort(key=lambda blk: blk.bbox.y)
                return self._restrict_to_region(blocks)
        except Exception:
            return []

    def _restrict_to_region(self, blocks: list[TextBlock]) -> list[TextBlock]:
        """Keep blocks inside this crop and move them into local coordinates."""
        if self.region is None:
            return blocks

        # Text blocks are in points; the region is in pixels.
        ox = self.region.x / self.scale
        oy = self.region.y / self.scale
        right = ox + self.width / self.scale
        bottom = oy + self.height / self.scale

        kept: list[TextBlock] = []
        for block in blocks:
            cx, cy = block.bbox.center
            if not (ox <= cx <= right and oy <= cy <= bottom):
                continue
            kept.append(
                TextBlock(
                    bbox=BBox(
                        int(block.bbox.x - ox), int(block.bbox.y - oy),
                        block.bbox.width, block.bbox.height,
                    ),
                    text=block.text,
                )
            )
        return kept

    @cached_property
    def has_text_layer(self) -> bool:
        """Whether this page carries extractable embedded text.

        False for scanned/image-only PDFs and for raster inputs, which is the
        signal to fall back to a CV strategy.
        """
        return len(self.text_blocks) > 0
