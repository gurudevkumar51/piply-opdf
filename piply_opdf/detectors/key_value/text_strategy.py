"""Key-value detection from the PDF text layer."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.text_layer import (
    TextLine,
    extract_words,
    group_into_lines,
)

__all__ = ["TextKeyValueStrategy"]


class TextKeyValueStrategy(DetectionStrategy):
    """Finds ``key: value`` rows.

    Deliberately conservative: an explicit separator is preferred, and a wide
    whitespace gap is only used as a fallback. Guessing inside prose produces
    far more noise than it is worth.
    """

    name = "text-layer"
    priority = 100

    #: Characters treated as an explicit field separator.
    SEPARATORS = ":="

    def __init__(self, *, gap_threshold_points: float = 35.0) -> None:
        self.gap_threshold_points = gap_threshold_points

    def is_applicable(self, page: PageContext) -> bool:
        return page.has_text_layer

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []

        results: list[DetectedComponent] = []
        seen: set[tuple[str, str, tuple[int, int, int, int]]] = set()
        index = 1

        for line in group_into_lines(extract_words(page)):
            if len(line.words) < 2:
                continue
            if page.to_pixels(line.bbox).is_excluded_by(exclusions, threshold=0.35):
                continue

            for segment, parsed, confidence in self._candidates(line):
                key, value, separator = parsed
                bbox = page.to_pixels(segment.bbox)
                fingerprint = (key.lower(), value.lower(), bbox.to_tuple())
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)

                results.append(
                    DetectedComponent(
                        id=f"key_value_{page.page_number:03d}_{index:03d}",
                        type=ComponentType.KEY_VALUE,
                        page=page.page_number,
                        bbox=bbox,
                        text=f"{key}: {value}",
                        confidence=confidence,
                        index=index,
                        metadata={
                            "strategy": self.name,
                            "key": key,
                            "value": value,
                            "separator": separator,
                        },
                    )
                )
                index += 1

        return results

    def _candidates(self, line: TextLine):
        """Yield ``(segment, (key, value, sep), confidence)`` for one line."""
        # A line with several separators holds several pairs side by side.
        multi = list(self._multi_pair_candidates(line))
        if multi:
            yield from multi
            return

        parsed = self._parse_separator(line.text)
        if parsed and self._is_valid(parsed[0], parsed[1]):
            yield line, parsed, 0.90
            return

        parsed = self._parse_gap(line)
        if parsed and self._is_valid(parsed[0], parsed[1]):
            yield line, parsed, 0.78

    def _separator_indices(self, line: TextLine) -> list[int]:
        """Word positions acting as field separators.

        Matches a standalone ``:``/``=`` and the common ``Key:`` form. A colon
        inside a number (``11:58``) is not a field separator.
        """
        found: list[int] = []
        for index, word in enumerate(line.words):
            text = word.text
            if text in self.SEPARATORS:
                found.append(index)
            elif len(text) > 1 and text[-1] in self.SEPARATORS:
                found.append(index)
        return found

    def _multi_pair_candidates(self, line: TextLine):
        """Split a form line holding two or more pairs.

        Uses the separators as anchors instead of guessing column boundaries
        from gap widths. The gap between a key and its value and the gap
        between columns are both wide, and which is wider depends on the
        layout — so a gap threshold cannot tell them apart. Between two known
        separators, however, exactly one boundary exists: where the previous
        pair's value ends and the next pair's key begins. That is the widest
        gap in *that stretch alone*, which is an easy and reliable decision.
        """
        separators = self._separator_indices(line)
        if len(separators) < 2:
            return

        # Word index at which each pair's key starts.
        boundaries: list[int] = [0]
        for current, following in zip(separators, separators[1:]):
            between = list(range(current + 1, following))
            if len(between) < 2:
                # Nothing to split: the value or the key is a single word.
                boundaries.append(following - 1 if between else following)
                continue
            widest_at = max(
                between[:-1],
                key=lambda i: line.words[i + 1].bbox.x - line.words[i].bbox.x1,
            )
            boundaries.append(widest_at + 1)
        boundaries.append(len(line.words))

        for pair_index, separator_at in enumerate(separators):
            key_start = boundaries[pair_index]
            value_end = boundaries[pair_index + 1]

            key_words = line.words[key_start:separator_at]
            # A trailing "Key:" carries its own separator, so include it.
            if not key_words and separator_at > key_start - 1:
                key_words = line.words[key_start:separator_at + 1]
                value_words = line.words[separator_at + 1:value_end]
            else:
                value_words = line.words[separator_at + 1:value_end]

            if not key_words or not value_words:
                continue

            key = self._clean(" ".join(w.text for w in key_words))
            value = self._clean(" ".join(w.text for w in value_words))
            if not self._is_valid(key, value):
                continue

            segment = TextLine(tuple(key_words + value_words))
            yield segment, (key, value, ":"), 0.90

    def _parse_separator(self, text: str) -> tuple[str, str, str] | None:
        """Split on the first *field* separator in *text*.

        Scans candidates rather than taking the first ``:`` blindly: a colon
        between two digits belongs to a time or a ratio (``11:58``), not to a
        field, and splitting there yields nonsense like
        ``key="11-Feb-2026 11", value="58 AM"``.
        """
        for position, char in enumerate(text):
            if char not in self.SEPARATORS:
                continue
            if self._is_inside_number(text, position):
                continue

            key = self._clean(text[:position])
            value = self._clean(text[position + 1:])
            if key and value:
                return key, value, char

        return None

    @staticmethod
    def _is_inside_number(text: str, position: int) -> bool:
        """True when the character at *position* is flanked by digits."""
        before = text[position - 1] if position > 0 else ""
        after = text[position + 1] if position + 1 < len(text) else ""
        return before.isdigit() and after.isdigit()

    def _parse_gap(self, line: TextLine) -> tuple[str, str, str] | None:
        """Treat the widest gap in a short line as an implicit separator."""
        if len(line.words) > 10:
            return None

        gaps = [
            (right.bbox.x - left.bbox.x1, i)
            for i, (left, right) in enumerate(zip(line.words, line.words[1:]))
        ]
        if not gaps:
            return None

        widest, split_at = max(gaps, key=lambda item: item[0])
        if widest < self.gap_threshold_points:
            return None

        left_words = line.words[: split_at + 1]
        right_words = line.words[split_at + 1 :]
        if not left_words or not right_words:
            return None

        return (
            self._clean(" ".join(w.text for w in left_words)),
            self._clean(" ".join(w.text for w in right_words)),
            "gap",
        )

    @staticmethod
    def _is_valid(key: str, value: str) -> bool:
        if not key or not value:
            return False
        if len(key) > 80 or len(value) > 160:
            return False
        if len(key.split()) > 8:
            return False
        if sum(ch.isalpha() for ch in key) < 2:
            return False
        # A trailing full stop suggests the "key" is really the tail of a
        # sentence — but only when it is long. Short abbreviated labels such as
        # "Ref. Dr." or "No." are perfectly ordinary field names.
        if key.endswith(".") and len(key.split()) > 4:
            return False
        return True

    @staticmethod
    def _clean(text: str) -> str:
        return " ".join(text.strip(" \t:-=").split())
