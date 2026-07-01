from __future__ import annotations

import re
from typing import Any

import fitz


BBox = tuple[int, int, int, int]


class KeyValueDetector:
    """
    Detects simple key-value rows from embedded PDF text.

    The detector intentionally stays conservative: it prefers explicit
    separators and obvious two-part lines over guessing inside paragraphs.
    """

    _SEPARATOR_PATTERN = re.compile(r"^\s*(?P<key>.{1,80}?)(?P<sep>[:=])\s*(?P<value>.+?)\s*$")

    def __init__(self, target_dpi: int = 300) -> None:
        self.target_dpi = target_dpi
        self.scale = target_dpi / 72.0

    def detect_key_values(
        self,
        doc_path: str,
        page_num: int,
        exclusion_bboxes: list[BBox] | None = None,
    ) -> list[dict[str, Any]]:
        exclusion_bboxes = exclusion_bboxes or []

        doc = fitz.open(doc_path)
        try:
            page = doc[page_num - 1]
            words = page.get_text("words")
        finally:
            doc.close()

        lines = self._group_words_by_line(words)
        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str, BBox]] = set()
        kv_idx = 1

        for line_words in lines:
            if len(line_words) < 2:
                continue

            line_text = " ".join(word[4] for word in line_words).strip()
            bbox = self._line_bbox(line_words)
            scaled_bbox = self._scale_bbox(*bbox)

            if self._is_excluded(scaled_bbox, exclusion_bboxes):
                continue

            # First, try splitting the line by large horizontal gaps.
            # If multiple independent KVs exist on the same line, this will separate them.
            sub_lines = self._split_by_gaps(line_words, threshold=35)
            parsed_sub_lines = []
            if len(sub_lines) > 1:
                for sl in sub_lines:
                    sl_text = " ".join(word[4] for word in sl).strip()
                    sl_parsed = self._parse_separator_line(sl_text)
                    if sl_parsed and self._valid_key_value(sl_parsed[0], sl_parsed[1]):
                        parsed_sub_lines.append((sl_parsed, sl))

            if len(parsed_sub_lines) > 1 or (len(parsed_sub_lines) == 1 and len(sub_lines) > 1):
                # Emit the valid sub-lines as independent key-values
                for (key, value, separator), sl in parsed_sub_lines:
                    sl_bbox = self._line_bbox(sl)
                    sl_scaled = self._scale_bbox(*sl_bbox)
                    fingerprint = (key.lower(), value.lower(), sl_scaled)
                    if fingerprint not in seen:
                        seen.add(fingerprint)
                        results.append({
                            "id": f"key_value_{page_num:03d}_{kv_idx:03d}",
                            "type": "key_value",
                            "page": page_num,
                            "bbox": list(sl_scaled),
                            "text": f"{key}: {value}",
                            "key": key,
                            "value": value,
                            "separator": separator,
                            "confidence": 0.9,
                        })
                        kv_idx += 1
                continue

            parsed = self._parse_separator_line(line_text)
            confidence = 0.9

            if parsed is None:
                parsed = self._parse_gap_line(line_words)
                confidence = 0.78

            if parsed is None:
                continue

            key, value, separator = parsed
            if not self._valid_key_value(key, value):
                continue

            fingerprint = (key.lower(), value.lower(), scaled_bbox)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)

            results.append(
                {
                    "id": f"key_value_{page_num:03d}_{kv_idx:03d}",
                    "type": "key_value",
                    "page": page_num,
                    "bbox": list(scaled_bbox),
                    "text": f"{key}: {value}",
                    "key": key,
                    "value": value,
                    "separator": separator,
                    "confidence": confidence,
                }
            )
            kv_idx += 1

        return results

    def _merge_wrapped_words(self, line_words: list[tuple]) -> list[tuple]:
        merged = []
        i = 0
        n = len(line_words)
        while i < n:
            w = line_words[i]
            text = str(w[4]).strip()
            
            is_open_bracket = text.startswith('[')
            is_open_paren = text.startswith('(')
            
            clean_text = text.rstrip('.,:;')
            is_closed_bracket = clean_text.endswith(']')
            is_closed_paren = clean_text.endswith(')')
            
            if (is_open_bracket and not is_closed_bracket) or \
               (is_open_paren and not is_closed_paren):
                
                group_words = [w]
                j = i + 1
                found_end = False
                while j < n:
                    nw = line_words[j]
                    ntext = str(nw[4]).strip()
                    ntext_clean = ntext.rstrip('.,:;')
                    group_words.append(nw)
                    
                    if (is_open_bracket and ntext_clean.endswith(']')) or \
                       (is_open_paren and ntext_clean.endswith(')')):
                        found_end = True
                        break
                    j += 1
                
                if found_end:
                    x0 = min(gw[0] for gw in group_words)
                    y0 = min(gw[1] for gw in group_words)
                    x1 = max(gw[2] for gw in group_words)
                    y1 = max(gw[3] for gw in group_words)
                    merged_text = " ".join(str(gw[4]).strip() for gw in group_words)
                    merged.append((x0, y0, x1, y1, merged_text, w[5], w[6], w[7]))
                    i = j + 1
                else:
                    merged.append(w)
                    i += 1
            else:
                merged.append(w)
                i += 1
                
        return merged

    def _group_words_by_line(self, words: list[tuple]) -> list[list[tuple]]:
        valid_words = [w for w in words if len(w) >= 7 and str(w[4]).strip()]
        valid_words.sort(key=lambda w: (w[1] + w[3]) / 2)

        lines = []
        current_line = []
        for w in valid_words:
            cy = (w[1] + w[3]) / 2
            if not current_line:
                current_line.append(w)
            else:
                last_cy = (current_line[0][1] + current_line[0][3]) / 2
                if abs(cy - last_cy) < 5:
                    current_line.append(w)
                else:
                    current_line.sort(key=lambda item: item[0])
                    merged_current = self._merge_wrapped_words(current_line)
                    lines.append(merged_current)
                    current_line = [w]
        if current_line:
            current_line.sort(key=lambda item: item[0])
            merged_current = self._merge_wrapped_words(current_line)
            lines.append(merged_current)

        lines.sort(key=lambda items: (items[0][1], items[0][0]))
        return lines

    def _split_by_gaps(self, line_words: list[tuple], threshold: float = 35.0) -> list[list[tuple]]:
        if not line_words:
            return []
        chunks = []
        current_chunk = [line_words[0]]
        for i in range(1, len(line_words)):
            prev_word = line_words[i - 1]
            curr_word = line_words[i]
            gap = curr_word[0] - prev_word[2]
            if gap > threshold:
                chunks.append(current_chunk)
                current_chunk = [curr_word]
            else:
                current_chunk.append(curr_word)
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def _line_bbox(self, line_words: list[tuple]) -> tuple[float, float, float, float]:
        x0 = min(word[0] for word in line_words)
        y0 = min(word[1] for word in line_words)
        x1 = max(word[2] for word in line_words)
        y1 = max(word[3] for word in line_words)
        return x0, y0, x1, y1

    def _scale_bbox(self, x0: float, y0: float, x1: float, y1: float) -> BBox:
        sx0 = int(x0 * self.scale)
        sy0 = int(y0 * self.scale)
        sx1 = int(x1 * self.scale)
        sy1 = int(y1 * self.scale)
        return (sx0, sy0, sx1 - sx0, sy1 - sy0)

    def _parse_separator_line(self, text: str) -> tuple[str, str, str] | None:
        match = self._SEPARATOR_PATTERN.match(text)
        if not match:
            return None

        key = self._clean_part(match.group("key"))
        value = self._clean_part(match.group("value"))
        return key, value, match.group("sep")

    def _parse_gap_line(self, line_words: list[tuple]) -> tuple[str, str, str] | None:
        if len(line_words) > 10:
            return None

        gaps = []
        for idx in range(len(line_words) - 1):
            left = line_words[idx]
            right = line_words[idx + 1]
            gaps.append((right[0] - left[2], idx))

        if not gaps:
            return None

        max_gap, split_idx = max(gaps, key=lambda item: item[0])
        if max_gap < 35:
            return None

        left_words = line_words[: split_idx + 1]
        right_words = line_words[split_idx + 1 :]
        if not left_words or not right_words:
            return None

        key = self._clean_part(" ".join(word[4] for word in left_words))
        value = self._clean_part(" ".join(word[4] for word in right_words))
        return key, value, "gap"

    def _valid_key_value(self, key: str, value: str) -> bool:
        if not key or not value:
            return False
        if len(key) > 80 or len(value) > 160:
            return False
        if len(key.split()) > 8:
            return False
        if sum(ch.isalpha() for ch in key) < 2:
            return False
        if key.endswith("."):
            return False
        return True

    def _clean_part(self, text: str) -> str:
        return " ".join(text.strip(" \t:-=").split())

    def _is_excluded(self, bbox: BBox, exclusion_bboxes: list[BBox]) -> bool:
        bx, by, bw, bh = bbox
        if bw <= 0 or bh <= 0:
            return True

        cx = bx + bw / 2
        cy = by + bh / 2

        for ex, ey, ew, eh in exclusion_bboxes:
            if ex <= cx <= ex + ew and ey <= cy <= ey + eh:
                return True

            overlap_w = max(0, min(bx + bw, ex + ew) - max(bx, ex))
            overlap_h = max(0, min(by + bh, ey + eh) - max(by, ey))
            overlap_area = overlap_w * overlap_h
            if overlap_area / max(1, bw * bh) > 0.35:
                return True

        return False
