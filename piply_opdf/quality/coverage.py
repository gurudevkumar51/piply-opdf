"""
Ink coverage: the machine-checkable form of "nothing is lost".

R7 promises that every region of ink on a page becomes some component. That is
a claim about the whole page, so it can be measured directly rather than
inspected: binarise the page, union every component's box, and report what
fraction of the ink falls inside.

A page that scores below the target has lost content. Nothing else needs to be
known about the document to say so — which makes this the one detection quality
signal available without labelled ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from piply_opdf.core.types import BBox, DetectedComponent, PageContext
from piply_opdf.detectors.common import binarize, to_grayscale

__all__ = ["CoverageReport", "measure_coverage", "TARGET_COVERAGE"]

#: A page must account for at least this share of its ink. The remainder is
#: speckle below the noise floor — dust, scanner grain, JPEG ringing.
TARGET_COVERAGE = 0.995


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """How much of a page's ink was claimed by some component."""

    #: Share of ink pixels inside at least one component. 1.0 means nothing lost.
    accounted: float
    #: Ink pixels on the page.
    total_ink: int
    #: Ink pixels no component covered.
    missed_ink: int
    #: Separate uncovered regions, largest first. Where to look when it drops.
    gaps: tuple[BBox, ...]

    @property
    def meets_target(self) -> bool:
        return self.accounted >= TARGET_COVERAGE


def _walk(components: list[DetectedComponent]):
    for component in components:
        yield from component.walk()


def measure_coverage(
    page: PageContext,
    components: list[DetectedComponent],
    *,
    min_gap_ratio: float = 0.00002,
) -> CoverageReport:
    """Measure what share of *page*'s ink lies inside *components*.

    Every component counts, at any depth — a word inside a sentence inside a
    paragraph covers its own area. Nested boxes overlap, which is harmless: the
    union is what matters.

    *min_gap_ratio* filters specks out of the reported gaps so the list points
    at real losses rather than dust.
    """
    if page.image is None or page.image.size == 0:
        return CoverageReport(1.0, 0, 0, ())

    ink = binarize(to_grayscale(page.image)) > 0
    total = int(ink.sum())
    if total == 0:
        # A blank page loses nothing.
        return CoverageReport(1.0, 0, 0, ())

    claimed = np.zeros(ink.shape, dtype=bool)
    for component in _walk(components):
        box = component.bbox
        x0, y0 = max(0, box.x), max(0, box.y)
        x1, y1 = min(page.width, box.x1), min(page.height, box.y1)
        if x1 > x0 and y1 > y0:
            claimed[y0:y1, x0:x1] = True

    missed_mask = ink & ~claimed
    missed = int(missed_mask.sum())

    return CoverageReport(
        accounted=(total - missed) / total,
        total_ink=total,
        missed_ink=missed,
        gaps=_gap_boxes(missed_mask, page, min_gap_ratio),
    )


def _gap_boxes(
    missed_mask: np.ndarray,
    page: PageContext,
    min_gap_ratio: float,
) -> tuple[BBox, ...]:
    """Group uncovered ink into regions worth looking at, largest first."""
    import cv2

    if not missed_mask.any():
        return ()

    # Join neighbouring stray marks so one lost paragraph is one gap, not fifty.
    gap = max(3, int(min(page.width, page.height) * 0.004))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (gap, gap))
    merged = cv2.dilate(missed_mask.astype(np.uint8) * 255, kernel, iterations=1)

    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = page.width * page.height * min_gap_ratio

    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h >= min_area:
            boxes.append(BBox(x, y, w, h))

    boxes.sort(key=lambda b: b.area, reverse=True)
    return tuple(boxes[:20])
