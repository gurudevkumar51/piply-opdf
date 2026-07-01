from __future__ import annotations

from typing import Any

import fitz


BBox = tuple[int, int, int, int]


class ParagraphDetector:
    """
    Detects paragraph text from PyMuPDF words.

    Paragraphs are built from consecutive paragraph-like lines after excluding
    tables, headers, footers, and already-detected key-value rows. Each
    paragraph also carries word boxes so words can become OCR/review units.
    """

    def __init__(self, target_dpi: int = 300) -> None:
        self.target_dpi = target_dpi
        self.scale = target_dpi / 72.0

    def detect_paragraphs(
        self,
        doc_path: str,
        page_num: int,
        exclusion_bboxes: list[BBox] | None = None,
    ) -> dict[str, Any]:
        exclusion_bboxes = exclusion_bboxes or []

        doc = fitz.open(doc_path)
        try:
            page = doc[page_num - 1]
            words = page.get_text("words")
        finally:
            doc.close()

        lines = self._group_words_by_line(words)
        paragraphs: list[dict[str, Any]] = []
        sentences: list[dict[str, Any]] = []
        current_lines: list[list[tuple]] = []
        paragraph_idx = 1
        sentence_idx = 1

        for line_words in lines:
            line_bbox = self._scale_bbox(*self._line_bbox(line_words))
            line_text = " ".join(str(word[4]) for word in line_words).strip()

            if self._is_excluded(line_bbox, exclusion_bboxes) or not self._looks_like_paragraph_line(line_text):
                print("Excluded line:", line_text, "Excluded by bbox:", self._is_excluded(line_bbox, exclusion_bboxes), "Looks like paragraph:", self._looks_like_paragraph_line(line_text))
                paragraph_idx, sentence_idx = self._flush_paragraph(
                    current_lines,
                    paragraphs,
                    sentences,
                    page_num,
                    paragraph_idx,
                    sentence_idx,
                )
                current_lines = []
                continue


            if current_lines:
                gap = self._line_gap(current_lines[-1], line_words)
                prev_x0 = min(w[0] for w in current_lines[-1])
                curr_x0 = min(w[0] for w in line_words)
                prev_x1 = max(w[2] for w in current_lines[-1])
                
                # Split if:
                # 1. Vertical gap > 12pt (standard blank line)
                # 2. X0 indentation shift > 10pt (new bullet/section)
                # 3. Previous line ended early (x1 < 350) leaving lots of empty space
                if gap > 12 or abs(prev_x0 - curr_x0) > 10 or prev_x1 < 350:
                    paragraph_idx, sentence_idx = self._flush_paragraph(
                        current_lines,
                        paragraphs,
                        sentences,
                        page_num,
                        paragraph_idx,
                        sentence_idx,
                    )
                    current_lines = []

            current_lines.append(line_words)

        self._flush_paragraph(current_lines, paragraphs, sentences, page_num, paragraph_idx, sentence_idx)
        return {"paragraphs": paragraphs, "sentences": sentences}

    def _flush_paragraph(
        self,
        lines: list[list[tuple]],
        paragraphs: list[dict[str, Any]],
        sentences: list[dict[str, Any]],
        page_num: int,
        paragraph_idx: int,
        sentence_idx: int,
    ) -> tuple[int, int]:
        if not lines:
            return paragraph_idx, sentence_idx

        all_words = [word for line in lines for word in line]
        text = " ".join(str(word[4]) for word in all_words).strip()
        if not self._looks_like_paragraph(text):
            return paragraph_idx, sentence_idx

        is_sentence = len(lines) == 1
        target_list = sentences if is_sentence else paragraphs
        comp_type = "sentence" if is_sentence else "paragraph"
        idx = sentence_idx if is_sentence else paragraph_idx

        bbox = self._scale_bbox(*self._line_bbox(all_words))
        word_items = []
        for word_idx, word in enumerate(all_words, start=1):
            word_text = str(word[4]).strip()
            if not word_text:
                continue
            word_bbox = self._scale_bbox(word[0], word[1], word[2], word[3])
            word_items.append(
                {
                    "id": f"word_{page_num:03d}_{idx:03d}_{word_idx:03d}",
                    "type": "word",
                    "page": page_num,
                    "bbox": list(word_bbox),
                    "text": word_text,
                    "confidence": 0.88,
                }
            )

        target_list.append(
            {
                "id": f"{comp_type}_{page_num:03d}_{idx:03d}",
                "type": comp_type,
                "page": page_num,
                "bbox": list(bbox),
                "text": text,
                "word_count": len(word_items),
                "line_count": len(lines),
                "words": word_items,
                "confidence": self._confidence(text, len(lines)),
            }
        )
        
        if is_sentence:
            return paragraph_idx, sentence_idx + 1
        else:
            return paragraph_idx + 1, sentence_idx

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
        by_line: dict[tuple[int, int], list[tuple]] = {}
        for word in words:
            if len(word) < 7 or not str(word[4]).strip():
                continue
            block_no = int(word[5])
            line_no = int(word[6])
            by_line.setdefault((block_no, line_no), []).append(word)

        lines = []
        for line_words in by_line.values():
            line_words.sort(key=lambda item: item[0])
            merged_line_words = self._merge_wrapped_words(line_words)
            lines.append(merged_line_words)

        lines.sort(key=lambda items: (items[0][1], items[0][0]))
        return lines

    def _line_bbox(self, line_words: list[tuple]) -> tuple[float, float, float, float]:
        x0 = min(word[0] for word in line_words)
        y0 = min(word[1] for word in line_words)
        x1 = max(word[2] for word in line_words)
        y1 = max(word[3] for word in line_words)
        return x0, y0, x1, y1

    def _line_gap(self, prev_line: list[tuple], next_line: list[tuple]) -> float:
        return min(word[1] for word in next_line) - max(word[3] for word in prev_line)

    def _scale_bbox(self, x0: float, y0: float, x1: float, y1: float) -> BBox:
        sx0 = int(x0 * self.scale)
        sy0 = int(y0 * self.scale)
        sx1 = int(x1 * self.scale)
        sy1 = int(y1 * self.scale)
        return (sx0, sy0, sx1 - sx0, sy1 - sy0)

    def _looks_like_paragraph_line(self, text: str) -> bool:
        words = text.split()
        if not words:
            return False
        if self._looks_like_key_value(text):
            return False

        alpha_chars = sum(ch.isalpha() for ch in text)
        if alpha_chars < 2:
            return False

        return True

    def _looks_like_paragraph(self, text: str) -> bool:
        words = text.split()
        if len(words) < 2:
            return False
        if self._looks_like_key_value(text):
            return False

        return True

    def _looks_like_key_value(self, text: str) -> bool:
        if ":" not in text and "=" not in text:
            return False
        return len(text.split()) <= 14

    def _confidence(self, text: str, line_count: int) -> float:
        words = len(text.split())
        if words >= 25 or line_count >= 2:
            return 0.9
        if words >= 15:
            return 0.84
        return 0.76

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
            if overlap_area / max(1, bw * bh) > 0.45:
                return True

        return False
