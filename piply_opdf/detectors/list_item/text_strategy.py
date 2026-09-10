"""List-item detection from the PDF text layer."""

from __future__ import annotations

import re

from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.text_layer import TextLine, extract_words, group_into_lines

__all__ = ["TextListItemStrategy", "LIST_MARKER_PATTERN"]


#: Bullets, dashes, stars, check marks, ballot boxes, and numeric/alphabetic/
#: roman enumerators in ``1.`` ``1)`` ``(1)`` forms.
LIST_MARKER_PATTERN = re.compile(
    r"^(?:"
    r"[•‣◦⁃∙*\-+✓✔☐☑■□]"
    r"|(?:\(\d+\)|\d+[.)])"
    r"|(?:\([a-zA-Z]\)|[a-zA-Z][.)])"
    r"|(?:\([ivxlcdmIVXLCDM]+\)|[ivxlcdmIVXLCDM]+[.)])"
    r")\s+",
    re.IGNORECASE,
)


class TextListItemStrategy(DetectionStrategy):
    """Starts an item at a marker and absorbs its wrapped continuation lines."""

    name = "text-layer"
    priority = 100

    def __init__(
        self,
        *,
        max_line_gap_points: float = 12.0,
        max_outdent_points: float = 15.0,
    ) -> None:
        self.max_line_gap_points = max_line_gap_points
        self.max_outdent_points = max_outdent_points

    def is_applicable(self, page: PageContext) -> bool:
        return page.has_text_layer

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []
        lines = group_into_lines(extract_words(page))
        if not lines:
            return []

        text_right = max(ln.right for ln in lines)

        items: list[DetectedComponent] = []
        run: list[TextLine] = []
        marker_left: int | None = None
        index = 1

        def flush() -> None:
            nonlocal run, index, marker_left
            if run:
                built = self._build(run, page, index)
                if built is not None:
                    items.append(built)
                    index += 1
                run = []
                marker_left = None

        for line in lines:
            text = line.text
            if page.to_pixels(line.bbox).is_excluded_by(exclusions) or len(text) < 2:
                flush()
                continue

            if LIST_MARKER_PATTERN.match(text):
                flush()
                run = [line]
                marker_left = line.left
                continue

            if run:
                previous = run[-1]
                # A continuation line stays indented and close to its item.
                if (
                    previous.gap_to(line) > self.max_line_gap_points
                    or (marker_left is not None and line.left < marker_left - self.max_outdent_points)
                    or previous.right < text_right * 0.55
                ):
                    flush()
                else:
                    run.append(line)

        flush()
        return items

    def _build(
        self,
        lines: list[TextLine],
        page: PageContext,
        index: int,
    ) -> DetectedComponent | None:
        words = [w for line in lines for w in line.words]
        text = " ".join(w.text for w in words).strip()
        if len(text) < 2:
            return None

        bbox = page.to_pixels(
            BBox.from_xyxy(
                min(w.bbox.x for w in words),
                min(w.bbox.y for w in words),
                max(w.bbox.x1 for w in words),
                max(w.bbox.y1 for w in words),
            )
        )

        children = [
            DetectedComponent(
                id=f"word_{page.page_number:03d}_L{index:03d}_{i:03d}",
                type=ComponentType.WORD,
                page=page.page_number,
                bbox=page.to_pixels(word.bbox),
                text=word.text,
                confidence=0.88,
                index=i,
            )
            for i, word in enumerate(words, start=1)
        ]

        return DetectedComponent(
            id=f"list_item_{page.page_number:03d}_{index:03d}",
            type=ComponentType.LIST_ITEM,
            page=page.page_number,
            bbox=bbox,
            text=text,
            confidence=0.90,
            index=index,
            children=children,
            metadata={"strategy": self.name, "line_count": len(lines)},
        )
