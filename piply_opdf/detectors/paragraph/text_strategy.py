"""Paragraph/sentence detection from the PDF text layer."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.text_layer import TextLine, extract_words, group_into_lines

__all__ = ["TextParagraphStrategy"]


class TextParagraphStrategy(DetectionStrategy):
    """Builds paragraphs from consecutive paragraph-like lines.

    A run of one line is emitted as a SENTENCE; a run of several as a
    PARAGRAPH. Both carry their words as children so a word can become an
    OCR/review unit.
    """

    name = "text-layer"
    priority = 100

    def __init__(
        self,
        *,
        max_line_gap_points: float = 12.0,
        max_indent_shift_points: float = 10.0,
        short_line_ratio: float = 0.55,
    ) -> None:
        self.max_line_gap_points = max_line_gap_points
        self.max_indent_shift_points = max_indent_shift_points
        #: A line ending before this fraction of the text width closes a run.
        self.short_line_ratio = short_line_ratio

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

        # Right edge of the text column, used to spot early-terminating lines
        # without hard-coding a page width.
        text_right = max(ln.right for ln in lines)

        components: list[DetectedComponent] = []
        counters = {ComponentType.PARAGRAPH: 1, ComponentType.SENTENCE: 1}
        run: list[TextLine] = []

        def flush() -> None:
            nonlocal run
            if run:
                built = self._build(run, page, counters)
                if built is not None:
                    components.append(built)
                run = []

        for line in lines:
            pixel_bbox = page.to_pixels(line.bbox)
            if pixel_bbox.is_excluded_by(exclusions, threshold=0.45) or not self._is_prose(line.text):
                flush()
                continue

            if run:
                previous = run[-1]
                if (
                    previous.gap_to(line) > self.max_line_gap_points
                    or abs(previous.left - line.left) > self.max_indent_shift_points
                    or previous.right < text_right * self.short_line_ratio
                ):
                    flush()

            run.append(line)

        flush()
        return components

    def _build(
        self,
        lines: list[TextLine],
        page: PageContext,
        counters: dict[str, int],
    ) -> DetectedComponent | None:
        words = [w for line in lines for w in line.words]
        text = " ".join(w.text for w in words).strip()
        if len(text.split()) < 2:
            return None

        comp_type = ComponentType.SENTENCE if len(lines) == 1 else ComponentType.PARAGRAPH
        index = counters[comp_type]
        counters[comp_type] += 1

        x0 = min(w.bbox.x for w in words)
        y0 = min(w.bbox.y for w in words)
        x1 = max(w.bbox.x1 for w in words)
        y1 = max(w.bbox.y1 for w in words)
        bbox = page.to_pixels(BBox.from_xyxy(x0, y0, x1, y1))

        children = [
            DetectedComponent(
                id=f"word_{page.page_number:03d}_{index:03d}_{i:03d}",
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
            id=f"{comp_type.lower()}_{page.page_number:03d}_{index:03d}",
            type=comp_type,
            page=page.page_number,
            bbox=bbox,
            text=text,
            confidence=self._confidence(text, len(lines)),
            index=index,
            children=children,
            metadata={"strategy": self.name, "line_count": len(lines)},
        )

    @staticmethod
    def _is_prose(text: str) -> bool:
        """Reject lines that are mostly punctuation, rules, or digits-only."""
        return sum(ch.isalpha() for ch in text) >= 2

    @staticmethod
    def _confidence(text: str, line_count: int) -> float:
        words = len(text.split())
        if words >= 25 or line_count >= 2:
            return 0.90
        if words >= 15:
            return 0.84
        return 0.76
