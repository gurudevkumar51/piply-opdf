"""
Panel detection: closed frames that hold content but are not tables.

A panel is a box drawn around something — a boxed note, a framed photograph, a
signature block. It looks exactly like a table from the outside. What separates
them is what is inside:

    2 or more cells  ->  TABLE   (left for the table detector)
    exactly 1 cell   ->  PANEL

See docs/components.md, Rule 1.

There is no text-layer strategy. A frame is drawn, not written, so it never
appears in a PDF's text layer — the outline has to be found in the image
whether the page is digital or scanned.
"""

from __future__ import annotations

from piply_opdf.classification.content import classify, measure
from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.common import count_cells, find_frames

__all__ = ["CvPanelStrategy"]

#: Content types that mean the inside of a frame is a picture, not structure.
#: UNKNOWN is excluded: an unrecognised interior with real rules is more likely
#: a sparse table than a picture.
_PICTURE_CONTENT = (
    ComponentType.IMAGE,
    ComponentType.LOGO,
    ComponentType.STAMP,
    ComponentType.SIGNATURE,
)


class CvPanelStrategy(DetectionStrategy):
    """Finds closed frames and keeps the undivided ones."""

    name = "cv-frame"
    priority = 10

    def __init__(
        self,
        *,
        min_side_ratio: float = 0.06,
        max_page_coverage: float = 0.92,
    ) -> None:
        #: Smallest frame side, as a fraction of the page. Below this a closed
        #: shape is a glyph part (O, D, 8) or noise, not layout.
        self.min_side_ratio = min_side_ratio
        #: A "frame" covering nearly the whole page is the page border or the
        #: scanner edge, not a panel.
        self.max_page_coverage = max_page_coverage

    def is_applicable(self, page: PageContext) -> bool:
        return page.image is not None and page.image.size > 0

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []
        page_area = page.width * page.height

        panels: list[DetectedComponent] = []
        index = 1

        for frame in find_frames(page.image, min_side_ratio=self.min_side_ratio):
            if frame.area > page_area * self.max_page_coverage:
                continue
            if frame.is_excluded_by(exclusions, threshold=0.5):
                continue

            cells = count_cells(page.image, frame)

            if cells >= 2 and not self._interior_is_picture(page, frame):
                # Divided inside — a table, not a panel. Left alone so the
                # table detector claims it.
                continue

            panels.append(
                DetectedComponent(
                    id=f"panel_{page.page_number:03d}_{index:03d}",
                    type=ComponentType.PANEL,
                    page=page.page_number,
                    bbox=frame,
                    text="",
                    confidence=0.80,
                    index=index,
                    metadata={
                        "strategy": self.name,
                        "cell_count": 1 if self._interior_is_picture(page, frame) else cells,
                        # A container: its children come from running detection
                        # again inside it, not from a parser of its own.
                        "is_container": True,
                    },
                )
            )
            index += 1

        return panels

    @staticmethod
    def _interior_is_picture(page: PageContext, frame: BBox) -> bool:
        """Whether the inside of *frame* is a picture rather than structure.

        Counting rules is a geometric test, and a photograph defeats it: render
        artefacts and image detail produce thin streaks that look like cell
        dividers, so a framed picture reads as a table with several cells.

        Asking the classifier what the interior actually *is* settles it. Only
        confident picture types count — an unrecognised interior with real
        rules is more likely a sparse table.
        """
        inset = max(3, int(min(frame.width, frame.height) * 0.06))
        x0, y0 = frame.x + inset, frame.y + inset
        x1, y1 = frame.x1 - inset, frame.y1 - inset
        if x1 <= x0 or y1 <= y0:
            return False

        crop = page.image[y0:y1, x0:x1]
        return classify(measure(crop)).type in _PICTURE_CONTENT
