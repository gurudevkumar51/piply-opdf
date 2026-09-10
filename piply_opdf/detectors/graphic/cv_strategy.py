"""
Residual region detection: everything the other detectors did not claim.

Runs **last** in the layout stage, with every other detector's output as
exclusions. Whatever ink remains is a region no text detector recognised —
a logo, a signature, handwriting, a photograph of a person or an animal, a
diagram, a stamp.

Each surviving region is measured and typed by
:mod:`piply_opdf.classification.content`. Anything the classifier cannot type
confidently becomes ``UNKNOWN`` rather than being discarded or force-fitted:
a page should never silently lose content, and deciding what to do with an
unclassified region is a later phase's job.

Where the classifier reports **text**, the region is emitted as a ``SENTENCE``
flagged ``needs_ocr`` instead. Reaching this sweep only means the text
detectors missed it, not that it stopped being text — on a scanned bank
statement every value on the page arrived here.
"""

from __future__ import annotations

import cv2

from piply_opdf.classification.content import classify, measure
from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.common import binarize, points_to_px, to_grayscale

__all__ = ["CvGraphicStrategy"]

#: Types that are marks: small things placed on a page, not regions of it.
_MARK_TYPES = (
    ComponentType.SIGNATURE,
    ComponentType.STAMP,
    ComponentType.LOGO,
    ComponentType.HANDWRITING,
)

#: A mark larger than this share of the page is not a mark. Measured on the
#: sample corpus: genuine marks run 0.5-2.3%, the wrongly typed regions 6-45%.
#: Set with room above the real ones rather than tight against them.
_MAX_MARK_PAGE_SHARE = 0.05


class CvGraphicStrategy(DetectionStrategy):
    """Finds and types unclaimed ink regions."""

    name = "cv-residual"
    priority = 10

    def __init__(
        self,
        *,
        min_area_ratio: float = 0.00035,
        merge_gap_points: float = 6.0,
        max_regions: int = 40,
    ) -> None:
        #: Ignore specks below this fraction of the page area.
        self.min_area_ratio = min_area_ratio
        #: Nearby fragments within this distance merge into one region.
        self.merge_gap_points = merge_gap_points
        #: Safety valve against a noisy scan producing thousands of regions.
        self.max_regions = max_regions

    def is_applicable(self, page: PageContext) -> bool:
        return page.image is not None and page.image.size > 0

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []

        binary = binarize(to_grayscale(page.image))

        # Erase everything already accounted for; what is left is residual.
        for ex in exclusions:
            x0, y0 = max(0, ex.x), max(0, ex.y)
            x1, y1 = min(page.width, ex.x1), min(page.height, ex.y1)
            if x1 > x0 and y1 > y0:
                binary[y0:y1, x0:x1] = 0

        # Merge fragments of one graphic (a signature's separate pen strokes,
        # a logo's separate glyphs) into a single region.
        gap = max(2, points_to_px(self.merge_gap_points, page.dpi))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (gap, gap))
        merged = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        merged = cv2.dilate(merged, kernel, iterations=1)

        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        page_area = float(page.width * page.height)
        min_area = page_area * self.min_area_ratio

        boxes: list[BBox] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w * h < min_area:
                continue
            boxes.append(BBox(x, y, w, h))

        # Largest first, so the cap keeps the most significant regions.
        boxes.sort(key=lambda b: b.area, reverse=True)
        boxes = boxes[: self.max_regions]
        boxes.sort(key=lambda b: (b.y, b.x))

        components: list[DetectedComponent] = []
        counters: dict[str, int] = {}

        for box in boxes:
            crop = page.image[box.y:box.y1, box.x:box.x1]
            features = measure(crop)
            verdict = classify(features)
            component_type, confidence = verdict.type, verdict.confidence
            candidates = list(verdict.candidates)

            # The classifier may report printed text: that means a text
            # detector missed it rather than that it is a graphic.
            #
            # Report it as text needing OCR rather than burying it in the
            # residual bin. UNKNOWN says "nobody knows what this is", which on
            # a scanned bank statement was untrue and unhelpful — every value
            # on the page landed there. Text the detectors missed is still
            # text, and saying so sends it for reading and review.
            #
            # Confidence stays low: this arrived through the residual sweep,
            # so the geometry was never confirmed by a text detector.
            needs_ocr = False
            if component_type not in ComponentType.GRAPHIC:
                component_type = ComponentType.SENTENCE
                confidence = min(confidence, 0.50)
                candidates = []
                needs_ocr = True

            # A signature, a stamp and a logo are all *marks* — small things.
            # Nothing enforced that, so a whole revenue chart came back
            # SIGNATURE, an empty table column came back SIGNATURE, and a whole
            # transaction table came back HANDWRITING.
            #
            # Measured across the corpus: genuine marks run 0.5-2.3% of a page,
            # while the wrongly typed regions run 6-45%. The classifier cannot
            # apply this itself — it only ever sees the crop, never the page.
            if (
                component_type in _MARK_TYPES
                and box.area > page_area * _MAX_MARK_PAGE_SHARE
            ):
                component_type = ComponentType.UNKNOWN
                confidence = 0.30
                candidates = []

            index = counters.get(component_type, 0) + 1
            counters[component_type] = index

            metadata = {"strategy": self.name, "needs_ocr": needs_ocr}
            if needs_ocr:
                # Marks a box that came from pixels rather than from known
                # text, so segmentation leaves it whole until it is read.
                metadata["residual_fragment"] = True
            if features is not None:
                metadata["features"] = {
                    "ink_ratio": round(features.ink_ratio, 4),
                    "stroke_width_cv": round(features.stroke_width_cv, 3),
                    "saturation": round(features.saturation, 3),
                    "colour_richness": round(features.colour_richness, 3),
                    "component_density": round(features.component_density, 1),
                    "aspect_ratio": round(features.aspect_ratio, 2),
                }

            components.append(
                DetectedComponent(
                    id=f"{component_type.lower()}_{page.page_number:03d}_{index:03d}",
                    type=component_type,
                    page=page.page_number,
                    bbox=box,
                    text="",
                    confidence=confidence,
                    index=index,
                    candidates=candidates,
                    metadata=metadata,
                )
            )

        return components
